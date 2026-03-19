"""Pass 10: Triggers -- Generate reactive events that fire on game state changes.

Runs after quests and before validation. Reads everything from
prior passes -- rooms, items, NPCs, dialogue nodes, flags, locks, exits,
puzzles, commands, and quests -- then prompts the LLM to generate triggers
that wire reactive game behavior.

Triggers are NOT player-initiated commands.  They fire automatically when
a game event occurs (player enters a room, a flag is set, a dialogue node
is reached, an item is picked up or dropped).  They use the same
precondition/effect system as DSL commands.

This pass is separate from commands because the mental models differ:
commands answer "what can the player do?" while triggers answer "what
happens reactively?"  Keeping them separate produces better results from
the LLM and avoids conflating the two systems.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from anyzork.db.schema import GameDB
from anyzork.generator.providers.base import BaseProvider, GenerationContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid precondition and effect types (must match engine/commands.py)
# ---------------------------------------------------------------------------

VALID_PRECONDITION_TYPES = {
    "in_room",
    "has_item",
    "has_flag",
    "not_flag",
    "item_in_room",
    "npc_in_room",
    "lock_unlocked",
    "puzzle_solved",
    "health_above",
    "container_open",
    "item_in_container",
    "not_item_in_container",
    "container_has_contents",
    "container_empty",
    "has_quantity",
}

VALID_EFFECT_TYPES = {
    "move_item",
    "remove_item",
    "set_flag",
    "unlock",
    "move_player",
    "spawn_item",
    "change_health",
    "add_score",
    "reveal_exit",
    "solve_puzzle",
    "discover_quest",
    "print",
    "open_container",
    "move_item_to_container",
    "take_item_from_container",
    "consume_quantity",
    "restore_quantity",
    "set_toggle_state",
}

VALID_EVENT_TYPES = {
    "room_enter",
    "flag_set",
    "dialogue_node",
    "item_taken",
    "item_dropped",
}

# ---------------------------------------------------------------------------
# JSON schema the LLM must conform to
# ---------------------------------------------------------------------------

TRIGGERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["triggers"],
    "properties": {
        "triggers": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "event_type",
                    "event_data",
                    "preconditions",
                    "effects",
                    "message",
                    "priority",
                    "one_shot",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": (
                            "Unique snake_case identifier.  Convention: "
                            "trigger_{event_type}_{description}."
                        ),
                    },
                    "event_type": {
                        "type": "string",
                        "enum": [
                            "room_enter",
                            "flag_set",
                            "dialogue_node",
                            "item_taken",
                            "item_dropped",
                        ],
                        "description": "The game event that fires this trigger.",
                    },
                    "event_data": {
                        "type": "object",
                        "description": (
                            "Event-specific match criteria.  Keys depend on "
                            "event_type.  Empty {} matches any event of that type."
                        ),
                    },
                    "preconditions": {
                        "type": "array",
                        "description": (
                            "Array of precondition objects.  ALL must be true.  "
                            "Same types as DSL commands."
                        ),
                        "items": {
                            "type": "object",
                            "required": ["type"],
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": sorted(VALID_PRECONDITION_TYPES),
                                },
                            },
                        },
                    },
                    "effects": {
                        "type": "array",
                        "description": (
                            "Ordered array of effect objects.  Same types as "
                            "DSL commands.  Must contain at least one effect."
                        ),
                        "items": {
                            "type": "object",
                            "required": ["type"],
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": sorted(VALID_EFFECT_TYPES),
                                },
                            },
                        },
                    },
                    "message": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional text displayed when the trigger fires, "
                            "before effects run.  null = no message."
                        ),
                    },
                    "priority": {
                        "type": "integer",
                        "description": (
                            "Evaluation order.  Higher = evaluated first.  "
                            "Puzzle-critical: 10-99.  Atmospheric: 0.  Default: 0."
                        ),
                    },
                    "one_shot": {
                        "type": "boolean",
                        "description": (
                            "true = fires only once ever.  "
                            "false = fires every time the event occurs."
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
    """Construct the LLM prompt for trigger generation."""

    concept = context.get("concept", {})
    rooms = context.get("rooms", [])
    items = context.get("items", [])
    npcs = context.get("npcs", [])
    locks = context.get("locks", [])
    exits = context.get("exits", [])
    puzzles = context.get("puzzles", [])
    flags = context.get("flags", [])
    commands = context.get("commands", [])
    quests = context.get("quests", [])
    dialogue_nodes = context.get("dialogue_nodes", [])
    realism = context.get("realism", "medium")

    rooms_summary = json.dumps(
        [{"id": r["id"], "name": r["name"], "region": r.get("region")} for r in rooms],
        indent=2,
    )

    items_summary = json.dumps(
        [
            {
                "id": i["id"],
                "name": i["name"],
                "room_id": i.get("room_id"),
                "item_tags": i.get("item_tags"),
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
                "room_id": n.get("room_id"),
            }
            for n in npcs
        ],
        indent=2,
    )

    dialogue_summary = json.dumps(
        [
            {
                "id": d["id"],
                "npc_id": d["npc_id"],
                "content_preview": d.get("content", "")[:80],
                "set_flags": d.get("set_flags"),
                "is_root": d.get("is_root", 0),
            }
            for d in dialogue_nodes
        ],
        indent=2,
    ) if dialogue_nodes else "[]"

    locks_summary = json.dumps(
        [
            {
                "id": lk["id"],
                "target_exit_id": lk.get("target_exit_id"),
                "is_locked": lk.get("is_locked", 1),
            }
            for lk in locks
        ],
        indent=2,
    ) if locks else "[]"

    exits_summary = json.dumps(
        [
            {
                "id": e["id"],
                "from_room_id": e.get("from_room_id"),
                "to_room_id": e.get("to_room_id"),
                "direction": e.get("direction"),
                "is_locked": e.get("is_locked", 0),
                "is_hidden": e.get("is_hidden", 0),
            }
            for e in exits
        ],
        indent=2,
    ) if exits else "[]"

    puzzles_summary = json.dumps(
        [
            {
                "id": p["id"],
                "name": p["name"],
                "room_id": p.get("room_id"),
            }
            for p in puzzles
        ],
        indent=2,
    ) if puzzles else "[]"

    flags_summary = json.dumps(
        [{"id": f["id"], "description": f.get("description", "")} for f in flags],
        indent=2,
    ) if flags else "[]"

    commands_summary = json.dumps(
        [
            {
                "id": c["id"],
                "verb": c.get("verb"),
                "pattern": c.get("pattern"),
                "one_shot": c.get("one_shot", 0),
            }
            for c in commands
        ],
        indent=2,
    ) if commands else "[]"

    quests_summary = json.dumps(quests, indent=2) if quests else "[]"

    return f"""\
