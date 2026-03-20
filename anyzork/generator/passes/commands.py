"""Pass 7: Commands — Wire the entire world together with DSL rules.

This is the most critical pass in the generation pipeline.  Every
interactable entity in the game needs commands.  If the player can see it,
they will try to interact with it.  If there is no command for that
interaction, they get a generic "You can't do that" — acceptable for truly
non-interactive scenery but frustrating for items, NPCs, and puzzle elements.

Commands use the AnyZork Command DSL: each command is a JSON rule with a
verb, a pattern, preconditions (all must be true to fire), and effects
(executed in order when the command fires).

**Built-in verbs** handled by the engine (do NOT generate DSL commands for
these unless overriding default behavior):
  - take, drop, examine, open, talk, ask

**DSL commands should focus on game-specific interactions**:
  - use X on Y, combine X with Y, read X, pull X, push X, give X to Y,
    show X to Y, enter <code>, light X, extinguish X, etc.

This pass also generates all the flag definitions referenced by commands.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from anyzork.db.schema import GameDB
from anyzork.generator.providers.base import BaseProvider, GenerationContext
from anyzork.generator.validator import (
    ValidationError,
    _validate_rule_effects,
    _validate_rule_preconditions,
)

logger = logging.getLogger(__name__)

_DEFAULT_STAGE_TIMEOUTS: dict[str, float] = {
    "intents": 90.0,
    "compile": 180.0,
}


class _StageTimeoutSignal(BaseException):
    """Internal signal used to interrupt a stuck provider call."""

# ---------------------------------------------------------------------------
# JSON schema the LLM must conform to
# ---------------------------------------------------------------------------

COMMAND_INTENTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["intents"],
    "properties": {
        "intents": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "verb",
                    "pattern",
                    "purpose",
                    "trigger_conditions",
                    "outcome_steps",
                    "success_message",
                    "failure_message",
                    "priority",
                    "one_shot",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "verb": {"type": "string"},
                    "pattern": {"type": "string"},
                    "purpose": {
                        "type": "string",
                        "description": "One-sentence summary of what this interaction does.",
                    },
                    "trigger_conditions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Human-readable conditions that must be true.",
                    },
                    "outcome_steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Human-readable ordered outcomes when the command succeeds.",
                    },
                    "success_message": {"type": "string"},
                    "failure_message": {"type": "string"},
                    "priority": {"type": "integer"},
                    "one_shot": {"type": "integer", "enum": [0, 1]},
                    "context_room_ids": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                    },
                    "done_message": {"type": "string"},
                },
            },
        }
    },
}


COMMANDS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["commands", "flags"],
    "properties": {
        "commands": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "verb",
                    "pattern",
                    "preconditions",
                    "effects",
                    "success_message",
                    "failure_message",
                    "priority",
                    "one_shot",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique snake_case identifier.",
                    },
                    "verb": {
                        "type": "string",
                        "description": "The first word of input that triggers matching.",
                    },
                    "pattern": {
                        "type": "string",
                        "description": (
                            "Full input pattern with {slot} placeholders. "
                            "Must start with the verb."
                        ),
                    },
                    "preconditions": {
                        "type": "array",
                        "description": "Array of precondition objects. ALL must be true.",
                        "items": {
                            "type": "object",
                            "required": ["type"],
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
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
                                        "toggle_state",
                                    ],
                                },
                            },
                        },
                    },
                    "effects": {
                        "type": "array",
                        "description": "Ordered array of effect objects.",
                        "items": {
                            "type": "object",
                            "required": ["type"],
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
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
                                        "print",
                                        "open_container",
                                        "move_item_to_container",
                                        "take_item_from_container",
                                        "consume_quantity",
                                        "restore_quantity",
                                        "set_toggle_state",
                                    ],
                                },
                            },
                        },
                    },
                    "success_message": {
                        "type": "string",
                        "description": "Text shown when the command fires.",
                    },
                    "failure_message": {
                        "type": "string",
                        "description": (
                            "Text shown when preconditions fail. "
                            "Should hint at what is missing."
                        ),
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Higher priority wins on ambiguous matches.",
                    },
                    "one_shot": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "1 = fires only once, then disabled forever.",
                    },
                    "context_room_ids": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": (
                            "JSON array of room IDs where this command is "
                            "active. null = global (works anywhere). "
                            '["room_a"] = only in that room. '
                            '["room_a", "room_b"] = works in either.'
                        ),
                    },
                    "done_message": {
                        "type": "string",
                        "description": (
                            "For one_shot commands: message shown when the player "
                            "tries the action again after it has already been "
                            "executed. Leave empty if no feedback is needed."
                        ),
                    },
                },
            },
        },
        "flags": {
            "type": "array",
            "description": "All flags referenced by commands, with initial values.",
            "items": {
                "type": "object",
                "required": ["id", "description"],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique snake_case flag identifier.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Internal documentation of this flag.",
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
    """Construct the LLM prompt for command generation."""

    concept = context.get("concept", {})
    rooms = context.get("rooms", [])
    items = context.get("items", [])
    npcs = context.get("npcs", [])
    locks = context.get("locks", [])
    puzzles = context.get("puzzles", [])

    rooms_summary = json.dumps(
        [{"id": r["id"], "name": r["name"], "region": r["region"]} for r in rooms],
        indent=2,
    )

    items_summary = json.dumps(items, indent=2)
    npcs_summary = json.dumps(npcs, indent=2)
    locks_summary = json.dumps(locks, indent=2) if locks else "[]"
    puzzles_summary = json.dumps(puzzles, indent=2) if puzzles else "[]"

    # Build the exits summary from context
    exits = context.get("exits", [])
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

    retry_guidance = ""
    last_error = context.get("_last_error")
    if last_error:
        retry_guidance = f"""

