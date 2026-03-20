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
import re
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
    "item_accessible",
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
    "toggle_state",
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

TRIGGER_INTENTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["trigger_intents"],
    "properties": {
        "trigger_intents": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "moment",
                    "event_kind",
                    "consequences",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": (
                            "Stable snake_case-ish slug for the trigger concept. "
                            "The compiler normalizes uniqueness."
                        ),
                    },
                    "moment": {
                        "type": "string",
                        "description": (
                            "Creative description of the reactive moment and why it matters."
                        ),
                    },
                    "event_kind": {
                        "type": "string",
                        "enum": sorted(VALID_EVENT_TYPES),
                        "description": (
                            "Which runtime event should watch for this moment."
                        ),
                    },
                    "watched_room_id": {
                        "type": "string",
                        "description": "Room to watch for room-enter or room-scoped events.",
                    },
                    "watched_flag_id": {
                        "type": "string",
                        "description": "Flag to watch for flag_set events.",
                    },
                    "watched_dialogue_node_id": {
                        "type": "string",
                        "description": "Dialogue node to watch for dialogue-driven events.",
                    },
                    "watched_item_id": {
                        "type": "string",
                        "description": "Item to watch for item_taken or item_dropped events.",
                    },
                    "dropped_room_id": {
                        "type": "string",
                        "description": "Room where an item must be dropped, if relevant.",
                    },
                    "required_room_id": {
                        "type": "string",
                        "description": "Extra room precondition if the reaction is room-gated.",
                    },
                    "required_flags_all": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Flags that must already be set.",
                    },
                    "blocked_flags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Flags that must NOT be set yet.",
                    },
                    "required_item_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Inventory items required for the reaction.",
                    },
                    "required_puzzle_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Puzzles that must already be solved.",
                    },
                    "required_lock_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Locks that must already be unlocked.",
                    },
                    "required_npc_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "NPCs that must be present in the scoped room for this trigger."
                        ),
                    },
                    "response_text": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional text the player sees when the trigger fires."
                        ),
                    },
                    "priority_tier": {
                        "type": "string",
                        "enum": ["atmosphere", "standard", "critical", "override", "cleanup"],
                        "description": (
                            "Relative importance. The compiler maps this onto runtime priority."
                        ),
                    },
                    "repeat_mode": {
                        "type": "string",
                        "enum": ["once", "repeat"],
                        "description": (
                            "Whether this should fire once or keep recurring."
                        ),
                    },
                    "consequences": {
                        "type": "object",
                        "description": (
                            "High-level deterministic outcomes. Use exact IDs from the world."
                        ),
                        "properties": {
                            "set_flags": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "unlock_locks": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "reveal_exits": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "solve_puzzles": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "discover_quests": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "open_containers": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "give_item_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "remove_item_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "printed_messages": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "spawn_items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["item_id", "location"],
                                    "properties": {
                                        "item_id": {"type": "string"},
                                        "location": {"type": "string"},
                                    },
                                },
                            },
                            "toggle_items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["item_id", "state"],
                                    "properties": {
                                        "item_id": {"type": "string"},
                                        "state": {"type": "string"},
                                    },
                                },
                            },
                            "move_player_room_id": {
                                "type": "string",
                            },
                            "score_delta": {
                                "type": "integer",
                            },
                            "health_delta": {
                                "type": "integer",
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
    """Construct the LLM prompt for trigger-intent generation."""

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
You are designing reactive world moments for a Zork-style text adventure engine.
Your job is NOT to emit final trigger DSL. Your job is to decide which
reactive moments should exist, what event should watch for them, what
conditions matter, and what outcomes should happen.

Code will compile your intents into legal runtime triggers.

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

## Your Task — Generate Trigger Intents

Each trigger intent should describe:
- the reactive moment
- the watched event kind
- the exact ID being watched
- any extra gating conditions
- the outcome bundle that should happen

Think like a game designer, not a database compiler.

## Event Kinds

### `room_enter`
Watch the player entering a specific room.

### `flag_set`
Watch a specific flag becoming true.

### `dialogue_node`
Watch a specific dialogue node being shown.
Use this whenever dialogue implies a real world change.

### `item_taken`
Watch a specific item being taken.

### `item_dropped`
Watch a specific item being dropped, optionally in a specific room.

## Outcome Bundles

Describe outcomes using the `consequences` object, not raw DSL.
Use the exact IDs from the world data.

- `set_flags`: flags that become true
- `unlock_locks`: locks that should unlock
- `reveal_exits`: hidden exits that should be revealed
- `solve_puzzles`: puzzles that become solved
- `discover_quests`: quests that should be discovered
- `open_containers`: containers that should open
- `give_item_ids`: items the player should receive directly in inventory
- `spawn_items`: items that should appear in a room or container
- `remove_item_ids`: items removed from play
- `toggle_items`: toggleable items set to `on` or `off`
- `move_player_room_id`: room the player is moved to
- `score_delta`: score reward/penalty
- `health_delta`: health change
- `printed_messages`: extra text snippets printed as effects

## Gating Conditions

Use these only when they matter:
- `required_flags_all`
- `blocked_flags`
- `required_item_ids`
- `required_puzzle_ids`
- `required_lock_ids`
- `required_npc_ids`
- `required_room_id`

## Guidelines

1. **Dialogue side effects are critical.** Every dialogue node where an NPC
   gives, trades, reveals, unlocks, rewards, or changes the world should
   usually have a `dialogue_node` trigger intent.

2. **Flag cascades matter.** If two or more flags combine to unlock a result,
   create symmetric `flag_set` intents so the outcome works regardless of order.

3. **Room entry moments should feel authored.** Use `room_enter` for greetings,
   traps, discoveries, warnings, or atmosphere that changes with state.

4. **Dropped-item puzzles need specificity.** For offerings and placement
   puzzles, use `item_dropped` plus a `dropped_room_id`.

5. **Recurring vs one-shot.**
   - `repeat_mode: "once"` for gifts, discoveries, traps, first-time reveals
   - `repeat_mode: "repeat"` for ambient reactions or persistent greetings

6. **Priority tiers.**
   - `override` for safety-critical ordering
   - `critical` for puzzle or progression results
   - `standard` for normal reactive gameplay
   - `atmosphere` for flavor-only moments
   - `cleanup` for very low-priority maintenance reactions

7. **Keep reactions concise.** `response_text` and printed messages should be
   short and punchy. One to three sentences is plenty.

## What NOT to Generate

- **Do NOT emit raw precondition/effect DSL.** The compiler handles that.
- **Do NOT duplicate commands.** Triggers are for reactive state changes.
- **Do NOT invent IDs.** Use ONLY the exact IDs from the data above.

## Realism Level: {realism}

- Low: triggers are sparse, only critical path wiring
- Medium: triggers for critical path + atmospheric room entries + NPC reactions
- High: comprehensive triggers including traps, item reactions, cascading effects

## CRITICAL: Use Exact IDs

You MUST use the exact `id` values from the data above.  Do NOT invent
room, item, NPC, lock, exit, puzzle, flag, or dialogue node IDs.  Copy
them verbatim from the lists.

## Examples

### Dialogue gives the player a key
```json
{{
  "id": "blacksmith_gives_key",
  "moment": "The blacksmith finally hands over the forged key as a reward.",
  "event_kind": "dialogue_node",
  "watched_dialogue_node_id": "blacksmith_forges_key",
  "response_text": "The blacksmith presses a warm iron key into your hand.",
  "priority_tier": "critical",
  "repeat_mode": "once",
  "consequences": {{
    "give_item_ids": ["forged_key"],
    "score_delta": 5
  }}
}}
```

### Room entry warning with an NPC present
```json
{{
  "id": "guard_challenge",
  "moment": "The guard challenges the player the first time they enter the post.",
  "event_kind": "room_enter",
  "watched_room_id": "guard_post",
  "blocked_flags": ["guard_challenged"],
  "required_npc_ids": ["stern_guard"],
  "priority_tier": "atmosphere",
  "repeat_mode": "once",
  "consequences": {{
    "set_flags": ["guard_challenged"],
    "printed_messages": ["The guard steps forward. \\"State your business, stranger.\\""]
  }}
}}
```

### Two flags combine to unlock a door
```json
{{
  "id": "qualifications_unlock_range",
  "moment": "Once both certifications are complete, the office door unlocks.",
  "event_kind": "flag_set",
  "watched_flag_id": "p226_qualified",
  "required_flags_all": ["ar15_qualified"],
  "priority_tier": "critical",
  "repeat_mode": "once",
  "consequences": {{
    "unlock_locks": ["range_office_lock"],
    "printed_messages": ["Both qualifications complete. The range office door unlocks."]
  }}
}}
```

## Output Format

```json
{{
  "trigger_intents": [
    {{
      "id": "trigger_idea",
      "moment": "what happens and why it matters",
      "event_kind": "room_enter|flag_set|dialogue_node|item_taken|item_dropped",
      "response_text": "string or null",
      "priority_tier": "atmosphere|standard|critical|override|cleanup",
      "repeat_mode": "once|repeat",
      "consequences": {{}}
    }}
  ]
}}
```

Generate trigger intents for ALL reactive events this world needs. Focus on:
1. Dialogue nodes that imply world changes (most important)
2. Flag cascades for multi-step unlocks
3. Room entry events for important rooms
4. Item reactions for special/cursed items
5. Placement puzzles

Be thorough. A missing trigger intent means a dialogue promise goes unfulfilled
or a cascade never happens.
"""


# ---------------------------------------------------------------------------
# Intent compiler
# ---------------------------------------------------------------------------


def _slugify_trigger_id(raw_id: str, used_ids: set[str]) -> str:
    """Return a stable unique snake_case trigger id."""
    slug = re.sub(r"[^a-z0-9]+", "_", raw_id.lower()).strip("_")
    if not slug:
        slug = "trigger"
    if not slug.startswith("trigger_"):
        slug = f"trigger_{slug}"

    candidate = slug
    index = 2
    while candidate in used_ids:
        candidate = f"{slug}_{index}"
        index += 1
    used_ids.add(candidate)
    return candidate


def _normalize_priority(intent: dict) -> int:
    """Map a creative priority tier onto a deterministic runtime priority."""
    tier = str(intent.get("priority_tier", "standard")).strip().lower()
    return {
        "override": 100,
        "critical": 25,
        "standard": 10,
        "atmosphere": 0,
        "cleanup": -10,
    }.get(tier, 10)


def _normalize_one_shot(intent: dict) -> bool:
    """Return whether the trigger should fire only once."""
    repeat_mode = str(intent.get("repeat_mode", "once")).strip().lower()
    return repeat_mode != "repeat"


def _normalize_location(location: str | None) -> str | None:
    """Normalize common location aliases used in spawn consequences."""
    if not location:
        return None

    normalized = location.strip()
    lowered = normalized.lower()
    if lowered in {"inventory", "_inventory"}:
        return "_inventory"
    if lowered in {"current", "_current", "current_room"}:
        return "_current"
    return normalized


def _room_scope_for_intent(intent: dict, context: dict) -> str | None:
    """Return the best room scope for room-based preconditions."""
    room_ids = {room["id"] for room in context.get("rooms", [])}

    for key in ("required_room_id", "watched_room_id", "dropped_room_id"):
        room_id = intent.get(key)
        if room_id in room_ids:
            return room_id

    if intent.get("event_kind") == "dialogue_node":
        node_map = {
            node["id"]: node.get("npc_id")
            for node in context.get("dialogue_nodes", [])
            if node.get("id")
        }
        npc_map = {
            npc["id"]: npc.get("room_id")
            for npc in context.get("npcs", [])
            if npc.get("id")
        }
        npc_id = node_map.get(intent.get("watched_dialogue_node_id"))
        room_id = npc_map.get(npc_id)
        if room_id in room_ids:
            return room_id

    return None


def _compile_event_data(intent: dict, context: dict) -> dict:
    """Compile intent-level event selectors into runtime event_data."""
    event_kind = intent.get("event_kind")
    dialogue_nodes = {
        node["id"]: node for node in context.get("dialogue_nodes", []) if node.get("id")
    }

    if event_kind == "room_enter":
        room_id = intent.get("watched_room_id")
        return {"room_id": room_id} if room_id else {}

    if event_kind == "flag_set":
        flag_id = intent.get("watched_flag_id")
        return {"flag": flag_id} if flag_id else {}

    if event_kind == "dialogue_node":
        node_id = intent.get("watched_dialogue_node_id")
        if not node_id:
            return {}
        event_data = {"node_id": node_id}
        npc_id = dialogue_nodes.get(node_id, {}).get("npc_id")
        if npc_id:
            event_data["npc_id"] = npc_id
        return event_data

    if event_kind == "item_taken":
        item_id = intent.get("watched_item_id")
        return {"item_id": item_id} if item_id else {}

    if event_kind == "item_dropped":
        event_data: dict[str, str] = {}
        item_id = intent.get("watched_item_id")
        room_id = intent.get("dropped_room_id")
        if item_id:
            event_data["item_id"] = item_id
        if room_id:
            event_data["room_id"] = room_id
        return event_data

    return {}


def _compile_preconditions(intent: dict, context: dict) -> list[dict]:
    """Compile simplified gating fields into runtime preconditions."""
    room_scope = _room_scope_for_intent(intent, context)
    npc_rooms = {
        npc["id"]: npc.get("room_id")
        for npc in context.get("npcs", [])
        if npc.get("id")
    }
    preconditions: list[dict] = []

    required_room_id = intent.get("required_room_id")
    if required_room_id:
        preconditions.append({"type": "in_room", "room": required_room_id})

    for flag_id in intent.get("required_flags_all", []):
        preconditions.append({"type": "has_flag", "flag": flag_id})

    for flag_id in intent.get("blocked_flags", []):
        preconditions.append({"type": "not_flag", "flag": flag_id})

    for item_id in intent.get("required_item_ids", []):
        preconditions.append({"type": "has_item", "item": item_id})

    for puzzle_id in intent.get("required_puzzle_ids", []):
        preconditions.append({"type": "puzzle_solved", "puzzle": puzzle_id})

    for lock_id in intent.get("required_lock_ids", []):
        preconditions.append({"type": "lock_unlocked", "lock": lock_id})

    for npc_id in intent.get("required_npc_ids", []):
        room_id = room_scope or npc_rooms.get(npc_id)
        if room_id:
            preconditions.append({"type": "npc_in_room", "npc": npc_id, "room": room_id})

    return preconditions


def _compile_effects(intent: dict) -> tuple[list[dict], str | None]:
    """Compile high-level consequences into runtime effect objects."""
    consequences = intent.get("consequences", {}) or {}
    effects: list[dict] = []

    for flag_id in consequences.get("set_flags", []):
        effects.append({"type": "set_flag", "flag": flag_id})

    for lock_id in consequences.get("unlock_locks", []):
        effects.append({"type": "unlock", "lock": lock_id})

    for exit_id in consequences.get("reveal_exits", []):
        effects.append({"type": "reveal_exit", "exit": exit_id})

    for puzzle_id in consequences.get("solve_puzzles", []):
        effects.append({"type": "solve_puzzle", "puzzle": puzzle_id})

    for quest_id in consequences.get("discover_quests", []):
        effects.append({"type": "discover_quest", "quest": quest_id})

    for container_id in consequences.get("open_containers", []):
        effects.append({"type": "open_container", "container": container_id})

    for item_id in consequences.get("give_item_ids", []):
        effects.append({"type": "spawn_item", "item": item_id, "location": "_inventory"})

    for item_id in consequences.get("remove_item_ids", []):
        effects.append({"type": "remove_item", "item": item_id})

    for placement in consequences.get("spawn_items", []):
        item_id = placement.get("item_id")
        location = _normalize_location(placement.get("location"))
        if item_id and location:
            effects.append({"type": "spawn_item", "item": item_id, "location": location})

    for toggle in consequences.get("toggle_items", []):
        item_id = toggle.get("item_id")
        state = toggle.get("state")
        if item_id and state:
            effects.append({"type": "set_toggle_state", "item": item_id, "state": state})

    move_player_room_id = consequences.get("move_player_room_id")
    if move_player_room_id:
        effects.append({"type": "move_player", "room": move_player_room_id})

    score_delta = consequences.get("score_delta")
    if isinstance(score_delta, int) and score_delta != 0:
        effects.append({"type": "add_score", "points": score_delta})

    health_delta = consequences.get("health_delta")
    if isinstance(health_delta, int) and health_delta != 0:
        effects.append({"type": "change_health", "amount": health_delta})

    for message in consequences.get("printed_messages", []):
        if message:
            effects.append({"type": "print", "message": message})

    response_text = intent.get("response_text")
    if response_text and not effects:
        effects.append({"type": "print", "message": response_text})
        return effects, None

    return effects, response_text


def _compile_trigger_intents(intents: list[dict], context: dict) -> list[dict]:
    """Compile creative trigger intents into deterministic runtime triggers."""
    compiled: list[dict] = []
    used_ids: set[str] = set()

    for intent in intents:
        effects, message = _compile_effects(intent)
        compiled.append(
            {
                "id": _slugify_trigger_id(intent.get("id", "trigger"), used_ids),
                "event_type": intent.get("event_kind"),
                "event_data": _compile_event_data(intent, context),
                "preconditions": _compile_preconditions(intent, context),
                "effects": effects,
                "message": message,
                "priority": _normalize_priority(intent),
                "one_shot": _normalize_one_shot(intent),
                "moment": intent.get("moment", ""),
            }
        )

    return compiled


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_triggers(triggers: list[dict], context: dict) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors: list[str] = []

    room_ids = {r["id"] for r in context.get("rooms", [])}
    item_ids = {i["id"] for i in context.get("items", [])}
    dialogue_node_ids = {d["id"] for d in context.get("dialogue_nodes", [])}
    puzzle_ids = {p["id"] for p in context.get("puzzles", [])}
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
            elif etype == "solve_puzzle":
                puzzle_id = eff.get("puzzle", "")
                if puzzle_id and puzzle_id not in puzzle_ids:
                    errors.append(
                        f"Trigger {tid} references unknown puzzle in effect: {puzzle_id}"
                    )

        if event_type == "flag_set":
            watched_flag = event_data.get("flag")
            if watched_flag and any(
                eff.get("type") == "set_flag" and eff.get("flag") == watched_flag
                for eff in effects
            ):
                errors.append(
                    f"Trigger {tid} watches flag {watched_flag} and sets it again"
                )

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


def _insert_missing_flags_for_triggers(
    db: GameDB, triggers: list[dict], context: dict
) -> list[dict]:
    """Insert any trigger-referenced flags missing from the flags table."""
    existing_flags = {f["id"] for f in context.get("flags", [])}
    discovered_flags: set[str] = set()

    for trigger in triggers:
        event_type = trigger.get("event_type")
        event_data = trigger.get("event_data", {}) or {}
        if event_type == "flag_set":
            flag = event_data.get("flag")
            if flag:
                discovered_flags.add(flag)

        for pre in trigger.get("preconditions", []):
            if pre.get("type") in {"has_flag", "not_flag"} and pre.get("flag"):
                discovered_flags.add(pre["flag"])

        for eff in trigger.get("effects", []):
            if eff.get("type") == "set_flag" and eff.get("flag"):
                discovered_flags.add(eff["flag"])

    inserted_flags: list[dict] = []
    for flag_id in sorted(discovered_flags - existing_flags):
        if db.get_flag(flag_id) is not None:
            continue
        db.insert_flag(
            id=flag_id,
            value="false",
            description=f"Autogenerated from trigger references: {flag_id}",
        )
        inserted_flags.append(
            {
                "id": flag_id,
                "description": f"Autogenerated from trigger references: {flag_id}",
            }
        )

    return inserted_flags


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_pass(db: GameDB, provider: BaseProvider, context: dict) -> dict:
    """Run Pass 10: Triggers. Returns updated context with trigger data."""

    logger.info("Pass 10: Generating trigger intents...")

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

    result = provider.generate_structured(prompt, TRIGGER_INTENTS_SCHEMA, gen_ctx)
    trigger_intents: list[dict] = result.get("trigger_intents", [])
    triggers = _compile_trigger_intents(trigger_intents, context)

    # Validate
    errors = _validate_triggers(triggers, context)
    if errors:
        preview = "; ".join(errors[:8])
        raise ValueError(f"Trigger validation failed: {preview}")

    inserted_flags = _insert_missing_flags_for_triggers(db, triggers, context)
    if inserted_flags:
        context["flags"] = [*context.get("flags", []), *inserted_flags]

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
