"""Pass 9: Quests -- Generate player-facing objectives with trackable progress.

Reads everything from prior passes, then prompts the LLM to generate
quests that organize the player's experience into clear objectives.

Every game has exactly one main quest (the win condition) and 2-4 side
quests that reward exploration. Quest objectives reference existing flags
from prior passes -- the quest system observes flag state, it never
gates actions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from anyzork.db.schema import GameDB
from anyzork.generator.providers.base import BaseProvider, GenerationContext

logger = logging.getLogger(__name__)

_MAX_GENERATION_ATTEMPTS = 3

# ---------------------------------------------------------------------------
# JSON schema the LLM must conform to
# ---------------------------------------------------------------------------

QUEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["quests", "flags"],
    "properties": {
        "quests": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "name",
                    "description",
                    "quest_type",
                    "completion_flag",
                    "score_value",
                    "sort_order",
                    "objectives",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique snake_case identifier.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Player-facing quest title.",
                    },
                    "description": {
                        "type": "string",
                        "description": "1-3 sentences describing the quest.",
                    },
                    "quest_type": {
                        "type": "string",
                        "enum": ["main", "side"],
                    },
                    "discovery_flag": {
                        "type": ["string", "null"],
                        "description": (
                            "Flag that triggers discovery. NULL = auto-discover at start."
                        ),
                    },
                    "completion_flag": {
                        "type": "string",
                        "description": "Flag set by engine when quest completes.",
                    },
                    "score_value": {
                        "type": "integer",
                        "description": "Points awarded on completion.",
                    },
                    "sort_order": {
                        "type": "integer",
                        "description": "Display order in quest log.",
                    },
                    "objectives": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": [
                                "id",
                                "description",
                                "completion_flag",
                                "order_index",
                                "is_optional",
                                "bonus_score",
                            ],
                            "properties": {
                                "id": {"type": "string"},
                                "description": {"type": "string"},
                                "completion_flag": {"type": "string"},
                                "order_index": {"type": "integer"},
                                "is_optional": {"type": "integer"},
                                "bonus_score": {"type": "integer"},
                            },
                        },
                    },
                },
            },
        },
        "flags": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "value", "description"],
                "properties": {
                    "id": {"type": "string"},
                    "value": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_prompt(context: dict) -> str:
    """Construct the LLM prompt for quest generation."""

    concept = context.get("concept", {})
    rooms = context.get("rooms", [])
    items = context.get("items", [])
    npcs = context.get("npcs", [])
    puzzles = context.get("puzzles", [])
    flags = context.get("flags", [])
    commands = context.get("commands", [])

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
            }
            for n in npcs
        ],
        indent=2,
    )

    puzzles_summary = json.dumps(
        [
            {
                "id": p["id"],
                "name": p["name"],
                "room_id": p["room_id"],
                "is_optional": p.get("is_optional", 0),
            }
            for p in puzzles
        ],
        indent=2,
    ) if puzzles else "[]"

    flags_summary = json.dumps(
        [{"id": f["id"], "description": f.get("description", "")} for f in flags],
        indent=2,
    ) if flags else "[]"

    # Summarize flag-setting effects from commands
    flag_effects: list[dict] = []
    for cmd in commands:
        effects_raw = cmd.get("effects")
        if effects_raw:
            try:
                effects = json.loads(effects_raw) if isinstance(effects_raw, str) else effects_raw
            except (json.JSONDecodeError, TypeError):
                continue
            for eff in effects:
                if eff.get("type") == "set_flag":
                    flag_effects.append({
                        "command_id": cmd.get("id", ""),
                        "flag": eff.get("flag", ""),
                    })

    flag_effects_summary = json.dumps(flag_effects, indent=2) if flag_effects else "[]"

    # Win conditions
    win_conditions = "[]"
    if "concept" in context and isinstance(context["concept"], dict):
        win_conditions = context["concept"].get("win_conditions", "[]")

    retry_guidance = ""
    last_error = context.get("_last_error")
    if last_error:
        retry_guidance = f"""

## Previous Attempt Failed
Your previous quest draft was rejected with these validation errors:
{last_error}

Fix those exact issues in this new draft.

Critical repair rules:
- Do NOT reuse an existing flag ID from the Existing Flags list.
- Quest-generated flags must be new IDs that do not conflict with any
  existing flag, quest completion flag, or objective completion flag.