You are designing triggers for a Zork-style text adventure engine.
Triggers are reactive events that fire automatically when game state
changes -- NOT when the player types a command.  They use the same
precondition/effect system as DSL commands.

## World Concept
{json.dumps(concept, indent=2)}

## Rooms
{rooms_summary}

## Exits
{exits_summary}

## Items
{items_summary}

## NPCs
{npcs_summary}

## Dialogue Nodes
{dialogue_summary}

## Locks
{locks_summary}

## Puzzles
{puzzles_summary}

## Existing Flags (from prior passes)
{flags_summary}

## Existing Commands (from prior passes)
{commands_summary}

## Quests
{quests_summary}

## What Triggers Are

A trigger is a stored rule:
> When [event] occurs AND [preconditions] are met, execute [effects].

Triggers fire when a **game event** occurs, not when the player types
input.  They are deterministic -- stored in the database, evaluated at
runtime using the same precondition/effect machinery as DSL commands.

## Event Types

### `room_enter` -- player enters a room
`event_data: {{"room_id": "room_id_here"}}`

Use for:
- NPC greetings or challenges when the player enters a room
- Traps that fire when the player walks in
- Atmospheric messages on room entry (beyond first_visit_text)
- Ambushes: enemies appear, health decreases
- Flag-gated entry text: "Now that you have the amulet, the statues glow"

