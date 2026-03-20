"""Pass 6: Puzzles — Design multi-step challenges that gate progression.

Reads the world concept, rooms, items, NPCs, and locks from prior passes,
then prompts the LLM to generate puzzles.  Puzzles are the primary
progression mechanic — they are what makes the game a game rather than a
walking simulator.

Every puzzle obeys the **fairness contract**:

  1. All clues exist in the world.
  2. Clues precede (or accompany) the puzzle — never come after.
  3. Red herrings are minimal and fair.
  4. Failure feedback hints at what is wrong.
  5. No softlocks — the game is never unwinnable.

Puzzle types: fetch-and-apply, combination/sequence, environmental,
observation, dialogue, and multi-step chains.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from anyzork.db.schema import GameDB
from anyzork.generator.providers.base import BaseProvider, GenerationContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON schema the LLM must conform to
# ---------------------------------------------------------------------------

PUZZLE_INTENTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["puzzle_intents"],
    "properties": {
        "puzzle_intents": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "name",
                    "core_concept",
                    "primary_room_candidates",
                    "solution_beats",
                    "hint_progression",
                    "difficulty_hint",
                    "progression_role",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Stable snake_case slug for the puzzle concept.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Human-readable puzzle name.",
                    },
                    "core_concept": {
                        "type": "string",
                        "description": (
                            "The creative heart of the puzzle: what makes it interesting, "
                            "what the player realizes, and what fiction it expresses."
                        ),
                    },
                    "primary_room_candidates": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Ordered room IDs where this puzzle could plausibly anchor. "
                            "Use exact IDs from the room list."
                        ),
                    },
                    "clue_room_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Room IDs where clue breadcrumbs live.",
                    },
                    "involved_item_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Item IDs materially involved in the puzzle.",
                    },
                    "involved_npc_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "NPC IDs materially involved in the puzzle.",
                    },
                    "solution_beats": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Ordered creative beats for solving the puzzle. "
                            "These are intent-level beats, not final DSL commands."
                        ),
                    },
                    "hint_progression": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "2-3 progressive hints from vague to specific. "
                            "The most specific hint should make the solution "
                            "almost obvious."
                        ),
                    },
                    "difficulty_hint": {
                        "type": "integer",
                        "enum": [1, 2, 3],
                        "description": (
                            "Suggested difficulty. The compiler normalizes this."
                        ),
                    },
                    "progression_role": {
                        "type": "string",
                        "enum": ["critical", "optional"],
                        "description": (
                            "Whether the puzzle is critical-path or optional side content."
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
    """Construct the LLM prompt for puzzle-intent generation."""

    concept = context.get("concept", {})
    rooms = context.get("rooms", [])
    items = context.get("items", [])
    npcs = context.get("npcs", [])
    locks = context.get("locks", [])

    rooms_summary = json.dumps(
        [
            {
                "id": r["id"],
                "name": r["name"],
                "region": r["region"],
                "is_start": r.get("is_start", 0),
            }
            for r in rooms
        ],
        indent=2,
    )

    items_summary = json.dumps(
        [
            {
                "id": i["id"],
                "name": i["name"],
                "room_id": i.get("room_id"),
                "category": i.get("category"),
                "is_takeable": i.get("is_takeable", 1),
            }
            for i in items
        ],
        indent=2,
    )

    npcs_summary = json.dumps(
        [
            {
                "id": n["id"],
                "name": n["name"],
                "room_id": n["room_id"],
                "is_blocking": n.get("is_blocking", 0),
            }
            for n in npcs
        ],
        indent=2,
    )

    locks_summary = json.dumps(locks, indent=2) if locks else "[]"

    return f"""\
You are a puzzle designer for a Zork-style text adventure engine.

## World Concept
{json.dumps(concept, indent=2)}

## Existing Rooms
{rooms_summary}

## Existing Items
{items_summary}

## Existing NPCs
{npcs_summary}

## Existing Locks
{locks_summary}

## Your Task — Generate Puzzle Intents

Design multi-step puzzles that create moments of discovery and realization.
The best puzzles chain multiple steps, each feeling like its own "aha!" moment.

### CRITICAL: Use Exact IDs

You MUST use the exact `id` values from the existing data above. Do NOT
invent room IDs — copy them verbatim from the lists. If `room_id` does not
exactly match one of the room IDs listed in "Existing Rooms", the puzzle
will fail to insert.