- If a quest needs to reference a pre-existing state flag, reference it in
  an objective completion_flag or discovery_flag only when the schema allows
  an existing flag.
- Every new quest completion_flag must be unique.
- Every new objective completion_flag must be unique.
- Do NOT invent flags that duplicate common win-state flags like
  `game_won` unless the world already explicitly defines them as existing.
"""

    return f"""\
You are designing quests for a Zork-style text adventure. You have the
complete world from prior passes. Your job is to organize the player's
experience into clear objectives.

## World Concept
{json.dumps(concept, indent=2)}

## Rooms
{rooms_summary}

## Items
{items_summary}

## NPCs
{npcs_summary}

## Puzzles
{puzzles_summary}

## Existing Flags (from prior passes)
{flags_summary}

## Commands That Set Flags
{flag_effects_summary}

## Win Conditions
{win_conditions}
{retry_guidance}

## Your Task

### 1. Main Quest
Design exactly ONE main quest. Its objectives should map to the major
milestones on the critical path to winning.

Requirements:
- 2-5 objectives that span the critical path
- Each objective's completion_flag MUST reference an existing flag
- discovery_flag: null (auto-discovered at game start)
- score_value: 0 (the main quest IS the game)
- quest_type: "main"

### 2. Side Quests
Design 2-4 side quests. Each should:
- Use existing items, NPCs, rooms, and puzzles NOT on the critical path
- Have 1-3 objectives per quest
- Reference existing flags as objective completion_flags
- Have a clear discovery trigger (discovery_flag referencing an existing flag)
- Award 5-20 score points on completion
- quest_type: "side"

### 3. Flags
For each quest, create:
- A completion_flag (e.g., quest_<quest_id>_complete)
- A discovery_flag for side quests (referencing an existing flag)

