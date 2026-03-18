"""Pass 5: NPCs — Populate the world with non-player characters.

Reads the world concept, rooms, items, and locks from prior passes, then
prompts the LLM to generate NPCs and their dialogue entries.

NPCs serve five roles:

  * **Quest givers** — provide information, tasks, or items.
  * **Gatekeepers** — block exits until a condition is met.
  * **Merchants / traders** — exchange items with the player.
  * **Lore sources** — deliver world-building through dialogue.
  * **Hostile NPCs** — must be dealt with (combat, diplomacy, stealth).

Every NPC has a consistent voice defined by vocabulary, sentence rhythm, and
personality.  Dialogue lines must pass the "would a real person say this?"
test — no exposition disguised as conversation, no "as you know" speeches.

Dialogue entries are flag-gated: the engine selects the highest-priority
matching entry whose ``required_flags`` are all satisfied.
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

NPCS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["npcs"],
    "properties": {
        "npcs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "name",
                    "description",
                    "examine_description",
                    "room_id",
                    "default_dialogue",
                    "dialogue_entries",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique snake_case identifier.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Display name shown to the player.",
                    },
                    "description": {
                        "type": "string",
                        "description": "1-2 sentence description shown when NPC is in a room.",
                    },
                    "examine_description": {
                        "type": "string",
                        "description": "2-4 sentence detailed description on examination.",
                    },
                    "room_id": {
                        "type": "string",
                        "description": "Room ID where this NPC is located.",
                    },
                    "default_dialogue": {
                        "type": "string",
                        "description": "Fallback dialogue when no specific entry matches.",
                    },
                    "is_blocking": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "1 = blocks an exit until a condition is met.",
                    },
                    "blocked_exit_id": {
                        "type": ["string", "null"],
                        "description": "Exit ID this NPC blocks (if is_blocking = 1).",
                    },
                    "unblock_flag": {
                        "type": ["string", "null"],
                        "description": "Flag that must be set to unblock the exit.",
                    },
                    "hp": {
                        "type": ["integer", "null"],
                        "description": "Hit points for combat NPCs, null for non-combatants.",
                    },
                    "damage": {
                        "type": ["integer", "null"],
                        "description": "Damage per attack for combat NPCs, null for non-combatants.",
                    },
                    "dialogue_entries": {
                        "type": "array",
                        "description": "Array of dialogue entries for this NPC.",
                        "items": {
                            "type": "object",
                            "required": ["id", "content", "priority"],
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "Unique snake_case identifier for this dialogue.",
                                },
                                "topic": {
                                    "type": ["string", "null"],
                                    "description": (
                                        "Keyword for 'ask NPC about TOPIC'. "
                                        "null = general 'talk to' response."
                                    ),
                                },
                                "content": {
                                    "type": "string",
                                    "description": "The dialogue text shown to the player.",
                                },
                                "required_flags": {
                                    "type": ["array", "null"],
                                    "items": {"type": "string"},
                                    "description": "Flags that must be set for this line to appear.",
                                },
                                "set_flags": {
                                    "type": ["array", "null"],
                                    "items": {"type": "string"},
                                    "description": "Flags to set when this dialogue is delivered.",
                                },
                                "priority": {
                                    "type": "integer",
                                    "description": "Higher priority wins when multiple entries match.",
                                },
                            },
                        },
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
    """Construct the LLM prompt for NPC generation."""

    concept = context.get("concept", {})
    rooms = context.get("rooms", [])
    items = context.get("items", [])
    locks = context.get("locks", [])
    exits = context.get("exits", [])

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

    exits_summary = json.dumps(
        [
            {
                "id": e["id"],
                "from_room_id": e.get("from_room_id"),
                "to_room_id": e.get("to_room_id"),
                "direction": e.get("direction"),
            }
            for e in exits
        ],
        indent=2,
    ) if exits else "[]"

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

    locks_summary = json.dumps(locks, indent=2) if locks else "[]"

    return f"""\
You are a narrative designer creating NPCs for a Zork-style text adventure.

## World Concept
{json.dumps(concept, indent=2)}

## Existing Rooms
{rooms_summary}

## Existing Exits
{exits_summary}

## Existing Items
{items_summary}

## Existing Locks
{locks_summary}

## Your Task — Generate NPCs and Dialogue

Create NPCs that serve clear narrative and mechanical purposes.  Every NPC
must contribute: gate progress, provide a useful item, deliver critical
information, or present a meaningful interaction.  No NPCs exist as empty
decoration.

### NPC Types

1. **Quest Givers** — Provide information, tasks, or items in exchange for
   player actions.  Place on or near the critical path.

