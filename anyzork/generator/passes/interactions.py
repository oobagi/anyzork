"""Pass 5b: Interaction Responses -- Generate the interaction matrix.

Runs after items (Pass 4) and NPCs (Pass 5).  Reads all items with
``item_tags`` and all NPC categories from context, then prompts the LLM
to generate response templates for each item_tag x target_category
combination.  Also generates wildcard (``"*"``) defaults.

The interaction matrix handles "soft" interactions -- the ones that
produce flavor text but don't change game state.  DSL commands still
handle "hard" interactions (puzzle solutions, state changes).  The
engine resolves DSL commands first, then falls back to the interaction
matrix, then to built-in handlers.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from anyzork.db.schema import GameDB
from anyzork.generator.providers.base import BaseProvider, GenerationContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON schema the LLM must conform to
# ---------------------------------------------------------------------------

INTERACTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["interaction_responses"],
    "properties": {
        "interaction_responses": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "item_tag",
                    "target_category",
                    "response",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique snake_case identifier.",
                    },
                    "item_tag": {
                        "type": "string",
                        "description": (
                            "Tag on the item being used. Must match a tag "
                            "from the items list, or '*' for a wildcard default."
                        ),
                    },
                    "target_category": {
                        "type": "string",
                        "description": (
                            "Category on the target (item or NPC). Must match "
                            "a category from items or NPCs, or '*' for a "
                            "wildcard default."
                        ),
                    },
                    "response": {
                        "type": "string",
                        "description": (
                            "Template text with {item} and {target} placeholders. "
                            "1-2 sentences. Must not change game state."
                        ),
                    },
                    "priority": {
                        "type": "integer",
                        "description": (
                            "Higher priority wins on ambiguous matches. "
                            "Specific matches should be 0+, wildcard defaults "
                            "should be -1."
                        ),
                    },
                    "room_id": {
                        "type": ["string", "null"],
                        "description": (
                            "Room ID where this response is active. "
                            "NULL = global (works anywhere)."
                        ),
                    },
                    "requires_state": {
                        "type": ["string", "null"],
                        "description": (
                            "Item must be in this toggle_state for the "
                            "response to match. NULL = any state."
                        ),
                    },
                    "consumes": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": (
                            "1 = triggers quantity consumption on the item. "
                            "0 = no consumption."
                        ),
                    },
                    "consume_amount": {
                        "type": "integer",
                        "description": (
                            "How many units to consume when consumes = 1. "
                            "Default 1."
                        ),
                    },
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_prompt(context: dict) -> str:
    """Construct the LLM prompt for interaction response generation."""

    concept = context.get("concept", {})
    items = context.get("items", [])
    npcs = context.get("npcs", [])
    realism = context.get("realism", "medium")

    # Collect unique item tags from all items.
    all_tags: set[str] = set()
    for item in items:
        tags = item.get("item_tags")
        if tags:
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except (json.JSONDecodeError, TypeError):
                    tags = []
            for tag in tags:
                all_tags.add(tag)

    # Collect unique target categories from items and NPCs.
    all_categories: set[str] = set()
    for item in items:
        cat = item.get("category")
        if cat:
            all_categories.add(cat)
    for npc in npcs:
        cat = npc.get("category")
        if cat:
            all_categories.add(cat)

    items_summary = json.dumps(
        [
            {
                "id": i["id"],
                "name": i["name"],
                "item_tags": i.get("item_tags"),
                "category": i.get("category"),
            }
            for i in items
            if i.get("item_tags")
        ],
        indent=2,
    )

    npcs_summary = json.dumps(
        [
            {
                "id": n["id"],
                "name": n["name"],
                "category": n.get("category"),
            }
            for n in npcs
        ],
        indent=2,
    )

    return f"""\
You are a game interaction designer for a Zork-style text adventure engine.

## World Concept
{json.dumps(concept, indent=2)}

## Items with Tags
{items_summary}

## NPCs with Categories
{npcs_summary}

## Item Tags Present in This World
{json.dumps(sorted(all_tags), indent=2)}

## Target Categories Present in This World
{json.dumps(sorted(all_categories), indent=2)}

## Your Task -- Generate Interaction Responses

Generate interaction response templates for this game world. These are
used when the player types "use {{item}} on {{target}}" and no DSL command
matches. The interaction matrix provides contextual flavor text.

### How It Works

Each response maps an **item tag** to a **target category**:
- `item_tag`: a tag from the item being used (e.g., "firearm", "blade")
- `target_category`: the category of the target (e.g., "character", "furniture")
- `response`: template text with {{item}} and {{target}} placeholders

When the player uses an item on a target, the engine:
1. Gets the item's tags (e.g., ["weapon", "firearm"])
2. Gets the target's category (e.g., "character")
3. Finds the best matching response by tag + category
4. Substitutes {{item}} and {{target}} with display names

### Requirements

1. For each item tag present in the world, create response templates for
   every target category that makes a logical pairing.

2. Always include wildcard defaults:
   - A default for each item tag with `target_category: "*"` (catches
     any target not specifically handled)
   - A global default with `item_tag: "*"` and `target_category: "*"`
     at priority -1 (absolute fallback)