## Previous Attempt Failed
Your previous command draft was rejected with these validation errors:
{last_error}

Fix those exact issues in this new draft.

Critical repair rules:
- Do NOT invent IDs. Only use IDs listed in Rooms, Exits, Items, NPCs, Locks, and Puzzles.
- `pattern` must begin with the command verb. If the draft omits it, prefix the verb.
- `toggle_state` is a PRECONDITION. `set_toggle_state` is an EFFECT.
- `not_flag` is a PRECONDITION only. To clear a flag, use
  `{{"type": "set_flag", "flag": "some_flag", "value": false}}`.
- To destroy or hide an item after use, use `remove_item`.
  Do NOT move items to `_nowhere` or `nowhere`.
- To take an item out of a container, use `take_item_from_container`.
  Do NOT use `move_item` with a container in `from`.
- To place an item into a container, use `move_item_to_container`.
  Do NOT use `move_item` with a container in `to`.
- `_inventory` is not a real container for containment checks. Use `has_item`
  for inventory possession, and use a real container ID for `item_in_container`
  or `not_item_in_container`.
- `unlock` must reference a lock ID from the Locks list, never an exit ID
  or a container/item ID.
- `_player_inventory` is not a valid alias. Use `_inventory`.
- `item_in_container` with `_inventory` should become `has_item`.
- `not_item_in_container` must not use `_inventory`; use a real container.
- NPCs are not items. Do NOT model NPC relocation with `move_item`; if an NPC
  move is only flavor, express it with text or flags instead.
- Commands that only provide special text, such as an `examine` override,
  are allowed to have an empty `effects` array.
"""

    return f"""\
You are the command systems designer for a Zork-style text adventure engine.
Your job is to generate the DSL command rules that wire every interactable
entity in the game together.

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

## Locks
{locks_summary}

## Puzzles
{puzzles_summary}
{retry_guidance}

## The Command DSL — CRITICAL REFERENCE

### Structure

Each command is a JSON rule:
- **verb**: The first word of the player's input (lowercased).
- **pattern**: Full input pattern with {{slot}} placeholders.
  Example: `use {{item}} on {{target}}`
- **preconditions**: ALL must be true for the command to fire.
- **effects**: Executed in order when all preconditions pass.
- **success_message**: Shown when the command fires.
- **failure_message**: Shown when preconditions fail. Must be informative and non-empty.
- **one_shot**: 1 = fires only once (key unlocks, puzzle solutions, quest
  discoveries). 0 = repeatable.
- **context_room_ids**: JSON array of room IDs where the command is active.
  null = global (works anywhere). `["room_a"]` = only in that room.
  `["room_a", "room_b"]` = works in either.

### BUILT-IN VERBS — DO NOT GENERATE COMMANDS FOR THESE

The engine handles these verbs with built-in logic:
- **take** / **get** — picks up takeable items
- **drop** — drops items from inventory
- **examine** / **look at** / **inspect** — shows examine_description
- **read** — shows read_description (falls back to examine_description).
  DO NOT generate "read" commands — set `read_description` on items instead.
- **open** — basic open interaction (including auto-unlock if player has key)
- **unlock** — tries to unlock exits/containers using key_item_id from schema
- **use {{item}} on {{target}}** — the engine handles this built-in. It first
  tries key-on-lock (if the target has `key_item_id`), then falls back to
  put-in-container (treats "use X on Y" as "put X in Y").
  DO NOT generate "use" commands — keys are handled via `key_item_id` and
  container interactions are handled via the built-in `put in` logic.
- **put {{item}} in {{container}}** — places an item into a container. The engine
  validates whitelists (`accepts_items`) and cycle detection automatically.
  DO NOT generate "put" commands for basic container insertion.
- **talk to** / **speak to** — triggers NPC dialogue system
- **ask ... about** — triggers NPC topic dialogue with flag-gated responses.
  DO NOT generate "ask NPC about topic" commands — use dialogue table entries.

DO NOT create commands for these verbs UNLESS you need to override default
behavior for a specific interaction (e.g., examining a specific item triggers
a special event beyond the normal examine_description).

### ONE-SHOT COMMANDS — USE done_message INSTEAD OF DUPLICATES

When a one-shot command has already been executed, the engine shows its
`done_message` field instead of "I don't understand." DO NOT generate
separate "already done" duplicate commands. Instead, set `done_message`
on the original one-shot command.

### GAME-SPECIFIC VERBS — YOUR FOCUS

Generate commands for these kinds of interactions:
- `combine {{item}} with {{item2}}` — merge two inventory items
- `pull {{target}}` — pull levers, chains, handles
- `push {{target}}` — push buttons, statues, blocks
- `give {{item}} to {{npc}}` — hand items to NPCs for quests
- `show {{item}} to {{npc}}` — present items without giving them away
- `light {{target}}` — light a lantern, torch, candle
- `enter {{code}}` — combination lock codes
- `pour {{item}}` / `pour {{item}} on {{target}}` — liquid interactions
- `climb {{target}}` — ropes, ladders, walls
- `turn {{target}}` — dials, wheels, keys in locks
- `insert {{item}} in {{target}}` — placing objects into receptacles

**Container nesting commands:**
When the world contains nested containers (gun/magazine/ammo,
backpack/pouch/gem), generate DSL commands for assembly and disassembly
verbs:
- `load {{target}}` — alias for putting the right item into the target
  container. Use `move_item_to_container` effect.
