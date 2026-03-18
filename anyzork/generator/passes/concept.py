"""Pass 1: World Concept — interprets the user prompt into structured world parameters.

This is the root pass. It reads only the raw user prompt and produces
a concept document that every subsequent pass consumes: theme, setting,
tone, era, scale targets, vocabulary hints, and genre tags.
"""

from __future__ import annotations

import json

from anyzork.db.schema import GameDB
from anyzork.generator.providers.base import BaseProvider, GenerationContext

# ---------------------------------------------------------------------------
# JSON schema the LLM must conform to
# ---------------------------------------------------------------------------

CONCEPT_SCHEMA: dict = {
    "type": "object",
    "required": [
        "theme",
        "setting",
        "tone",
        "era",
        "scale",
        "room_count_target",
        "region_count_target",
        "vocabulary_hints",
        "genre_tags",
        "win_condition_description",
    ],
    "properties": {
        "theme": {
            "type": "string",
            "description": "1-3 word thematic tag (e.g. 'sci-fi horror', 'dark fantasy').",
        },
        "setting": {
            "type": "string",
            "description": (
                "A paragraph describing the world: where is it, what happened, "
                "who is the player, what is the situation."
            ),
        },
        "tone": {
            "type": "string",
            "enum": ["dark", "whimsical", "serious", "comedic", "surreal", "grim", "hopeful"],
            "description": "Dominant tonal register of the world.",
        },
        "era": {
            "type": "string",
            "description": "When this world exists (e.g. 'far future', 'medieval', '1920s').",
        },
        "scale": {
            "type": "string",
            "enum": ["small", "medium", "large"],
            "description": (
                "World size tier. small = 8-15 rooms / 1 region. "
                "medium = 16-30 rooms / 2-3 regions. "
                "large = 31-50 rooms / 4-6 regions."
            ),
        },
        "room_count_target": {
            "type": "integer",
            "minimum": 8,
            "maximum": 50,
            "description": "Exact target number of rooms to generate.",
        },
        "region_count_target": {
            "type": "integer",
            "minimum": 1,
            "maximum": 6,
            "description": "Exact target number of thematic regions.",
        },
        "vocabulary_hints": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "description": (
                "Words and naming conventions that fit the tone. "
                "E.g. ['corridor', 'bulkhead', 'terminal'] for sci-fi."
            ),
        },
        "genre_tags": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": "Gameplay genre tags (e.g. 'exploration', 'puzzle', 'survival').",
        },
        "win_condition_description": {
            "type": "string",
            "description": (
                "A plain-language description of how the player wins. "
                "E.g. 'Escape the station by reaching the shuttle bay after restoring power.'"
            ),
        },
    },
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_PROMPT = """\
You are a world concept designer for a text adventure game engine called AnyZork.

The player has described the game they want with this prompt:

---
{user_prompt}
---

Your job is to interpret this prompt and produce a structured concept document \
that will guide all subsequent generation passes (rooms, exits, items, NPCs, \
puzzles, commands, and lore).

## Interpretation Guidelines

1. **Be generous but precise.** Expand vague prompts into concrete worlds. \
"A spooky house" becomes a specific haunted manor with a history, a reason \
the player is there, and a goal. Never ignore explicit details the user gave.

2. **Establish who the player is.** The player character needs a reason to \
be in this place and a goal to achieve. This drives the win condition.

3. **Pick a scale that matches the prompt.** A single building or ship is \
small (8-15 rooms). A complex with multiple wings is medium (16-30 rooms). \
A sprawling world with distinct zones is large (31-50 rooms). When in doubt, \
choose medium.

4. **Vocabulary hints matter.** They set the lexicon for every room name, \
item name, and description in the game. A medieval castle uses "chamber", \
"torch", "tapestry". A space station uses "module", "terminal", "airlock". \
Provide at least 6 vocabulary hints.

5. **Genre tags guide gameplay.** "puzzle" means lock-key-gate structures. \
"exploration" means rewarding curiosity with lore and hidden areas. \
"survival" means resource tension. "combat" means hostile NPCs. \
Choose 2-4 tags that match the prompt.

6. **Win condition** must be achievable through exploration and puzzle-solving. \
Describe it in one or two sentences.

7. **Room and region counts** must be consistent with the chosen scale:
   - small: 8-15 rooms, 1 region
   - medium: 16-30 rooms, 2-3 regions
   - large: 31-50 rooms, 4-6 regions

## Output Format

Return a single JSON object matching this schema:

```json
{schema_json}
```

Produce ONLY the JSON object. No commentary, no markdown fences.
"""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_VALID_SCALES = {"small", "medium", "large"}