### Puzzle Types

1. **Fetch and Apply** — Bring item X to location Y and use it.  More complex
   than a simple lock because it may involve multiple items or a specific order.

2. **Combination / Sequence** — Input a code, arrange objects in order, play
   notes in sequence.  The clue (code/sequence) is found elsewhere in the
   world.

3. **Environmental** — Manipulate room features: flip switches, redirect
   pipes, align mirrors.  The puzzle is understanding the system.

4. **Observation** — Notice a detail in a room description that reveals a
   hidden interaction.  The room description must contain the clue explicitly.

5. **Dialogue** — Extract information from an NPC by choosing the right
   conversation paths.  The clue is knowing what to ask.

6. **Multi-Step Chains** — The best puzzles combine types.  Example:
   find a torn page (fetch) that describes a constellation (knowledge),
   then align mirrors to match the constellation (environmental).

### The Fairness Contract — MANDATORY

Every puzzle MUST obey these rules:

1. **All clues exist in the world.**  The player never needs out-of-game
   knowledge.
2. **Clues precede the puzzle.**  The player encounters the clue before or
   simultaneously with the puzzle, never after.
3. **Red herrings are minimal and fair.**  A few misleading items add flavor;
   a world full of useless noise is hostile.
4. **Failure is informative.**  When a wrong solution is tried, the feedback
   hints at what is wrong — not just "nothing happens."
5. **No softlocks.**  The game is never unwinnable.  If a key item is consumed,
   it must not be needed again.  If a one-way path exists, everything needed
   beyond it is accessible.

### Difficulty Scaling

- **Difficulty 1** (easy): Single step, clue in the same or adjacent room.
  Good for early game / teaching mechanics.
- **Difficulty 2** (medium): 2-3 steps, clues spread across 2-3 rooms in the
  same region.  Core gameplay.
- **Difficulty 3** (hard): Multi-step, clues across regions.  Late-game
  synthesis puzzles.

### Hint Design

Each puzzle must have 2-3 progressive hints:
- **Hint 1**: Vague nudge in the right direction.
- **Hint 2**: Points to the relevant room or item.
- **Hint 3**: Nearly spells out the solution.

### Puzzle Coverage

- At least one puzzle per region.
- At least one critical-path puzzle (is_optional = 0) that gates progression.
- Optional puzzles (is_optional = 1) should reward with items, score, or lore.
- For puzzle-type locks in the locks data, create the corresponding puzzle
  whose completion unlocks the exit.
- Difficulty should increase from early regions to later regions.

### Score Values

- Easy puzzles: 10-15 points
- Medium puzzles: 15-20 points
- Hard puzzles: 20-30 points
- Optional puzzles can be slightly higher to reward going off the critical path.

### Output Format

Return a JSON object:

```json
{{
  "puzzle_intents": [
    {{
      "id": "snake_case_id",
      "name": "Human-Readable Name",
      "core_concept": "What the player realizes and why this puzzle is interesting",
      "primary_room_candidates": ["observatory", "library"],
      "clue_room_ids": ["library"],
      "involved_item_ids": ["torn_page", "telescope"],
      "involved_npc_ids": [],
      "solution_beats": [
        "Step 1: Find the torn page in the library",
        "Step 2: Read the page to learn the constellation",
        "Step 3: Use the telescope in the observatory to align to the constellation"
      ],
      "hint_progression": [
        "The observatory seems to be waiting for something. Have you explored the library?",
        "A torn page in the library mentions a constellation. The telescope might be useful.",
        "Try using the torn page, then look through the telescope."
      ],
      "difficulty_hint": 2,
      "progression_role": "critical"
    }}
  ]
}}
```