- `unload {{target}}` — alias for removing an item from a container. Use
  `take_item_from_container` effect.

Use these precondition types to gate nesting commands:
- `item_in_container` — check that an item IS inside a specific container
- `not_item_in_container` — check that an item is NOT inside a container
  (prevent double-loading)
- `container_has_contents` — check that a container is non-empty
- `container_empty` — check that a container is empty
  The player inventory is not a valid container target for these checks.

**Placement puzzles**: When the world design requires placing an item at a
specific location (putting a crystal on an altar, placing an offering in a
shrine), generate commands using the `put`, `place`, or `use` verbs with high
priority (10+). The engine tries DSL commands before built-in handlers for
these verbs. Preconditions should include both `has_item` and `in_room`. For
critical-path placements, generate commands for at least two verb variants so
the player's phrasing doesn't block them.

**Container transfer rules**:
- Moving an item from inventory/current room into a container uses
  `move_item_to_container`.
- Taking an item out of a container uses `take_item_from_container`.
- Do NOT use `move_item` when either side of the move is a container.

### Precondition Types Reference

| Type | Required Fields | Description |
|------|----------------|-------------|
| `in_room` | `room` | Player is in this room |
| `has_item` | `item` | Player has item in inventory. Supports `{{slot}}` refs |
| `has_flag` | `flag` | World flag is set (truthy) |
| `not_flag` | `flag` | World flag is NOT set |
| `item_in_room` | `item`, `room` | Item exists in room. `"_current"` for current room |
| `item_accessible` | `item` | Item is reachable now: room, inventory, or open container |
| `npc_in_room` | `npc`, `room` | NPC is in room. `"_current"` for current room |
| `lock_unlocked` | `lock` | Lock is unlocked |
| `puzzle_solved` | `puzzle` | Puzzle is solved |
| `health_above` | `threshold` | Player health > threshold |
| `item_in_container` | `item`, `container` | Item is inside a specific container |
| `not_item_in_container` | `item`, `container` | Item is NOT inside a container |
| `container_has_contents` | `container` | Container is non-empty |
| `container_empty` | `container` | Container is empty |
| `toggle_state` | `item`, `state` | Item has a specific toggle state |

### Effect Types Reference

| Type | Required Fields | Description |
|------|----------------|-------------|
| `move_item` | `item`, `from`, `to` | Move item between locations. Inventory/current room/room ID |
| `remove_item` | `item` | Permanently destroy item |
| `set_flag` | `flag` | Set a world flag. Optional `value` (default true) |
| `unlock` | `lock` | Unlock a lock |
| `move_player` | `room` | Teleport player |
| `spawn_item` | `item`, `location` | Place a hidden item into the world |
| `change_health` | `amount` | Modify HP (positive heals, negative damages) |
| `add_score` | `points` | Add score points |
| `reveal_exit` | `exit` | Make hidden exit visible |
| `solve_puzzle` | `puzzle` | Mark puzzle as solved |
| `print` | `message` | Display text. Supports `{{slot}}` refs |
| `open_container` | `container` | Set container is_locked=0 and is_open=1 |
| `move_item_to_container` | `item`, `container` | Move item into a container |
| `take_item_from_container` | `item`, `container` | Remove item from a container |
| `consume_quantity` | `item`, `amount` | Reduce item quantity by `amount` |
| `restore_quantity` | `item`, `amount` | Increase quantity. Optional `source` field |
| `set_toggle_state` | `item`, `state` | Set an item's toggle_state to a specific value |

### Additional Precondition Type

| `container_open` | `container` | Container is open (or has no lid) |
| `has_quantity` | `item`, `min` | Item has at least `min` quantity remaining |

### Container Unlock Commands

Locked containers with `key_item_id` set are handled automatically by the
engine — do NOT generate DSL commands for those. Only generate DSL commands
for locked containers that require non-key interactions (e.g., solving a
puzzle, using a tool in a non-standard way).

### Quantity and State Commands

Use the new precondition and effect types for item dynamics:

- `has_quantity` precondition: gate commands on items with limited uses.
  E.g., a gun command requires `{{"type": "has_quantity", "item": "ammo", "min": 1}}`.
- `consume_quantity` effect: reduce an item's quantity after use.
  E.g., firing a gun: `{{"type": "consume_quantity", "item": "ammo", "amount": 1}}`.
- `restore_quantity` effect: refill an item's quantity (reload, recharge).
  E.g., reloading: `{{"type": "restore_quantity", "item": "magazine", "amount": 10}}`.
  Optional `source` field consumes from another item.
- `set_toggle_state` effect: change an item's toggle state as a side effect.
  E.g., a puzzle that extinguishes all lanterns:
  `{{"type": "set_toggle_state", "item": "brass_lantern", "state": "off"}}`.
- `toggle_state` precondition: check whether an item is currently `"on"`,
  `"off"`, or another specific state before a command can fire.
- To clear a flag, use `{{"type": "set_flag", "flag": "some_flag", "value": false}}`.
  `not_flag` is a precondition type only, never an effect.
- `unlock` only accepts IDs from the Locks list. If you need to directly
  open a container, use `open_container` with the container's item ID.

**IMPORTANT**: Broad "use item on target" interactions are handled by the
interaction matrix, NOT by DSL commands. Only generate DSL commands for
interactions that change game state (solve puzzles, unlock things, advance
quests). The interaction matrix handles flavor text for casual interactions.

### Command Coverage Requirements

1. **Key-type locks are handled automatically** — do NOT generate "use key
   on lock" commands. The engine reads `key_item_id` from the locks table
   and items table (for containers) and handles unlocking automatically.