### `flag_set` -- a flag becomes true
`event_data: {{"flag": "flag_name_here"}}`

Use for:
- Cascading unlocks: both keys used -> door opens
- Rewards after quest flags are set
- Multi-step state changes: setting final flag triggers result
- NPC reactions to quest progress

### `dialogue_node` -- a dialogue node is displayed
`event_data: {{"node_id": "node_id_here"}}`

Use for:
- NPC gives the player an item during dialogue (spawn_item)
- Dialogue causes world changes (unlock, reveal_exit)
- NPC spawns something in another room as a reward

**IMPORTANT**: Every dialogue node where the narrative implies the NPC
gives, trades, reveals, or changes something in the world MUST have a
corresponding trigger.  Without it, the dialogue is just text with no
mechanical effect.

### `item_taken` -- player picks up an item
`event_data: {{"item_id": "item_id_here"}}`

Use for:
- Cursed items that damage the player
- Traps triggered by removing items from pedestals
- NPC reactions: "Hey, put that back!"
- Taking the last item reveals something hidden

### `item_dropped` -- player drops an item in a room
`event_data: {{"item_id": "item_id_here", "room_id": "room_id_here"}}`

Use for:
- Altar offerings: dropping the right item in the right room activates it
- Placement puzzles: dropping an item in a specific location
- NPC reactions to items left near them

## Precondition Types Reference

| Type | Required Fields | Description |
|------|----------------|-------------|
| `in_room` | `room` | Player is in this room |
| `has_item` | `item` | Player has item in inventory |
| `has_flag` | `flag` | World flag is set (truthy) |
| `not_flag` | `flag` | World flag is NOT set |
| `item_in_room` | `item`, `room` | Item exists in room |
| `npc_in_room` | `npc`, `room` | NPC is in room |
| `lock_unlocked` | `lock` | Lock is unlocked |
| `puzzle_solved` | `puzzle` | Puzzle is solved |
| `health_above` | `threshold` | Player health > threshold |
| `container_open` | `container` | Container is open |
| `item_in_container` | `item`, `container` | Item is inside container |
| `not_item_in_container` | `item`, `container` | Item is NOT inside container |
| `container_has_contents` | `container` | Container is non-empty |
| `container_empty` | `container` | Container is empty |
| `has_quantity` | `item`, `min` | Item has at least `min` quantity |

## Effect Types Reference

| Type | Required Fields | Description |
|------|----------------|-------------|
| `move_item` | `item`, `from`, `to` | Move item between locations |
| `remove_item` | `item` | Permanently destroy item |
| `set_flag` | `flag` | Set a world flag |
| `unlock` | `lock` | Unlock a lock |
| `move_player` | `room` | Teleport player to room |
| `spawn_item` | `item`, `location` | Place a hidden item into the world. `"_inventory"` = player inventory |
| `change_health` | `amount` | Modify HP (positive heals, negative damages) |
| `add_score` | `points` | Add score points |
| `reveal_exit` | `exit` | Make hidden exit visible |
| `solve_puzzle` | `puzzle` | Mark puzzle as solved |
| `discover_quest` | `quest` | Set quest discovery flag |
| `print` | `message` | Display text to the player |
| `open_container` | `container` | Open a container |
| `move_item_to_container` | `item`, `container` | Move item into container |
| `take_item_from_container` | `item`, `container` | Remove item from container |
| `consume_quantity` | `item`, `amount` | Reduce item quantity |
| `restore_quantity` | `item`, `amount` | Increase item quantity |
| `set_toggle_state` | `item`, `state` | Set item toggle state |

## Guidelines

1. **Dialogue side effects are critical.**  For every dialogue node where
   an NPC gives, trades, reveals, or changes something, generate a
   `dialogue_node` trigger with the appropriate effects (spawn_item,
   unlock, reveal_exit, etc.).  Without triggers, dialogue is just text.

