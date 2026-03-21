# AnyZork World Schema Reference

This document describes the current logical schema of a `.zork` file.

The executable SQL source of truth lives in [anyzork/db/schema.py](../../anyzork/db/schema.py). This document is the human-oriented companion: table purpose, major relationships, and field families.

## 1. Schema Overview

| Table | Purpose |
|---|---|
| `metadata` | Game-level metadata, intro/outro text, win/lose conditions, and authoring metadata |
| `rooms` | Discrete locations |
| `exits` | One-way room connections |
| `items` | World objects, including containers, toggles, consumables, and inventory items |
| `npcs` | Non-player characters |
| `dialogue_nodes` | NPC dialogue tree nodes |
| `dialogue_options` | Player-facing choices within dialogue nodes |
| `locks` | Exit gating rules |
| `puzzles` | Puzzle definitions and completion state |
| `commands` | Player-initiated DSL rules |
| `flags` | Shared world-state variables |
| `quests` | Quest headers and status |
| `quest_objectives` | Trackable quest steps |
| `player` | Single-row runtime state |
| `score_entries` | Runtime score log |
| `visited_rooms` | First-visit tracking |
| `interaction_responses` | Tag/category interaction templates |
| `triggers` | Reactive rules fired by engine events |

## 2. Relationship Map

```text
metadata

rooms <- exits -> rooms
rooms <- items
rooms <- npcs
rooms <- puzzles

items <- items              (container nesting)
items <- locks             (key items)
items <- interaction_responses (via tags/categories at runtime)

npcs <- dialogue_nodes <- dialogue_options

exits <- locks
puzzles <- locks
puzzles <- commands

flags <- commands
flags <- dialogue_nodes
flags <- dialogue_options
flags <- locks
flags <- quests
flags <- quest_objectives
flags <- triggers

quests <- quest_objectives

commands -> triggers       (shared effect/precondition vocabulary, event emission)
player / score_entries / visited_rooms track runtime state
```

## 3. Table Summaries

### `metadata`

Single-row game metadata.

Key fields:

- `title`, `author_prompt`, `seed`, `created_at`, `version`
- `app_version`, `prompt_system_version`
- `intro_text`, `win_text`, `lose_text`
- `win_conditions`, `lose_conditions`
- `max_score`, `region_count`, `room_count`
- `realism`
- `game_id`, `source_game_id`, `source_path`, `save_slot`, `last_played_at`, `is_template`

### `rooms`

Core spatial units.

Key fields:

- `id`, `name`
- `description`, `short_description`, `first_visit_text`
- `region`
- `is_dark`, `is_start`, `visited`

### `exits`

Directional or named room links.

Key fields:

- `from_room_id`, `to_room_id`, `direction`
- `description`
- `is_locked`, `is_hidden`

### `items`

The most feature-rich table in the schema. Items can be scenery, takeable objects, containers, keys, toggles, stackables, or realism-aware tools.

Major field groups:

- Core identity: `id`, `name`, `description`, `examine_description`
- Placement: `room_id`, `container_id`, `home_room_id`
- Visibility and portability: `is_takeable`, `is_visible`, `is_consumed_on_use`
- Containers: `is_container`, `is_open`, `has_lid`, `is_locked`, `lock_message`, `key_item_id`, `consume_key`, `accepts_items`, `reject_message`
- Messaging: `take_message`, `drop_message`, `open_message`, `search_message`, `unlock_message`, `drop_description`, `room_description`, `read_description`
- Physical: `weight`
- Toggle/state system: `is_toggleable`, `toggle_state`, `toggle_states`, `toggle_messages`, `toggle_on_message`, `toggle_off_message`
- Dependencies: `requires_item_id`, `requires_message`
- Quantities: `quantity`, `max_quantity`, `quantity_unit`, `depleted_message`, `quantity_description`
- Interaction taxonomy: `category`, `item_tags`

Constraint of note:

- an item cannot be in both a room and a container at once

### `npcs`

NPC placement and baseline behavior.

Key fields:

- `id`, `name`, `description`, `examine_description`
- `room_id`
- `is_alive`
- blocking/gating support: `is_blocking`, `blocked_exit_id`, `unblock_flag`
- baseline dialogue: `default_dialogue`
- optional combat stats: `hp`, `damage`
- `category`

### `dialogue_nodes`

Structured conversation nodes.

Key fields:

- `npc_id`
- `content`
- `set_flags`
- `is_root`

### `dialogue_options`

Player choices branching from dialogue nodes.

Key fields:

- `node_id`, `text`, `next_node_id`
- `required_flags`, `excluded_flags`
- `required_items`
- `set_flags`
- `sort_order`

### `locks`

Exit-gating records.

Key fields:

- `lock_type`
- `target_exit_id`
- `key_item_id`, `puzzle_id`, `combination`
- `required_flags`
- `locked_message`, `unlock_message`
- `is_locked`, `consume_key`

### `puzzles`

Trackable puzzle definitions.

Key fields:

- `name`, `description`
- `room_id`
- `is_solved`
- `solution_steps`
- `hint_text`
- `difficulty`, `score_value`, `is_optional`

### `commands`

Player-typed DSL rules.

Key fields:

- `verb`, `pattern`
- `preconditions`, `effects`
- `success_message`, `failure_message`, `done_message`
- `context_room_ids`
- `puzzle_id`
- `priority`
- `is_enabled`, `one_shot`, `executed`

See [docs/dsl/COMMANDS.md](../dsl/COMMANDS.md) for the runtime vocabulary.

### `flags`

Shared state variables used by nearly every other system.

Key fields:

- `id`
- `value`
- `description`

### `quests`

Player-facing quest headers.

Key fields:

- `name`, `description`
- `quest_type` (`main` or `side`)
- `status`
- `discovery_flag`
- `completion_flag`
- `score_value`
- `sort_order`

### `quest_objectives`

Trackable quest steps.

Key fields:

- `quest_id`
- `description`
- `completion_flag`
- `order_index`
- `is_optional`
- `bonus_score`

### `player`

Single-row runtime state.

Key fields:

- `current_room_id`
- `hp`, `max_hp`
- `score`
- `moves`
- `game_state`

### `score_entries`

Append-only runtime score log.

Key fields:

- `reason`
- `value`
- `move_number`

### `visited_rooms`

Tracks when the player first entered each room.

Key fields:

- `room_id`
- `first_visit`

### `interaction_responses`

Generic interaction templates used by the item dynamics system.

Key fields:

- `item_tag`
- `target_category`
- `response`
- `consumes`
- `score_change`
- `flag_to_set`
- `effects`

### `triggers`

Reactive rules that fire on emitted events.

Key fields:

- `event_type`
- `event_data`
- `preconditions`, `effects`
- `message`
- `priority`
- `one_shot`, `executed`, `is_enabled`

## 4. Design Notes

- `flags` are the shared glue between commands, dialogue, locks, quests, and triggers.
- Quests are a tracking layer on top of flags, not a separate gating system.
- Triggers reuse the same precondition/effect vocabulary as commands, but they execute reactively.
- Containers, toggle states, and quantities all live in `items` so the runtime can stay deterministic.
- Runtime progress is persisted directly into the same `.zork` file; there is no separate save file format.

## 5. Validation Priorities

When updating generation or runtime code, keep these invariants true:

- references always point to valid rows
- one-shot content persists its execution state
- score metadata remains internally consistent
- lock solutions remain reachable
- quest and trigger flags line up with actual command/dialogue behavior

If you need exact defaults, constraints, or index names, inspect [anyzork/db/schema.py](../../anyzork/db/schema.py).