2. **Every puzzle** needs commands matching its solution steps.  The final
   step should include `solve_puzzle` in its effects.

3. **Interactive scenery items** (levers, buttons, switches) need
   appropriate commands.

4. **NPC quest interactions** (give item, show item) need commands with
   `npc_in_room` preconditions. But "ask NPC about topic" is handled by
   the dialogue system — do NOT generate DSL commands for those.

5. **Combination locks** need `enter {{code}}` commands.

6. **State-based interactions** — items or scenery that change behavior
   depending on flags (lit/unlit lantern, open/closed container).

7. **Readable items are handled automatically** — do NOT generate "read"
   commands. Set `read_description` on the item instead.

### CRITICAL: Use Exact IDs

You MUST use the exact `id` values from the data above. Do NOT invent
room, item, NPC, lock, exit, or puzzle IDs — copy them verbatim from
the lists. If `context_room_ids` entries or `puzzle_id` does not match an
existing entity, the reference will be dropped.

### Design Principles

- **Focus on UNIQUE interactions only**: Do not generate commands for patterns
  the engine handles automatically (key-on-lock, read, ask NPC about topic).
  Only generate DSL commands for interactions that cannot be derived from
  schema data.

- **No verb synonym duplicates**: Generate ONE canonical command per
  interaction. Do not create alternate-verb versions (e.g., do not create
  both "use X on Y" and "cut Y" for the same action).

- **Use done_message for one-shot feedback**: When a one-shot command has
  already been executed, set `done_message` to tell the player. Do NOT
  generate a second "already done" command.

- **Informative failure messages**: "The door is locked" is better than
  "You can't do that."  "The key doesn't fit this lock" is better than
  "Nothing happens."

- **One-shot for permanent changes**: Puzzle solutions, quest
  discoveries, first-time NPC meetings should be one_shot = 1.

- **Repeatable for observation**: Looking at scenery — one_shot = 0.

- **Priority ordering**: Use higher priority for specific overrides.
  A room-specific "push statue" command (priority 10) should beat a generic
  "push {{target}}" command (priority 0).

### Flags

Also generate a `flags` array listing all NEW flags referenced by your commands
(in preconditions or effects) that do not already exist in prior-pass data.
Do not repeat flags that already exist. All new flags initialize to `"false"`.

## Output Format

```json
{{
  "commands": [
    {{
      "id": "pull_rusty_chain",
      "verb": "pull",
      "pattern": "pull {{target}}",
      "preconditions": [
        {{"type": "in_room", "room": "dungeon_entrance"}},
        {{"type": "not_flag", "flag": "secret_door_revealed"}}
      ],
      "effects": [
        {{"type": "reveal_exit", "exit": "dungeon_secret_passage"}},
        {{"type": "set_flag", "flag": "secret_door_revealed"}},
        {{"type": "add_score", "points": 10}},
        {{
          "type": "print",
          "message": "The chain grinds through old gears, and a hidden passage yawns open."
        }}
      ],
      "success_message": "",
      "failure_message": "You tug the chain, but nothing else happens.",
      "priority": 10,
      "one_shot": 1,
      "context_room_ids": ["dungeon_entrance"]
    }}
  ],
  "flags": [
    {{
      "id": "secret_door_revealed",
      "description": "Set when the player reveals the hidden dungeon passage."
    }}
  ]
}}
```

Generate commands for EVERY interactable entity and EVERY puzzle step.
Be thorough — a missing command means the player cannot progress.
"""


def _build_intents_prompt(context: dict) -> str:
    """Construct the first-stage prompt for interaction intents."""
    concept = context.get("concept", {})
    rooms = context.get("rooms", [])
    items = context.get("items", [])
    npcs = context.get("npcs", [])
    locks = context.get("locks", [])
    puzzles = context.get("puzzles", [])
    exits = context.get("exits", [])

    rooms_summary = json.dumps(
        [{"id": r["id"], "name": r["name"], "region": r["region"]} for r in rooms],
        indent=2,
    )
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
    items_summary = json.dumps(items, indent=2)
    npcs_summary = json.dumps(npcs, indent=2)
    locks_summary = json.dumps(locks, indent=2) if locks else "[]"
    puzzles_summary = json.dumps(puzzles, indent=2) if puzzles else "[]"

    return f"""\
You are designing interaction intents for a Zork-style text adventure.
Do NOT write strict DSL rules yet. First decide what bespoke interactions
the world needs so a later compiler can translate them into AnyZork's DSL.

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

## Locks
{locks_summary}

## Puzzles
{puzzles_summary}

## Your Task

Produce a concise interaction-intent list for the UNIQUE commands this world
needs beyond built-in engine behavior.

Built-in behavior already handles:
- take / get
- drop
- examine / look at / inspect
- read
- open
- unlock
- use {{item}} on {{target}} for standard key-on-lock and put-in-container
- put {{item}} in {{container}}
- talk to / speak to
- ask NPC about topic

So your intent list should focus on bespoke state-changing interactions and
special observation overrides, such as:
- puzzle steps
- hidden mechanism interactions
- NPC handoff/show interactions tied to progress
- light/extinguish or other stateful item interactions
- custom examine overrides that reveal clues or special text
- placement/assembly/disassembly interactions that matter to progression

For each intent:
- describe the purpose in plain English
- list trigger conditions in plain English
- list ordered outcome steps in plain English
- use exact world IDs whenever you mention a concrete entity
- do NOT invent new rooms, items, NPCs, locks, exits, or puzzles
- if an interaction would reveal, create, combine, or hand over an item later,
  that item must already exist in the Items list above
- commands are not allowed to mint brand-new items like combined objects or
  hidden rewards unless those items already exist in the generated item set