3. Responses should:
   - Match the game's tone and setting
   - Use {{item}} and {{target}} placeholders (REQUIRED)
   - Be 1-2 sentences
   - NOT change game state (state changes are handled by DSL commands)
   - Feel natural and specific to the world

4. Set `consumes: 1` on responses where using the item logically expends
   a resource (firing a gun uses ammo, swinging a blade does not).

5. Priority ordering:
   - Specific tag + specific category: 0 (default)
   - Specific tag + wildcard category (*): -1
   - Wildcard tag (*) + wildcard category (*): -2

### Realism Level: {realism}

- Low: responses are brief and functional
- Medium: responses are atmospheric and contextual
- High: responses include consequences (noise attracting attention,
  damage descriptions, realistic reactions)

### CRITICAL: Use Exact IDs

If you reference a `room_id`, it must match an existing room ID from the
world. For most responses, leave `room_id` as null (global).

### Output Format

```json
{{{{
  "interaction_responses": [
    {{{{
      "id": "firearm_character",
      "item_tag": "firearm",
      "target_category": "character",
      "response": "{{{{target}}}} dives for cover as you level the {{{{item}}}}.",
      "priority": 0,
      "room_id": null,
      "requires_state": null,
      "consumes": 0,
      "consume_amount": 1
    }}}},
    {{{{
      "id": "global_default",
      "item_tag": "*",
      "target_category": "*",
      "response": "Nothing interesting happens.",
      "priority": -2,
      "room_id": null,
      "requires_state": null,
      "consumes": 0,
      "consume_amount": 1
    }}}}
  ]
}}}}
```

Generate responses for ALL tag-category combinations that make sense,
plus wildcard defaults. Be thorough.
"""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_interactions(
    responses: list[dict], context: dict
) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors: list[str] = []
    room_ids = {r["id"] for r in context.get("rooms", [])}
    seen_ids: set[str] = set()

    has_global_default = False

    for resp in responses:
        rid = resp.get("id", "<missing>")

        # Unique ID
        if rid in seen_ids:
            errors.append(f"Duplicate interaction response id: {rid}")
        seen_ids.add(rid)

        # Required fields
        for field in ("item_tag", "target_category", "response"):
            if not resp.get(field):
                errors.append(
                    f"Interaction response {rid} missing required field: {field}"
                )

        # Room reference
        room_id = resp.get("room_id")
        if room_id is not None and room_id not in room_ids:
            errors.append(
                f"Interaction response {rid} references unknown room: {room_id}"
            )

        # Check for global default
        if resp.get("item_tag") == "*" and resp.get("target_category") == "*":
            has_global_default = True

    if not has_global_default:
        errors.append(
            "No global default interaction response (*/*) found. "
            "Add one with priority -2."
        )

    return errors


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------


def _insert_interactions(
    db: GameDB, responses: list[dict], context: dict
) -> list[dict]:
    """Insert validated interaction responses into the database.

    Returns the list of successfully inserted responses.
    """
    room_ids = {r["id"] for r in context.get("rooms", [])}
    inserted: list[dict] = []

    for resp in responses:
        rid = resp.get("id", "<unknown>")

        # Validate room_id (nullable FK)
        room_id = resp.get("room_id")
        if room_id is not None and room_id not in room_ids:
            logger.warning(
                "Interaction response %s references non-existent room_id %r "
                "-- setting to NULL",
                rid,
                room_id,
            )
            resp["room_id"] = None

        db.insert_interaction_response(
            id=resp["id"],
            item_tag=resp["item_tag"],
            target_category=resp["target_category"],
            response=resp["response"],
            priority=resp.get("priority", 0),
            room_id=resp.get("room_id"),
            requires_state=resp.get("requires_state"),
            consumes=resp.get("consumes", 0),
            consume_amount=resp.get("consume_amount", 1),
        )
        inserted.append(resp)

    return inserted


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_pass(db: GameDB, provider: BaseProvider, context: dict) -> dict:
    """Run Pass 5b: Interaction Responses.

    Returns updated context with interaction response data.
    """

    logger.info("Pass 5b: Generating interaction responses...")

    prompt = _build_prompt(context)
    gen_ctx = GenerationContext(
        existing_data={},
        seed=context.get("seed"),
        temperature=0.7,
        max_tokens=16_384,
    )

    result = provider.generate_structured(prompt, INTERACTIONS_SCHEMA, gen_ctx)
    responses: list[dict] = result.get("interaction_responses", [])

    # Validate
    errors = _validate_interactions(responses, context)
    if errors:
        for err in errors:
            logger.warning("Interaction validation: %s", err)

    # Insert into DB
    inserted = _insert_interactions(db, responses, context)

    # Build pass-specific data for downstream passes
    interactions_summary = [
        {
            "id": r["id"],
            "item_tag": r["item_tag"],
            "target_category": r["target_category"],
        }
        for r in inserted
    ]

    logger.info(
        "Pass 5b complete: %d interaction responses generated.",
        len(inserted),
    )
    return {"interactions": interactions_summary}