2. **Flag cascades.**  When multiple flags must be set before something
   happens (e.g., two keys collected -> door opens), generate `flag_set`
   triggers that check the other prerequisite flags as preconditions.
   Use one trigger per watched flag so both orderings work.

3. **Room entry events.**  Important rooms should have `room_enter`
   triggers for atmosphere or NPC reactions.  Use `one_shot: true` for
   events that happen once (traps, ambushes) and `one_shot: false` for
   recurring reactions (NPC greets player every time).

4. **Cursed/special items.**  Items that should cause effects when picked
   up need `item_taken` triggers.

5. **Placement puzzles.**  Items that must be dropped in specific rooms
   need `item_dropped` triggers.

6. **One-shot vs repeating.**
   - `one_shot: true` -- traps, item gifts, puzzle rewards, first-time events
   - `one_shot: false` -- NPC greetings, atmospheric text, recurring checks

7. **Use preconditions for safety.**  A greeting trigger should check
   `not_flag: guard_greeted` to avoid repeating.  A trap should check
   `not_flag: trap_sprung`.  Belt-and-suspenders with one_shot.

8. **Priority conventions.**
   - 100+ -- safety/override triggers
   - 10-99 -- puzzle-critical (unlock door, spawn key item)
   - 0 -- atmospheric/flavor (NPC comments, ambient text)
   - negative -- low-priority cleanup

9. **Keep messages concise.**  Trigger messages appear inline with other
   game text.  1-3 sentences max.

## What NOT to Generate

- **Do NOT duplicate DSL commands.**  Triggers are for reactive events,
  not player actions.  If a command already handles an interaction, do
  not create a trigger for the same thing.

- **Do NOT create triggers for quest completion notifications.**  The
  quest system handles those in `_check_quests()`.

- **Do NOT reference IDs that don't exist.**  Use ONLY the exact IDs
  from the data above.

## Realism Level: {realism}

- Low: triggers are sparse, only critical path wiring
- Medium: triggers for critical path + atmospheric room entries + NPC reactions
- High: comprehensive triggers including traps, item reactions, cascading effects

## CRITICAL: Use Exact IDs

You MUST use the exact `id` values from the data above.  Do NOT invent
room, item, NPC, lock, exit, puzzle, flag, or dialogue node IDs.  Copy
them verbatim from the lists.

## Examples

### Dialogue gives player an item
```json
{{
  "id": "trigger_dialogue_blacksmith_gives_key",
  "event_type": "dialogue_node",
  "event_data": {{"node_id": "blacksmith_forges_key"}},
  "preconditions": [],
  "effects": [
    {{"type": "spawn_item", "item": "forged_key", "location": "_inventory"}},
    {{"type": "add_score", "points": 5}}
  ],
  "message": "[You receive a heavy iron key, still warm from the forge.]",
  "priority": 10,
  "one_shot": true
}}
```

### Room entry triggers NPC greeting (one-shot)
```json
{{
  "id": "trigger_room_enter_guard_challenge",
  "event_type": "room_enter",
  "event_data": {{"room_id": "guard_post"}},
  "preconditions": [
    {{"type": "not_flag", "flag": "guard_challenged"}},
    {{"type": "npc_in_room", "npc": "stern_guard", "room": "guard_post"}}
  ],
  "effects": [
    {{"type": "set_flag", "flag": "guard_challenged"}},
    {{"type": "print", "message": "The guard steps forward. \\"State your business, stranger.\\""}}
  ],
  "message": null,
  "priority": 0,
  "one_shot": true
}}
```

### Both flags set -> door unlocks (two symmetric triggers)
```json
{{
  "id": "trigger_flag_p226_qualifies_range",
  "event_type": "flag_set",
  "event_data": {{"flag": "p226_qualified"}},
  "preconditions": [{{"type": "has_flag", "flag": "ar15_qualified"}}],
  "effects": [
    {{"type": "unlock", "lock": "range_office_lock"}},
    {{"type": "print", "message": "Both qualifications complete. The range office door unlocks."}}
  ],
  "message": null,
  "priority": 10,
  "one_shot": true
}}
```