2. **Gatekeepers** — Block passage until a condition is met (e.g., a guard
   who wants a bribe or proof of authority).  These correspond to NPC-type
   locks from the locks data.  Set `is_blocking: 1`, provide the
   `blocked_exit_id` and `unblock_flag`.

3. **Lore Sources** — Exist primarily to deliver world-building through
   dialogue.  Place in optional areas as exploration rewards.

4. **Merchants / Traders** — Exchange items with the player.  Optional but
   adds depth.

5. **Hostile NPCs** — Must be dealt with through combat, stealth, or
   diplomacy.  Telegraph danger in the room description.

### Dialogue Design Rules

Each NPC has dialogue entries — individual lines gated by game-state flags.

- **`topic: null`** entries are "talk to NPC" responses.  The engine picks the
  highest-priority entry whose `required_flags` are all satisfied.
- **`topic: "keyword"`** entries respond to "ask NPC about keyword".

**Voice consistency**: Each NPC must have a distinct voice.  A grizzled guard
speaks differently from a nervous scholar.  Define the character's vocabulary,
rhythm, and personality, then write every line through that lens.

**No exposition dumps**: Characters never explain things to each other (or the
player) that they would already know.  Information is delivered naturally
through the character's perspective and priorities.

**Flag chains**: Dialogue can set flags that unlock further dialogue, new
information, and puzzle progression.  Design dialogue trees where talking to
an NPC early unlocks new topics or changes responses later.

**Default dialogue**: The `default_dialogue` field is the catch-all — what the
NPC says when no specific dialogue entry matches.  It should feel natural for
repeated use.

### CRITICAL: Use Exact IDs

You MUST use the exact `id` values from the existing data above. Do NOT
invent room IDs or exit IDs — copy them verbatim from the lists above.
If `room_id` does not exactly match one of the room IDs listed in
"Existing Rooms", the NPC will fail to insert. If `blocked_exit_id` does
not exactly match an exit ID from "Existing Exits", it will be dropped.

### Placement Rules

- Spread NPCs across regions.  Do not cluster.
- Critical-path NPCs must be in rooms the player must pass through.
- Optional NPCs go in optional areas, rewarding exploration.
- Hostile NPCs should be telegraphed — the room description hints at danger.
- Scale: aim for approximately one NPC per 3-5 rooms.

### Output Format

Return a JSON object:

```json
{{
  "npcs": [
    {{
      "id": "snake_case_id",
      "name": "Display Name",
      "description": "1-2 sentences, shown when NPC is in room",
      "examine_description": "2-4 sentences on examination",
      "room_id": "room_id_where_npc_lives",
      "default_dialogue": "Fallback line for talk-to",
      "is_blocking": 0 or 1,
      "blocked_exit_id": "exit_id or null",
      "unblock_flag": "flag_name or null",
      "hp": null or integer,
      "damage": null or integer,
      "dialogue_entries": [
        {{
          "id": "unique_dialogue_id",
          "topic": "keyword or null",
          "content": "What the NPC says",
          "required_flags": ["flag1", "flag2"] or null,
          "set_flags": ["flag_to_set"] or null,
          "priority": 0
        }}
      ]
    }}
  ]
}}
```