### Output Format
```json
{{
  "quests": [
    {{
      "id": "main_quest",
      "name": "Quest Title",
      "description": "1-3 sentences.",
      "quest_type": "main",
      "discovery_flag": null,
      "completion_flag": "quest_main_complete",
      "score_value": 0,
      "sort_order": 0,
      "objectives": [
        {{
          "id": "obj_id",
          "description": "Short phrase",
          "completion_flag": "existing_flag",
          "order_index": 0,
          "is_optional": 0,
          "bonus_score": 0
        }}
      ]
    }}
  ],
  "flags": [
    {{
      "id": "quest_main_complete",
      "value": "false",
      "description": "Set by engine when all main quest objectives are complete"
    }}
  ]
}}
```
"""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_quests(quests: list[dict], flags_data: list[dict], context: dict) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors: list[str] = []

    # Build a set of all known flags (existing + new from this pass).
    existing_flags = {f["id"] for f in context.get("flags", [])}
    seen_new_flag_ids: set[str] = set()
    for flag in flags_data:
        fid = flag.get("id", "<missing>")
        if fid in seen_new_flag_ids:
            errors.append(f"Duplicate quest flag id: {fid}")
        seen_new_flag_ids.add(fid)
        if fid in existing_flags:
            errors.append(f"Quest flag id '{fid}' conflicts with an existing flag.")

    new_flags = seen_new_flag_ids
    all_flags = existing_flags | new_flags

    seen_quest_ids: set[str] = set()
    seen_obj_ids: set[str] = set()
    seen_obj_flags: set[str] = set()
    main_count = 0

    for quest in quests:
        qid = quest.get("id", "<missing>")

        if qid in seen_quest_ids:
            errors.append(f"Duplicate quest id: {qid}")
        seen_quest_ids.add(qid)

        if quest.get("quest_type") == "main":
            main_count += 1

        # Check discovery_flag.
        disc_flag = quest.get("discovery_flag")
        if disc_flag is not None and disc_flag not in all_flags:
            errors.append(f"Quest {qid} discovery_flag '{disc_flag}' not in flags.")

        # Check completion_flag.
        comp_flag = quest.get("completion_flag")
        if comp_flag and comp_flag not in all_flags:
            errors.append(f"Quest {qid} completion_flag '{comp_flag}' not in flags.")

        objectives = quest.get("objectives", [])
        has_required = False
        for obj in objectives:
            oid = obj.get("id", "<missing>")
            if oid in seen_obj_ids:
                errors.append(f"Duplicate objective id: {oid}")
            seen_obj_ids.add(oid)

            obj_flag = obj.get("completion_flag", "")
            if obj_flag in seen_obj_flags:
                errors.append(
                    f"Objective {oid} completion_flag '{obj_flag}' is used by another objective."
                )
            seen_obj_flags.add(obj_flag)

            if obj_flag and obj_flag not in all_flags:
                errors.append(
                    f"Objective {oid} completion_flag '{obj_flag}' not in flags."
                )

            if not obj.get("is_optional"):
                has_required = True

        if not has_required:
            errors.append(f"Quest {qid} has no required (non-optional) objectives.")

    if main_count != 1:
        errors.append(f"Expected exactly 1 main quest, found {main_count}.")

    return errors


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------


def _insert_quests(db: GameDB, quests: list[dict], flags_data: list[dict]) -> None:
    """Insert validated quests, objectives, and flags into the database."""

    # Insert new flags first.
    for flag in flags_data:
        db.insert_flag(
            id=flag["id"],
            value=flag.get("value", "false"),
            description=flag.get("description", ""),
        )

    # Insert quests and objectives.
    for quest in quests:
        db.insert_quest(
            id=quest["id"],
            name=quest["name"],
            description=quest["description"],
            quest_type=quest["quest_type"],
            status="undiscovered",
            discovery_flag=quest.get("discovery_flag"),
            completion_flag=quest["completion_flag"],
            score_value=quest.get("score_value", 0),
            sort_order=quest.get("sort_order", 0),
        )

        for obj in quest.get("objectives", []):
            db.insert_quest_objective(
                id=obj["id"],
                quest_id=quest["id"],
                description=obj["description"],
                completion_flag=obj["completion_flag"],
                order_index=obj.get("order_index", 0),
                is_optional=obj.get("is_optional", 0),
                bonus_score=obj.get("bonus_score", 0),
            )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_pass(db: GameDB, provider: BaseProvider, context: dict) -> dict:
    """Run Pass 8: Quests.  Returns updated context with quest data."""

    logger.info("Pass 8: Generating quests...")

    result: dict[str, Any] = {}
    quests: list[dict] = []
    flags_data: list[dict] = []
    errors: list[str] = []

    for attempt in range(1, _MAX_GENERATION_ATTEMPTS + 1):
        prompt = _build_prompt(context)
        gen_ctx = GenerationContext(
            existing_data={},
            seed=context.get("seed"),
            temperature=0.8,
            max_tokens=16_384,
        )

        result = provider.generate_structured(prompt, QUEST_SCHEMA, gen_ctx)
        quests = result.get("quests", [])
        flags_data = result.get("flags", [])

        errors = _validate_quests(quests, flags_data, context)
        if not errors:
            break

        preview = "; ".join(errors[:8])
        logger.warning(
            "Pass 8 validation failed (attempt %d/%d): %s",
            attempt,
            _MAX_GENERATION_ATTEMPTS,
            preview,
        )
        if attempt == _MAX_GENERATION_ATTEMPTS:
            raise ValueError(f"Quest validation failed: {preview}")
        context["_last_error"] = preview

    context.pop("_last_error", None)

    # Insert into DB.
    _insert_quests(db, quests, flags_data)

    main_quests = [q for q in quests if q.get("quest_type") == "main"]
    if len(main_quests) == 1 and main_quests[0].get("completion_flag"):
        db.set_meta(
            "win_conditions",
            json.dumps([main_quests[0]["completion_flag"]]),
        )

    # Build pass-specific data for downstream consumers.
    quest_summary = [
        {
            "id": q["id"],
            "name": q["name"],
            "quest_type": q["quest_type"],
            "completion_flag": q["completion_flag"],
            "score_value": q.get("score_value", 0),
        }
        for q in quests
    ]

    main_count = sum(1 for q in quests if q.get("quest_type") == "main")
    side_count = sum(1 for q in quests if q.get("quest_type") == "side")

    logger.info(
        "Pass 8 complete: %d quests generated (main=%d, side=%d).",
        len(quests),
        main_count,
        side_count,
    )
    return {"quests": quest_summary, "flags": flags_data}