- NPC movement is not a supported DSL effect. If a scene needs an NPC to
  "move", represent the consequence with text, a flag change, or another
  supported state transition instead of `move_item`.
- if an idea depends on a brand-new item that does not exist, rewrite it as a
  flag change, text reveal, or an interaction with an existing item instead
- keep `failure_message` specific and helpful
- use `one_shot = 1` only for permanent changes
- commands that are just custom text overrides may have no world-state outcome

Generate intents for every critical puzzle step and important bespoke
interaction, but avoid trivial duplicates.
"""


def _build_compile_prompt(context: dict, intents: list[dict]) -> str:
    """Construct the second-stage prompt that compiles intents into DSL."""
    base_prompt = _build_prompt(context)
    intents_section = (
        "## Interaction Intents To Compile\n"
        f"{json.dumps(intents, indent=2)}\n\n"
        "Compile these intents into valid AnyZork DSL rules without losing "
        "their meaning. Do not redesign the interaction list or invent extra "
        "commands unless needed to express one of these intents in valid DSL.\n"
        "If a draft uses `_player_inventory`, normalize it to `_inventory`.\n"
        "If a draft uses `move_item` for an NPC, remove that state move and "
        "preserve the narrative consequence with text or other supported effects.\n\n"
    )
    base_prompt = base_prompt.replace(
        "You are the command systems designer for a Zork-style text adventure engine.\n"
        "Your job is to generate the DSL command rules that wire every interactable\n"
        "entity in the game together.",
        "You are compiling interaction intents into AnyZork's strict command DSL.\n"
        "Preserve the authored intent faithfully, but the output must be valid DSL.",
        1,
    )
    return base_prompt.replace(
        "## The Command DSL — CRITICAL REFERENCE\n\n",
        f"{intents_section}## The Command DSL — CRITICAL REFERENCE\n\n",
        1,
    )


def _stage_timeout_seconds(stage: str, context: dict) -> float:
    """Return the configured timeout for a command-generation stage."""
    overrides = context.get("_command_stage_timeouts", {})
    if stage in overrides:
        return float(overrides[stage])

    env_name = f"ANYZORK_COMMANDS_{stage.upper()}_TIMEOUT_SECONDS"
    raw = os.getenv(env_name)
    if raw:
        try:
            return float(raw)
        except ValueError:
            logger.warning(
                "Ignoring invalid %s value %r; using default timeout.",
                env_name,
                raw,
            )

    return _DEFAULT_STAGE_TIMEOUTS.get(stage, 0.0)


def _command_debug_dir(context: dict) -> Path:
    """Return where command-pass debug artifacts should be written."""
    override = context.get("_command_debug_dir")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".anyzork" / "debug" / "commands"


def _command_debug_run_id(context: dict) -> str:
    """Return a stable run id for command-pass debug artifacts."""
    run_id = context.get("_command_debug_run_id")
    if run_id:
        return str(run_id)

    seed = context.get("seed")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"seed-{seed if seed is not None else 'auto'}-{timestamp}"
    context["_command_debug_run_id"] = run_id
    return run_id


def _persist_command_debug_artifact(stage: str, context: dict, payload: dict) -> Path:
    """Persist a JSON artifact describing a failed or slow command stage."""
    debug_dir = _command_debug_dir(context)
    debug_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{_command_debug_run_id(context)}-{stage}-{time.time_ns()}.json"
    artifact_path = debug_dir / filename
    artifact_path.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    context["_last_command_debug_artifact"] = str(artifact_path)
    return artifact_path


def _run_with_timeout(callable_obj: Any, *, timeout_seconds: float, label: str) -> Any:
    """Run a blocking provider call with a best-effort hard timeout."""
    if timeout_seconds <= 0:
        return callable_obj()

    if not hasattr(signal, "SIGALRM") or threading.current_thread() is not threading.main_thread():
        logger.warning(
            "Command stage timeout for %s is unsupported on this platform/thread; "
            "running without a hard deadline.",
            label,
        )
        return callable_obj()

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, 0.0)

    def _handle_timeout(signum: int, frame: Any) -> None:
        raise _StageTimeoutSignal(f"{label} timed out")

    signal.signal(signal.SIGALRM, _handle_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return callable_obj()
    except _StageTimeoutSignal as exc:
        raise TimeoutError(
            f"{label} timed out after {timeout_seconds:.1f} seconds"
        ) from exc
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)


def _generate_stage(
    provider: BaseProvider,
    *,
    stage: str,
    prompt: str,
    schema: dict,
    gen_ctx: GenerationContext,
    context: dict,
    extra_artifact_payload: dict | None = None,
) -> tuple[dict, float]:
    """Run a provider-backed stage with timing, timeout, and debug artifacts."""
    timeout_seconds = _stage_timeout_seconds(stage, context)
    start = time.perf_counter()
    logger.info(
        "Pass 7 [%s]: requesting provider output (timeout %.1fs).",
        stage,
        timeout_seconds,
    )

    try:
        result = _run_with_timeout(
            lambda: provider.generate_structured(prompt, schema, gen_ctx),
            timeout_seconds=timeout_seconds,
            label=f"commands {stage} stage",
        )
    except Exception as exc:
        payload = {
            "stage": stage,
            "seed": context.get("seed"),
            "elapsed_seconds": round(time.perf_counter() - start, 3),
            "timeout_seconds": timeout_seconds,
            "error": str(exc),
            "prompt": prompt,
        }
        if extra_artifact_payload:
            payload.update(extra_artifact_payload)
        artifact_path = _persist_command_debug_artifact(stage, context, payload)
        raise type(exc)(
            f"{exc} Debug artifact written to {artifact_path}."
        ) from exc

    elapsed = time.perf_counter() - start
    logger.info(
        "Pass 7 [%s]: provider returned in %.2fs.",
        stage,
        elapsed,
    )
    return result, elapsed


# ---------------------------------------------------------------------------
# Validation
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
    "print",
    "open_container",
    "move_item_to_container",
    "take_item_from_container",
    "consume_quantity",
    "restore_quantity",
    "set_toggle_state",
}


def _default_failure_message(verb: str, pattern: str) -> str:
    """Return a generic but informative failure message for a command."""
    verb = verb.lower().strip()
    tail = pattern[len(verb) :].strip() if pattern.lower().startswith(verb) else pattern.strip()

    if verb in {"examine", "read"}:
        return (
            f"You don't notice anything unusual about {tail}."
            if tail
            else "You don't notice anything unusual."
        )
    if verb in {"take", "get"}:
        return (
            f"You can't take {tail} right now."
            if tail
            else "You can't take that right now."
        )
    if verb in {"open", "unlock"}:
        return (
            f"That doesn't seem to open {tail}."
            if tail
            else "That doesn't seem to open anything useful."
        )
    if verb in {"use", "put", "insert", "give", "show", "combine", "pour"}:
        return (
            f"That doesn't seem to work with {tail}."
            if tail
            else "That doesn't seem to work."
        )
    if verb in {"pull", "push", "turn", "light", "extinguish", "bang", "climb"}:
        return (
            f"Nothing obvious happens when you try {tail}."
            if tail
            else "Nothing obvious happens."
        )
    if tail:
        return f"That doesn't seem to do anything useful with {tail}."
    return "That doesn't seem to do anything useful."


def _normalize_command_aliases(commands: list[dict], context: dict) -> None:
    """Normalize common provider aliases to canonical DSL constants."""
    inventory_aliases = {"inventory", "_inventory", "_player_inventory"}
    location_aliases = {
        "inventory": "_inventory",
        "_player_inventory": "_inventory",
        "current": "_current",
        "current_room": "_current",
        "null": "_current",
        "none": "_current",
        "nowhere": "_nowhere",
        "_nowhere": "_nowhere",
    }
    lock_by_exit_id = {
        lock["target_exit_id"]: lock["id"]
        for lock in context.get("locks", [])
        if lock.get("target_exit_id") and lock.get("id")
    }
    container_ids = {
        item["id"]
        for item in context.get("items", [])
        if item.get("is_container")
    }
    portable_item_ids = {
        item["id"]
        for item in context.get("items", [])
        if item.get("is_takeable")
    }
    npc_ids = {
        npc["id"]
        for npc in context.get("npcs", [])
        if npc.get("id")
    }

    for cmd in commands:
        verb = str(cmd.get("verb", "")).strip().lower()
        pattern = str(cmd.get("pattern", "")).strip()
        if verb and pattern and not pattern.lower().startswith(verb):
            cmd["pattern"] = f"{verb} {pattern}".strip()

        if not str(cmd.get("failure_message", "")).strip():
            cmd["failure_message"] = _default_failure_message(
                verb,
                str(cmd.get("pattern", "")),
            )

        for pre in cmd.get("preconditions", []):
            if pre.get("type") == "set_toggle_state":
                pre["type"] = "toggle_state"
            elif (
                pre.get("type") == "item_in_container"
                and str(pre.get("container", "")).strip().lower() in inventory_aliases
            ):
                pre["type"] = "has_item"
                pre.pop("container", None)
            elif (
                pre.get("type") == "item_in_room"
                and cmd.get("verb") in {"examine", "read"}
                and pre.get("item") in portable_item_ids
            ):
                pre["type"] = "item_accessible"
                pre.pop("room", None)

        normalized_effects: list[dict] = []
        for eff in cmd.get("effects", []):
            eff_type = eff.get("type")
            if eff_type == "not_flag":
                eff["type"] = "set_flag"
                eff["value"] = False
                eff_type = "set_flag"

            if eff_type == "spawn_item":
                location = eff.get("location")
                if isinstance(location, str):
                    key = location.strip().lower()
                    eff["location"] = location_aliases.get(key, location)
            elif eff_type == "move_item":
                for loc_key in ("from", "to"):
                    location = eff.get(loc_key)
                    if isinstance(location, str):
                        key = location.strip().lower()
                        eff[loc_key] = location_aliases.get(key, location)

                from_loc = eff.get("from")
                to_loc = eff.get("to")
                if to_loc == "_nowhere":
                    eff["type"] = "remove_item"
                    eff.pop("from", None)
                    eff.pop("to", None)
                elif eff.get("item") in npc_ids:
                    logger.warning(
                        "Dropping unsupported NPC move_item effect from command %s.",
                        cmd.get("id", "<unknown>"),
                    )
                    continue
                elif from_loc in container_ids and to_loc == "_inventory":
                    eff["type"] = "take_item_from_container"
                    eff.pop("from", None)
                    eff.pop("to", None)
                elif from_loc in container_ids and to_loc not in container_ids:
                    normalized_effects.append(
                        {
                            "type": "take_item_from_container",
                            "item": eff["item"],
                        }
                    )
                    normalized_effects.append(
                        {
                            "type": "move_item",
                            "item": eff["item"],
                            "from": "_inventory",
                            "to": to_loc,
                        }
                    )
                    continue
                elif to_loc in container_ids and from_loc in {"_inventory", "_current"}:
                    eff["type"] = "move_item_to_container"
                    eff.pop("from", None)
                    eff.pop("to", None)
            elif eff_type == "unlock":
                target = eff.get("lock")
                if target in lock_by_exit_id:
                    eff["lock"] = lock_by_exit_id[target]
                elif target in container_ids:
                    eff["type"] = "open_container"
                    eff["container"] = target
                    eff.pop("lock", None)

            normalized_effects.append(eff)

        cmd["effects"] = normalized_effects


def _validate_commands(
    commands: list[dict], flags: list[dict], context: dict
) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    room_ids = {r["id"] for r in context.get("rooms", [])}
    item_ids = {i["id"] for i in context.get("items", [])}
    npc_ids = {n["id"] for n in context.get("npcs", [])}
    lock_ids = {lock["id"] for lock in context.get("locks", [])}
    exit_ids = {e["id"] for e in context.get("exits", [])}
    puzzle_ids = {p["id"] for p in context.get("puzzles", [])}
    quest_ids = {q["id"] for q in context.get("quests", [])}
    flag_ids = {f["id"] for f in context.get("flags", [])}
    seen_ids: set[str] = set()
    errors: list[str] = []

    # Include newly generated flags so commands can reference them in the same pass.
    seen_flag_ids: set[str] = set()
    for flag in flags:
        fid = flag.get("id", "<missing>")
        if fid in seen_flag_ids:
            errors.append(f"Duplicate flag id: {fid}")
        seen_flag_ids.add(fid)
    flag_ids.update(seen_flag_ids)

    for cmd in commands:
        errors.extend(
            _validate_single_command(
                cmd,
                room_ids=room_ids,
                item_ids=item_ids,
                npc_ids=npc_ids,
                lock_ids=lock_ids,
                exit_ids=exit_ids,
                puzzle_ids=puzzle_ids,
                quest_ids=quest_ids,
                flag_ids=flag_ids,
                seen_ids=seen_ids,
            )
        )

    return errors


def _validate_single_command(
    cmd: dict,
    *,
    room_ids: set[str],
    item_ids: set[str],
    npc_ids: set[str],
    lock_ids: set[str],
    exit_ids: set[str],
    puzzle_ids: set[str],
    quest_ids: set[str],
    flag_ids: set[str],
    seen_ids: set[str],
) -> list[str]:
    """Return validation errors for a single command."""
    errors: list[str] = []
    cid = cmd.get("id", "<missing>")

    if cid in seen_ids:
        errors.append(f"Duplicate command id: {cid}")
    seen_ids.add(cid)

    if not cmd.get("verb"):
        errors.append(f"Command {cid} missing verb")

    pattern = cmd.get("pattern", "")
    verb = cmd.get("verb", "")
    if pattern and verb and not pattern.lower().startswith(verb.lower()):
        errors.append(
            f"Command {cid} pattern '{pattern}' does not start with verb '{verb}'"
        )

    ctx_rooms = cmd.get("context_room_ids")
    if ctx_rooms:
        if isinstance(ctx_rooms, list):
            for room_id in ctx_rooms:
                if room_id not in room_ids:
                    errors.append(
                        f"Command {cid} references unknown room in context_room_ids: {room_id}"
                    )
        elif isinstance(ctx_rooms, str) and ctx_rooms not in room_ids:
            errors.append(
                f"Command {cid} references unknown context_room_ids: {ctx_rooms}"
            )

    reference_findings: list[ValidationError] = []
    _validate_rule_preconditions(
        label=f"Command {cid}",
        category="command",
        preconds=cmd.get("preconditions", []),
        room_set=room_ids,
        item_set=item_ids,
        npc_set=npc_ids,
        lock_set=lock_ids,
        puzzle_set=puzzle_ids,
        flag_set=flag_ids,
        errors=reference_findings,
    )
    _validate_rule_effects(
        label=f"Command {cid}",
        category="command",
        effects=cmd.get("effects", []),
        room_set=room_ids,
        item_set=item_ids,
        lock_set=lock_ids,
        exit_set=exit_ids,
        puzzle_set=puzzle_ids,
        quest_set=quest_ids,
        flag_set=flag_ids,
        errors=reference_findings,
    )
    errors.extend(
        finding.message
        for finding in reference_findings
        if (
            finding.severity == "error"
            or "precondition has_item references unknown item" in finding.message
            or "effect move_item references unknown item" in finding.message
            or "effect move_item from=" in finding.message
            or "effect move_item to=" in finding.message
            or "effect spawn_item references unknown item" in finding.message
            or "effect spawn_item location" in finding.message
        )
    )

    if not cmd.get("failure_message"):
        errors.append(f"Command {cid} missing failure_message")

    return errors


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------


def _insert_commands(db: GameDB, commands: list[dict], context: dict) -> list[dict]:
    """Insert validated commands into the database.

    FK references (context_room_ids, puzzle_id) are checked against known
    IDs before insertion.  Invalid references are removed with a warning.

    Returns the list of successfully inserted commands.
    """
    room_ids = {r["id"] for r in context.get("rooms", [])}
    puzzle_ids = {p["id"] for p in context.get("puzzles", [])}
    inserted: list[dict] = []

    for cmd in commands:
        cid = cmd.get("id", "<unknown>")

        # --- Validate context_room_ids (nullable, JSON array of room IDs) ---
        ctx_rooms = cmd.get("context_room_ids")
        if ctx_rooms is not None:
            if isinstance(ctx_rooms, list):
                valid_rooms = [r for r in ctx_rooms if r in room_ids]
                invalid = [r for r in ctx_rooms if r not in room_ids]
                for r in invalid:
                    logger.warning(
                        "Command %s references non-existent room %r in "
                        "context_room_ids — removing",
                        cid,
                        r,
                    )
                cmd["context_room_ids"] = valid_rooms if valid_rooms else None
            elif isinstance(ctx_rooms, str):
                # Legacy single-string form
                if ctx_rooms not in room_ids:
                    logger.warning(
                        "Command %s references non-existent context_room_ids %r — "
                        "setting to NULL",
                        cid,
                        ctx_rooms,
                    )
                    cmd["context_room_ids"] = None
                else:
                    cmd["context_room_ids"] = [ctx_rooms]

        # --- Validate puzzle_id (nullable FK) ---
        puz_id = cmd.get("puzzle_id")
        if puz_id is not None and puz_id not in puzzle_ids:
            logger.warning(
                "Command %s references non-existent puzzle_id %r — "
                "setting to NULL",
                cid,
                puz_id,
            )
            cmd["puzzle_id"] = None

        ctx_value = cmd.get("context_room_ids")
        if isinstance(ctx_value, list):
            ctx_value = json.dumps(ctx_value) if ctx_value else None

        db.insert_command(
            id=cmd["id"],
            verb=cmd["verb"],
            pattern=cmd["pattern"],
            preconditions=json.dumps(cmd.get("preconditions", [])),
            effects=json.dumps(cmd.get("effects", [])),
            success_message=cmd.get("success_message", ""),
            failure_message=cmd.get("failure_message", ""),
            context_room_ids=ctx_value,
            puzzle_id=cmd.get("puzzle_id"),
            priority=cmd.get("priority", 0),
            is_enabled=1,
            one_shot=cmd.get("one_shot", 0),
            executed=0,
            done_message=cmd.get("done_message", ""),
        )
        inserted.append(cmd)

    return inserted


def _insert_flags(db: GameDB, flags: list[dict]) -> None:
    """Insert flag definitions into the database."""
    for flag in flags:
        db.insert_flag(
            id=flag["id"],
            value="false",
            description=flag.get("description", ""),
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_pass(db: GameDB, provider: BaseProvider, context: dict) -> dict:
    """Run Pass 7: Commands.  Returns updated context with command data."""

    logger.info("Pass 7: Generating commands...")

    intents = context.get("_command_intents")
    if intents is None:
        intents_prompt = _build_intents_prompt(context)
        intents_ctx = GenerationContext(
            existing_data={},
            seed=context.get("seed"),
            temperature=0.8,
            max_tokens=16_384,
        )
        logger.info(
            "Pass 7 [intents]: building interaction intents for %d rooms, %d items, "
            "%d NPCs, %d locks, and %d puzzles.",
            len(context.get("rooms", [])),
            len(context.get("items", [])),
            len(context.get("npcs", [])),
            len(context.get("locks", [])),
            len(context.get("puzzles", [])),
        )
        intents_result, intents_elapsed = _generate_stage(
            provider,
            stage="intents",
            prompt=intents_prompt,
            schema=COMMAND_INTENTS_SCHEMA,
            gen_ctx=intents_ctx,
            context=context,
        )
        intents = intents_result.get("intents", [])
        context["_command_intents"] = intents
        logger.info(
            "Pass 7 [intents]: generated %d intents in %.2fs.",
            len(intents),
            intents_elapsed,
        )
    else:
        logger.info(
            "Pass 7 [intents]: reusing %d cached intents from prior attempt.",
            len(intents),
        )

    compile_prompt = _build_compile_prompt(context, intents)
    compile_ctx = GenerationContext(
        existing_data={"intents": intents},
        seed=context.get("seed"),
        temperature=0.4,
        max_tokens=32_768,
    )

    logger.info(
        "Pass 7 [compile]: compiling %d intents into strict DSL.",
        len(intents),
    )
    result, compile_elapsed = _generate_stage(
        provider,
        stage="compile",
        prompt=compile_prompt,
        schema=COMMANDS_SCHEMA,
        gen_ctx=compile_ctx,
        context=context,
        extra_artifact_payload={"intents": intents},
    )
    commands: list[dict] = result.get("commands", [])
    flags: list[dict] = result.get("flags", [])
    logger.info(
        "Pass 7 [compile]: provider returned %d commands and %d flags in %.2fs.",
        len(commands),
        len(flags),
        compile_elapsed,
    )

    _normalize_command_aliases(commands, context)

    # Validate
    errors = _validate_commands(commands, flags, context)
    if errors:
        artifact_path = _persist_command_debug_artifact(
            "compile-validation",
            context,
            {
                "stage": "compile-validation",
                "seed": context.get("seed"),
                "error_count": len(errors),
                "errors": errors,
                "intents": intents,
                "commands": commands,
                "flags": flags,
                "prompt": compile_prompt,
            },
        )
        preview = "; ".join(errors[:8])
        raise ValueError(
            f"Command validation failed: {preview}. "
            f"Debug artifact written to {artifact_path}."
        )

    # Insert flags first (commands may reference them)
    _insert_flags(db, flags)

    # Insert commands (with FK validation)
    inserted_commands = _insert_commands(db, commands, context)

    # Build pass-specific data for downstream passes (only inserted commands)
    commands_summary = [
        {
            "id": c["id"],
            "verb": c["verb"],
            "pattern": c["pattern"],
            "context_room_ids": c.get("context_room_ids"),
            "one_shot": c.get("one_shot", 0),
        }
        for c in inserted_commands
    ]
    flags_summary = [
        {"id": f["id"], "description": f.get("description", "")} for f in flags
    ]

    logger.info(
        "Pass 7 complete: %d commands and %d flags generated.",
        len(inserted_commands),
        len(flags),
    )
    return {"commands": commands_summary, "flags": flags_summary}