### Picking up cursed item triggers trap
```json
{{
  "id": "trigger_item_taken_idol_curse",
  "event_type": "item_taken",
  "event_data": {{"item_id": "ancient_idol"}},
  "preconditions": [{{"type": "in_room", "room": "hidden_shrine"}}],
  "effects": [
    {{"type": "change_health", "amount": -20}},
    {{"type": "set_flag", "flag": "shrine_collapsed"}},
    {{"type": "print", "message": "The ground shakes. Stones crash down from the ceiling."}}
  ],
  "message": null,
  "priority": 10,
  "one_shot": true
}}
```

### Dropping offering on altar
```json
{{
  "id": "trigger_item_dropped_offering_altar",
  "event_type": "item_dropped",
  "event_data": {{"item_id": "golden_offering", "room_id": "ancient_shrine"}},
  "preconditions": [{{"type": "not_flag", "flag": "shrine_activated"}}],
  "effects": [
    {{"type": "set_flag", "flag": "shrine_activated"}},
    {{"type": "reveal_exit", "exit": "shrine_to_inner_sanctum"}},
    {{"type": "add_score", "points": 20}}
  ],
  "message": "As the offering touches the altar, the shrine comes alive.",
  "priority": 10,
  "one_shot": true
}}
```

## Output Format

```json
{{
  "triggers": [
    {{
      "id": "trigger_...",
      "event_type": "room_enter|flag_set|dialogue_node|item_taken|item_dropped",
      "event_data": {{}},
      "preconditions": [],
      "effects": [],
      "message": "string or null",
      "priority": 0,
      "one_shot": true
    }}
  ]
}}
```

Generate triggers for ALL reactive events this world needs.  Focus on:
1. Dialogue nodes that imply world changes (most important)
2. Flag cascades for multi-step unlocks
3. Room entry events for important rooms
4. Item reactions for special/cursed items
5. Placement puzzles