_SCALE_RANGES: dict[str, dict] = {
    "small":  {"rooms": (8, 15),  "regions": (1, 1)},
    "medium": {"rooms": (16, 30), "regions": (2, 3)},
    "large":  {"rooms": (31, 50), "regions": (4, 6)},
}


class ConceptValidationError(ValueError):
    """Raised when the LLM output fails structural validation."""


def _validate(concept: dict) -> None:
    """Raise ``ConceptValidationError`` if the concept is structurally invalid."""
    errors: list[str] = []

    # Required string fields must be non-empty
    for field in ("theme", "setting", "tone", "era", "win_condition_description"):
        val = concept.get(field)
        if not val or not isinstance(val, str) or not val.strip():
            errors.append(f"'{field}' is missing or empty.")

    # Scale must be a known tier
    scale = concept.get("scale", "")
    if scale not in _VALID_SCALES:
        errors.append(
            f"'scale' must be one of {sorted(_VALID_SCALES)}, got '{scale}'."
        )

    # Room and region counts must be within the scale's range
    if scale in _SCALE_RANGES:
        rng = _SCALE_RANGES[scale]
        room_count = concept.get("room_count_target", 0)
        rmin, rmax = rng["rooms"]
        if not (rmin <= room_count <= rmax):
            errors.append(
                f"room_count_target ({room_count}) out of range for "
                f"scale '{scale}' ({rmin}-{rmax})."
            )
        region_count = concept.get("region_count_target", 0)
        rgmin, rgmax = rng["regions"]
        if not (rgmin <= region_count <= rgmax):
            errors.append(
                f"region_count_target ({region_count}) out of range for "
                f"scale '{scale}' ({rgmin}-{rgmax})."
            )

    # Vocabulary hints
    vocab = concept.get("vocabulary_hints", [])
    if not isinstance(vocab, list) or len(vocab) < 3:
        errors.append("'vocabulary_hints' must be a list with at least 3 entries.")

    # Genre tags
    tags = concept.get("genre_tags", [])
    if not isinstance(tags, list) or len(tags) < 1:
        errors.append("'genre_tags' must be a list with at least 1 entry.")

    if errors:
        raise ConceptValidationError(
            "Concept validation failed:\n  - " + "\n  - ".join(errors)
        )


# ---------------------------------------------------------------------------
# Pass entry point
# ---------------------------------------------------------------------------

def run_pass(db: GameDB, provider: BaseProvider, context: dict) -> dict:
    """Run Pass 1: World Concept.

    Reads ``context["user_prompt"]``, asks the LLM to produce a concept
    document, validates it, stores it in the metadata table, and returns
    the updated context with the concept dict.

    Args:
        db: The GameDB instance (must already be initialized with tables).
        provider: The LLM provider to call.
        context: Pipeline context dict.  Must contain ``"user_prompt"``.

    Returns:
        Updated context dict with ``"concept"`` key added.

    Raises:
        ConceptValidationError: If the LLM output fails validation.
    """
    user_prompt: str = context.get("user_prompt") or context["prompt"]

    # Build the prompt
    prompt = _PROMPT.format(
        user_prompt=user_prompt,
        schema_json=json.dumps(CONCEPT_SCHEMA, indent=2),
    )

    # Build generation context for the provider
    gen_ctx = GenerationContext(
        seed=context.get("seed"),
        temperature=0.7,
        max_tokens=4_096,
    )

    # Call the LLM
    concept: dict = provider.generate_structured(
        prompt=prompt,
        schema=CONCEPT_SCHEMA,
        context=gen_ctx,
    )

    # Validate
    _validate(concept)

    # Persist concept data into the metadata table
    db.set_meta("title", f"AnyZork: {concept['theme'].title()}")
    db.set_meta("region_count", concept["region_count_target"])
    db.set_meta("room_count", concept["room_count_target"])

    # Store the full concept as a JSON string in author_prompt alongside
    # the raw user prompt so later passes can retrieve it.
    db.set_meta(
        "author_prompt",
        json.dumps(
            {"user_prompt": user_prompt, "concept": concept},
            indent=2,
        ),
    )

    # Return the concept dict — the orchestrator stores this as results["concept"]
    # and later passes access it via context["concept"]
    return concept