These are creative puzzle intents, not final DB rows. A deterministic compiler
will choose the legal primary room, normalize difficulty/score, and carry the
creative beats into later passes.
"""


def _slugify_puzzle_id(raw_id: str, used_ids: set[str]) -> str:
    """Return a stable unique snake_case puzzle id."""
    slug = re.sub(r"[^a-z0-9]+", "_", raw_id.lower()).strip("_")
    if not slug:
        slug = "puzzle"
    if not slug[0].isalpha():
        slug = f"puzzle_{slug}"

    candidate = slug
    index = 2
    while candidate in used_ids:
        candidate = f"{slug}_{index}"
        index += 1
    used_ids.add(candidate)
    return candidate


def _normalize_hint_progression(intent: dict) -> list[str]:
    """Return at least two progressive hints for a puzzle intent."""
    hints = [hint.strip() for hint in intent.get("hint_progression", []) if hint.strip()]
    if len(hints) >= 2:
        return hints[:3]

    concept = str(intent.get("core_concept", "")).strip()
    beats = [beat.strip() for beat in intent.get("solution_beats", []) if beat.strip()]

    if not hints and concept:
        hints.append(concept)
    if len(hints) < 2 and beats:
        hints.append(beats[0])
    if len(hints) < 2:
        hints.append("Look closely at the rooms and objects tied to this puzzle.")
    return hints[:3]


def _normalize_difficulty(intent: dict) -> int:
    """Return a legal puzzle difficulty from the intent."""
    raw = intent.get("difficulty_hint")
    if raw in (1, 2, 3):
        return raw

    step_count = len(intent.get("solution_beats", []))
    if step_count <= 1:
        return 1
    if step_count <= 3:
        return 2
    return 3


def _score_for_puzzle(difficulty: int, is_optional: int) -> int:
    """Return a normalized score value for the compiled puzzle."""
    base = {1: 12, 2: 18, 3: 24}[difficulty]
    if is_optional:
        base += 4
    return min(base, 30)


def _choose_puzzle_room(intent: dict, context: dict) -> str | None:
    """Pick a legal primary room deterministically from the intent."""
    rooms = context.get("rooms", [])
    room_ids = {room["id"] for room in rooms}

    for room_id in intent.get("primary_room_candidates", []):
        if room_id in room_ids:
            return room_id

    for room_id in intent.get("clue_room_ids", []):
        if room_id in room_ids:
            return room_id

    items_by_id = {item["id"]: item for item in context.get("items", [])}
    for item_id in intent.get("involved_item_ids", []):
        item = items_by_id.get(item_id)
        if item and item.get("room_id") in room_ids:
            return item["room_id"]

    start_rooms = [room["id"] for room in rooms if room.get("is_start")]
    if start_rooms:
        return start_rooms[0]
    if rooms:
        return rooms[0]["id"]
    return None


def _compile_puzzle_intents(intents: list[dict], context: dict) -> list[dict]:
    """Compile creative puzzle intents into deterministic puzzle rows."""
    compiled: list[dict] = []
    used_ids: set[str] = set()

    for intent in intents:
        room_id = _choose_puzzle_room(intent, context)
        difficulty = _normalize_difficulty(intent)
        is_optional = 1 if intent.get("progression_role") == "optional" else 0
        compiled.append(
            {
                "id": _slugify_puzzle_id(intent.get("id", "puzzle"), used_ids),
                "name": intent.get("name", "Unnamed Puzzle"),
                "description": intent.get("core_concept", ""),
                "room_id": room_id,
                "solution_steps": intent.get("solution_beats", []),
                "hint_text": _normalize_hint_progression(intent),
                "difficulty": difficulty,
                "score_value": _score_for_puzzle(difficulty, is_optional),
                "is_optional": is_optional,
                "primary_room_candidates": intent.get("primary_room_candidates", []),
                "clue_room_ids": intent.get("clue_room_ids", []),
                "involved_item_ids": intent.get("involved_item_ids", []),
                "involved_npc_ids": intent.get("involved_npc_ids", []),
                "core_concept": intent.get("core_concept", ""),
            }
        )

    return compiled


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_puzzles(puzzles: list[dict], context: dict) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors: list[str] = []
    room_ids = {r["id"] for r in context.get("rooms", [])}
    seen_ids: set[str] = set()

    for puzzle in puzzles:
        pid = puzzle.get("id", "<missing>")

        # Unique ID
        if pid in seen_ids:
            errors.append(f"Duplicate puzzle id: {pid}")
        seen_ids.add(pid)

        # Room reference
        rid = puzzle.get("room_id")
        if rid and rid not in room_ids:
            errors.append(f"Puzzle {pid} references unknown room: {rid}")

        # Required fields
        for field in ("name", "description"):
            if not puzzle.get(field):
                errors.append(f"Puzzle {pid} missing required field: {field}")

        # Solution steps
        steps = puzzle.get("solution_steps", [])
        if not steps:
            errors.append(f"Puzzle {pid} has no solution_steps")

        # Hints
        hints = puzzle.get("hint_text", [])
        if len(hints) < 2:
            errors.append(
                f"Puzzle {pid} has fewer than 2 hints ({len(hints)} provided)"
            )

        # Difficulty range
        diff = puzzle.get("difficulty", 0)
        if diff not in (1, 2, 3):
            errors.append(f"Puzzle {pid} has invalid difficulty: {diff}")

        # Score value
        score = puzzle.get("score_value", 0)
        if score <= 0:
            errors.append(f"Puzzle {pid} has non-positive score_value: {score}")

    # Check puzzle-type locks have corresponding puzzles
    locks = context.get("locks", [])
    for lock in locks:
        if lock.get("lock_type") == "puzzle":
            puzzle_id = lock.get("puzzle_id")
            if puzzle_id and puzzle_id not in seen_ids:
                errors.append(
                    f"Lock {lock['id']} references puzzle {puzzle_id} "
                    f"but no puzzle with that id was generated"
                )

    return errors


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------


def _insert_puzzles(
    db: GameDB, puzzles: list[dict], context: dict
) -> list[dict]:
    """Insert validated puzzles into the database.

    FK references (room_id) are checked against known room IDs before
    insertion.  Puzzles with invalid room references are skipped.

    Returns the list of puzzles that were successfully inserted.
    """
    room_ids = {r["id"] for r in context.get("rooms", [])}
    inserted: list[dict] = []

    for puzzle in puzzles:
        pid = puzzle.get("id", "<unknown>")

        # --- Validate room_id (NOT NULL FK) ---
        rid = puzzle.get("room_id")
        if rid not in room_ids:
            logger.warning(
                "Puzzle %s references non-existent room_id %r — "
                "skipping puzzle",
                pid,
                rid,
            )
            continue

        db.insert_puzzle(
            id=puzzle["id"],
            name=puzzle["name"],
            description=puzzle["description"],
            room_id=puzzle["room_id"],
            is_solved=0,
            solution_steps=json.dumps(puzzle.get("solution_steps", [])),
            hint_text=json.dumps(puzzle.get("hint_text", [])),
            difficulty=puzzle.get("difficulty", 1),
            score_value=puzzle.get("score_value", 0),
            is_optional=puzzle.get("is_optional", 0),
        )
        inserted.append(puzzle)

    return inserted


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_pass(db: GameDB, provider: BaseProvider, context: dict) -> dict:
    """Run Pass 6: Puzzles.  Returns updated context with compiled puzzle data."""

    logger.info("Pass 6: Generating puzzle intents...")

    prompt = _build_prompt(context)
    gen_ctx = GenerationContext(
        existing_data={},
        seed=context.get("seed"),
        temperature=0.7,
        max_tokens=32_768,
    )

    result = provider.generate_structured(prompt, PUZZLE_INTENTS_SCHEMA, gen_ctx)
    puzzle_intents: list[dict] = result.get("puzzle_intents", [])
    puzzles = _compile_puzzle_intents(puzzle_intents, context)

    # Validate
    errors = _validate_puzzles(puzzles, context)
    if errors:
        for err in errors:
            logger.warning("Puzzle validation: %s", err)

    # Insert into DB (with FK validation); returns only successfully inserted
    inserted_puzzles = _insert_puzzles(db, puzzles, context)

    # Build pass-specific data for downstream passes (only inserted puzzles)
    puzzles_summary = [
        {
            "id": p["id"],
            "name": p["name"],
            "room_id": p["room_id"],
            "difficulty": p.get("difficulty", 1),
            "score_value": p.get("score_value", 0),
            "is_optional": p.get("is_optional", 0),
            "solution_steps": p.get("solution_steps", []),
            "hint_text": p.get("hint_text", []),
            "core_concept": p.get("core_concept", ""),
            "clue_room_ids": p.get("clue_room_ids", []),
            "involved_item_ids": p.get("involved_item_ids", []),
            "involved_npc_ids": p.get("involved_npc_ids", []),
        }
        for p in inserted_puzzles
    ]

    if len(inserted_puzzles) < len(puzzles):
        logger.warning(
            "Pass 6: %d of %d puzzles skipped due to invalid FK references",
            len(puzzles) - len(inserted_puzzles),
            len(puzzles),
        )
    logger.info("Pass 6 complete: %d puzzles inserted.", len(inserted_puzzles))
    return {"puzzles": puzzles_summary}