Each dialogue `id` must be globally unique across all NPCs.
"""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_npcs(npcs: list[dict], context: dict) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors: list[str] = []
    room_ids = {r["id"] for r in context.get("rooms", [])}
    exit_ids = {e["id"] for e in context.get("exits", [])}

    seen_npc_ids: set[str] = set()
    seen_dialogue_ids: set[str] = set()

    for npc in npcs:
        nid = npc.get("id", "<missing>")

        # Unique NPC ID
        if nid in seen_npc_ids:
            errors.append(f"Duplicate NPC id: {nid}")
        seen_npc_ids.add(nid)

        # Room reference
        rid = npc.get("room_id")
        if rid and rid not in room_ids:
            errors.append(f"NPC {nid} references unknown room: {rid}")

        # Required fields
        for field in ("name", "description", "examine_description", "default_dialogue"):
            if not npc.get(field):
                errors.append(f"NPC {nid} missing required field: {field}")

        # Blocking NPC consistency
        if npc.get("is_blocking") == 1:
            if not npc.get("blocked_exit_id"):
                errors.append(
                    f"Blocking NPC {nid} has is_blocking=1 but no blocked_exit_id"
                )
            if not npc.get("unblock_flag"):
                errors.append(
                    f"Blocking NPC {nid} has is_blocking=1 but no unblock_flag"
                )

        # Dialogue entries
        entries = npc.get("dialogue_entries", [])
        if not entries:
            errors.append(f"NPC {nid} has no dialogue entries")

        for entry in entries:
            did = entry.get("id", "<missing>")
            if did in seen_dialogue_ids:
                errors.append(f"Duplicate dialogue id: {did}")
            seen_dialogue_ids.add(did)

            if not entry.get("content"):
                errors.append(f"Dialogue {did} has empty content")

    return errors


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------


def _insert_npcs(
    db: GameDB, npcs: list[dict], context: dict
) -> list[dict]:
    """Insert validated NPCs and their dialogue into the database.

    FK references (room_id, blocked_exit_id) are checked against the
    database before insertion.  Invalid references are nullified (if
    nullable) or cause the NPC to be skipped (if NOT NULL), with a
    logged warning.

    Returns the list of NPCs that were successfully inserted.
    """
    room_ids = {r["id"] for r in context.get("rooms", [])}
    exit_ids = {e["id"] for e in context.get("exits", [])}
    inserted: list[dict] = []

    for npc in npcs:
        nid = npc.get("id", "<unknown>")

        # --- Validate room_id (NOT NULL FK) ---
        rid = npc.get("room_id")
        if rid not in room_ids:
            logger.warning(
                "NPC %s references non-existent room_id %r — skipping NPC",
                nid,
                rid,
            )
            continue

        # --- Validate blocked_exit_id (nullable FK) ---
        blocked_exit = npc.get("blocked_exit_id")
        if blocked_exit is not None and blocked_exit not in exit_ids:
            logger.warning(
                "NPC %s references non-existent blocked_exit_id %r — "
                "setting to NULL",
                nid,
                blocked_exit,
            )
            npc["blocked_exit_id"] = None
            # If is_blocking was set but exit is invalid, clear blocking
            if npc.get("is_blocking") == 1:
                logger.warning(
                    "NPC %s had is_blocking=1 with invalid exit — "
                    "setting is_blocking=0",
                    nid,
                )
                npc["is_blocking"] = 0

        # Insert NPC row
        db.insert_npc(
            id=npc["id"],
            name=npc["name"],
            description=npc["description"],
            examine_description=npc["examine_description"],
            room_id=npc["room_id"],
            is_alive=1,
            is_blocking=npc.get("is_blocking", 0),
            blocked_exit_id=npc.get("blocked_exit_id"),
            unblock_flag=npc.get("unblock_flag"),
            default_dialogue=npc["default_dialogue"],
            hp=npc.get("hp"),
            damage=npc.get("damage"),
        )
        inserted.append(npc)

        # Insert dialogue entries
        for entry in npc.get("dialogue_entries", []):
            required_flags = entry.get("required_flags")
            set_flags = entry.get("set_flags")

            db.insert_dialogue(
                id=entry["id"],
                npc_id=npc["id"],
                topic=entry.get("topic"),
                content=entry["content"],
                required_flags=(
                    json.dumps(required_flags) if required_flags else None
                ),
                set_flags=json.dumps(set_flags) if set_flags else None,
                priority=entry.get("priority", 0),
            )

    return inserted


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_pass(db: GameDB, provider: BaseProvider, context: dict) -> dict:
    """Run Pass 5: NPCs.  Returns updated context with NPC data."""

    logger.info("Pass 5: Generating NPCs...")

    prompt = _build_prompt(context)
    gen_ctx = GenerationContext(
        existing_data={},
        seed=context.get("seed"),
        temperature=0.7,
        max_tokens=32_768,
    )

    result = provider.generate_structured(prompt, NPCS_SCHEMA, gen_ctx)
    npcs: list[dict] = result.get("npcs", [])

    # Validate
    errors = _validate_npcs(npcs, context)
    if errors:
        for err in errors:
            logger.warning("NPC validation: %s", err)

    # Insert into DB (with FK validation); returns only successfully inserted
    inserted_npcs = _insert_npcs(db, npcs, context)

    # Build pass-specific data for downstream passes (only inserted NPCs)
    npcs_summary = [
        {
            "id": n["id"],
            "name": n["name"],
            "room_id": n["room_id"],
            "is_blocking": n.get("is_blocking", 0),
            "blocked_exit_id": n.get("blocked_exit_id"),
            "unblock_flag": n.get("unblock_flag"),
            "dialogue_topics": [
                e.get("topic")
                for e in n.get("dialogue_entries", [])
                if e.get("topic")
            ],
        }
        for n in inserted_npcs
    ]

    if len(inserted_npcs) < len(npcs):
        logger.warning(
            "Pass 5: %d of %d NPCs skipped due to invalid FK references",
            len(npcs) - len(inserted_npcs),
            len(npcs),
        )
    logger.info("Pass 5 complete: %d NPCs inserted.", len(inserted_npcs))
    return {"npcs": npcs_summary}