Be thorough -- a missing trigger means a dialogue promise goes unfulfilled
or a cascade fails to fire.
"""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_triggers(triggers: list[dict], context: dict) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors: list[str] = []

    room_ids = {r["id"] for r in context.get("rooms", [])}
    item_ids = {i["id"] for i in context.get("items", [])}
    npc_ids = {n["id"] for n in context.get("npcs", [])}
    lock_ids = {lk["id"] for lk in context.get("locks", [])}
    puzzle_ids = {p["id"] for p in context.get("puzzles", [])}
    dialogue_node_ids = {d["id"] for d in context.get("dialogue_nodes", [])}
    flag_ids = {f["id"] for f in context.get("flags", [])}

    seen_ids: set[str] = set()

    for trigger in triggers:
        tid = trigger.get("id", "<missing>")

        # Unique ID
        if tid in seen_ids:
            errors.append(f"Duplicate trigger id: {tid}")
        seen_ids.add(tid)

        # Event type
        event_type = trigger.get("event_type", "")
        if event_type not in VALID_EVENT_TYPES:
            errors.append(f"Trigger {tid} has invalid event_type: {event_type}")

        # Event data validation
        event_data = trigger.get("event_data", {})
        if not isinstance(event_data, dict):
            errors.append(f"Trigger {tid} event_data must be a JSON object")
        else:
            if event_type == "room_enter":
                room_id = event_data.get("room_id")
                if room_id and room_id not in room_ids:
                    errors.append(
                        f"Trigger {tid} references unknown room in event_data: {room_id}"
                    )
            elif event_type == "item_taken":
                item_id = event_data.get("item_id")
                if item_id and item_id not in item_ids:
                    errors.append(
                        f"Trigger {tid} references unknown item in event_data: {item_id}"
                    )
            elif event_type == "item_dropped":
                item_id = event_data.get("item_id")
                if item_id and item_id not in item_ids:
                    errors.append(
                        f"Trigger {tid} references unknown item in event_data: {item_id}"
                    )
                room_id = event_data.get("room_id")
                if room_id and room_id not in room_ids:
                    errors.append(
                        f"Trigger {tid} references unknown room in event_data: {room_id}"
                    )
            elif event_type == "dialogue_node":
                node_id = event_data.get("node_id")
                if node_id and node_id not in dialogue_node_ids:
                    errors.append(
                        f"Trigger {tid} references unknown dialogue node in "
                        f"event_data: {node_id}"
                    )
            elif event_type == "flag_set":
                flag = event_data.get("flag")
                if flag and flag not in flag_ids:
                    # Flag references are soft warnings, not hard errors,
                    # because triggers may reference flags set by other
                    # triggers or by commands not yet visible in context.
                    logger.warning(
                        "Trigger %s references unknown flag in event_data: %s "
                        "(may be set by another trigger)",
                        tid,
                        flag,
                    )

        # Validate precondition types
        for pre in trigger.get("preconditions", []):
            ptype = pre.get("type", "")
            if ptype not in VALID_PRECONDITION_TYPES:
                errors.append(
                    f"Trigger {tid} has invalid precondition type: {ptype}"
                )

        # Validate effect types
        effects = trigger.get("effects", [])
        if not effects:
            errors.append(f"Trigger {tid} has no effects")
        for eff in effects:
            etype = eff.get("type", "")
            if etype not in VALID_EFFECT_TYPES:
                errors.append(f"Trigger {tid} has invalid effect type: {etype}")

    return errors


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------


def _insert_triggers(db: GameDB, triggers: list[dict]) -> list[dict]:
    """Insert validated triggers into the database.

    Returns the list of successfully inserted triggers.
    """
    inserted: list[dict] = []

    for trigger in triggers:
        tid = trigger.get("id", "<unknown>")

        try:
            # Convert one_shot boolean to integer for SQLite
            one_shot_val = trigger.get("one_shot", False)
            if isinstance(one_shot_val, bool):
                one_shot_val = 1 if one_shot_val else 0

            db.insert_trigger(
                id=tid,
                event_type=trigger["event_type"],
                event_data=json.dumps(trigger.get("event_data", {})),
                preconditions=json.dumps(trigger.get("preconditions", [])),
                effects=json.dumps(trigger.get("effects", [])),
                message=trigger.get("message"),
                priority=trigger.get("priority", 0),
                one_shot=one_shot_val,
                executed=0,
                is_enabled=1,
            )
            inserted.append(trigger)
        except Exception:
            logger.exception("Failed to insert trigger %s", tid)

    return inserted


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_pass(db: GameDB, provider: BaseProvider, context: dict) -> dict:
    """Run Pass 10: Triggers. Returns updated context with trigger data."""

    logger.info("Pass 10: Generating triggers...")

    # Fetch dialogue nodes from the DB since the NPC pass does not include
    # them in its context summary.  Triggers need dialogue node IDs to wire
    # dialogue side effects.
    dialogue_nodes = db._fetchall(
        "SELECT id, npc_id, content, set_flags, is_root FROM dialogue_nodes"
    )
    context["dialogue_nodes"] = dialogue_nodes

    prompt = _build_prompt(context)
    gen_ctx = GenerationContext(
        existing_data={},
        seed=context.get("seed"),
        temperature=0.7,
        max_tokens=16_384,
    )

    result = provider.generate_structured(prompt, TRIGGERS_SCHEMA, gen_ctx)
    triggers: list[dict] = result.get("triggers", [])

    # Validate
    errors = _validate_triggers(triggers, context)
    if errors:
        for err in errors:
            logger.warning("Trigger validation: %s", err)

    # Insert into DB
    inserted = _insert_triggers(db, triggers)

    # Build pass-specific data for downstream passes
    triggers_summary = [
        {
            "id": t["id"],
            "event_type": t["event_type"],
            "event_data": t.get("event_data", {}),
            "one_shot": t.get("one_shot", False),
        }
        for t in inserted
    ]

    logger.info(
        "Pass 10 complete: %d triggers generated.",
        len(inserted),
    )
    return {"triggers": triggers_summary}
