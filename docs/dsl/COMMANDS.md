# Command DSL Specification

## 1. Overview

### What This Is

The Command DSL is the rule system that defines every interactive verb in an AnyZork game. Each command is a JSON object containing a **verb**, a **pattern** for matching player input, a set of **preconditions** that must all be true for the command to fire, and an ordered list of **effects** that mutate game state when it does.

### Why It Exists

The LLM generates commands during world-building. The deterministic engine evaluates them at play-time. No LLM runs at runtime. This separation guarantees:

- **No hallucination** — a command either matches its preconditions or it doesn't. The engine never invents behavior.
- **No state drift** — effects are atomic mutations against a SQLite database. Game state is always consistent.
- **No security risk** — commands are data, not executable code. The engine interprets a closed set of effect types.

### Top-Level Command Structure

```json
{
  "id": "use_rusty_key_on_dungeon_door",
  "verb": "use",
  "pattern": "use {item} on {target}",
  "preconditions": [ ... ],
  "effects": [ ... ],
  "success_message": "The key turns with a grinding screech.",
  "failure_message": "That doesn't seem to work.",
  "done_message": "You already did that.",
  "priority": 0,
  "context_room_ids": ["dungeon_entrance"],
  "one_shot": false
}
```

| Field              | Type     | Required | Description |
|--------------------|----------|----------|-------------|
| `id`               | string   | yes      | Unique identifier for this command. Snake_case. Must be unique across the entire game. |
| `verb`             | string   | yes      | The first word of the player's input that triggers pattern matching. Lowercased. |
| `pattern`          | string   | yes      | The full input pattern including `{slot}` placeholders. Must start with the verb. |
| `preconditions`    | array    | yes      | Array of precondition objects. ALL must be satisfied for the command to fire. May be empty `[]` for unconditional commands. |
| `effects`          | array    | yes      | Ordered array of effect objects. Executed sequentially when all preconditions pass. |
| `success_message`  | string   | no       | Message displayed when the command succeeds, before effects run. Supports `{slot}` references. Defaults to empty. |
| `failure_message`  | string   | no       | Message printed when preconditions are not met. If omitted, the engine uses a generic failure message. |
| `done_message`     | string   | no       | Message displayed when a one-shot command has already been executed. Only meaningful when `one_shot` is `true`. Defaults to empty. |
| `priority`         | integer  | no       | Commands with higher priority are tried first during resolution. Defaults to `0`. Among equal-priority commands, fewer slots (more specific patterns) win. |
| `context_room_ids` | array    | no       | JSON array of room IDs this command is scoped to. If `null` or omitted, the command is global (matches in any room). When set, the command is only a candidate when the player is in one of the listed rooms. |
| `one_shot`         | boolean  | no       | If `true`, this command can only fire once. Defaults to `false`. See section 5. |

---

## 2. Pattern Matching

### How It Works

When the player types input, the engine:

1. **Extracts the verb** — the first whitespace-delimited word, lowercased.
2. **Finds candidate commands** — all enabled commands whose `verb` field matches, filtered to those whose `context_room_ids` include the player's current room (or are global, i.e., `context_room_ids` is `null`).
3. **Sorts by priority** — candidates are sorted by `priority` descending, then by specificity (fewer slots = more specific) ascending. Ties preserve database insertion order.
4. **Matches patterns** — for each candidate in priority order, attempts to match the full input against the command's `pattern`. Slots (`{slot}`) capture one or more words. Literal words must match exactly (case-insensitive).
5. **Skips executed one-shots** — if the matching command is a one-shot that has already executed, its `done_message` (if any) is saved as a fallback and the engine moves to the next candidate.
6. **Evaluates preconditions** — checks all preconditions using the captured slot values. The first command whose preconditions all pass is the one that fires.
7. **Executes effects** — runs the matched command's effects in order. If the command has a `success_message`, it is displayed before effects run.

### Slot Extraction

Slots are named placeholders wrapped in curly braces: `{slot_name}`. Each slot captures one or more contiguous words from the player's input. Slot names must be lowercase alphanumeric with underscores.

The captured value is normalized: lowercased, trimmed, and matched against item/NPC/room IDs using the game's alias table. For example, if the player types `use rusty key on iron door`, and the item with ID `rusty_key` has the alias `rusty key`, then `{item}` resolves to `rusty_key`.

### Pattern Examples

| Pattern | Matches | Slot Values |
|---------|---------|-------------|
| `look` | "look" | (none) |
| `look at {target}` | "look at old painting" | target = "old_painting" |
| `use {item} on {target}` | "use rusty key on dungeon door" | item = "rusty_key", target = "dungeon_door" |
| `talk to {npc}` | "talk to old wizard" | npc = "old_wizard" |
| `give {item} to {npc}` | "give golden coin to merchant" | item = "golden_coin", npc = "merchant" |
| `push {target}` | "push statue" | target = "statue" |
| `combine {item} with {item2}` | "combine lens with frame" | item = "lens", item2 = "frame" |
| `pull {target}` | "pull lever" | target = "lever" |

### Verb Conventions

Common verbs and their typical usage:

| Verb | Typical Patterns | Purpose |
|------|-----------------|---------|
| `look` | `look`, `look at {target}` | Examine surroundings or specific objects |
| `take` | `take {item}`, `take {item} from {target}` | Pick up items |
| `drop` | `drop {item}` | Leave an item in the current room |
| `use` | `use {item}`, `use {item} on {target}` | Interact with or apply items |
| `open` | `open {target}`, `open {target} with {item}` | Open doors, chests, containers |
| `talk` | `talk to {npc}` | Initiate NPC conversation |
| `give` | `give {item} to {npc}` | Hand an item to an NPC |
| `go` | `go {direction}` | Move through an exit |
| `examine` | `examine {target}` | Detailed inspection (synonym handling maps this to `look at`) |
| `combine` | `combine {item} with {item2}` | Merge two inventory items |
| `push` | `push {target}` | Physical interaction with scenery |
| `pull` | `pull {target}` | Physical interaction with scenery |
| `read` | `read {target}` | Read inscriptions, books, notes |
| `ask` | `ask {npc} about {target}` | Query an NPC about a topic |

---

## 3. Precondition Types

Every precondition is a JSON object with a `type` field and type-specific parameters. ALL preconditions in a command's array must evaluate to `true` for the command to fire.

### 3.1 `in_room`

The player must be in a specific room.

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `type`  | string | yes      | `"in_room"` |
| `room`  | string | yes      | The room ID the player must currently occupy. |

```json
{
  "type": "in_room",
  "room": "dungeon_entrance"
}
```

### 3.2 `has_item`

The player must have a specific item in their inventory.

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `type`  | string | yes      | `"has_item"` |
| `item`  | string | yes      | The item ID that must be in the player's inventory. Supports `{slot}` references to bind to a slot captured from the pattern. |

```json
{
  "type": "has_item",
  "item": "rusty_key"
}
```

With slot reference (the item comes from pattern matching):

```json
{
  "type": "has_item",
  "item": "{item}"
}
```

### 3.3 `has_flag`

A world-state flag must be set (truthy).

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `type`  | string | yes      | `"has_flag"` |
| `flag`  | string | yes      | The flag name that must be set. |

```json
{
  "type": "has_flag",
  "flag": "spoke_to_wizard"
}
```

### 3.4 `not_flag`

A world-state flag must NOT be set (falsy or absent).

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `type`  | string | yes      | `"not_flag"` |
| `flag`  | string | yes      | The flag name that must NOT be set. |

```json
{
  "type": "not_flag",
  "flag": "bridge_destroyed"
}
```

### 3.5 `item_in_room`

A specific item must be present in a specific room (not in anyone's inventory).

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `type`  | string | yes      | `"item_in_room"` |
| `item`  | string | yes      | The item ID. |
| `room`  | string | yes      | The room ID where the item must be located. Use `"_current"` for the player's current room. |

```json
{
  "type": "item_in_room",
  "item": "ancient_tome",
  "room": "_current"
}
```

### 3.6 `npc_in_room`

A specific NPC must be present in a specific room and alive. Dead NPCs fail this check.

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `type`  | string | yes      | `"npc_in_room"` |
| `npc`   | string | yes      | The NPC ID. Supports `{slot}` references. |
| `room`  | string | yes      | The room ID. Use `"_current"` for the player's current room. |

```json
{
  "type": "npc_in_room",
  "npc": "old_wizard",
  "room": "_current"
}
```

### 3.7 `lock_unlocked`

A specific lock must already be in the unlocked state.

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `type`  | string | yes      | `"lock_unlocked"` |
| `lock`  | string | yes      | The lock ID that must be unlocked. |

```json
{
  "type": "lock_unlocked",
  "lock": "dungeon_door_lock"
}
```

### 3.8 `puzzle_solved`

A specific puzzle must have been solved.

| Field    | Type   | Required | Description |
|----------|--------|----------|-------------|
| `type`   | string | yes      | `"puzzle_solved"` |
| `puzzle` | string | yes      | The puzzle ID that must be in the solved state. |

```json
{
  "type": "puzzle_solved",
  "puzzle": "mirror_alignment"
}
```

### 3.9 `health_above`

The player's health must be above a threshold.

| Field       | Type    | Required | Description |
|-------------|---------|----------|-------------|
| `type`      | string  | yes      | `"health_above"` |
| `threshold` | integer | yes      | The minimum health value (exclusive). The player's health must be strictly greater than this number. |

```json
{
  "type": "health_above",
  "threshold": 0
}
```

### 3.10 `item_accessible`

An item must be accessible to the player — meaning it is visible and either in the player's inventory, loose in the current room, or inside an open, accessible container in inventory or the current room. The engine walks the container chain to verify accessibility.

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `type`  | string | yes      | `"item_accessible"` |
| `item`  | string | yes      | The item ID. Supports `{slot}` references. |

```json
{
  "type": "item_accessible",
  "item": "{item}"
}
```

### 3.11 `container_open`

A container item must be in the open state (or have no lid).

| Field       | Type   | Required | Description |
|-------------|--------|----------|-------------|
| `type`      | string | yes      | `"container_open"` |
| `container` | string | yes      | The container item ID. Supports `{slot}` references. |

```json
{
  "type": "container_open",
  "container": "wooden_chest"
}
```

### 3.12 `item_in_container`

A specific visible item must be inside a specific container.

| Field       | Type   | Required | Description |
|-------------|--------|----------|-------------|
| `type`      | string | yes      | `"item_in_container"` |
| `item`      | string | yes      | The item ID. Supports `{slot}` references. |
| `container` | string | yes      | The container item ID. Supports `{slot}` references. |

```json
{
  "type": "item_in_container",
  "item": "gold_coin",
  "container": "wooden_chest"
}
```

### 3.13 `not_item_in_container`

A specific visible item must NOT be inside a specific container. The inverse of `item_in_container`.

| Field       | Type   | Required | Description |
|-------------|--------|----------|-------------|
| `type`      | string | yes      | `"not_item_in_container"` |
| `item`      | string | yes      | The item ID. Supports `{slot}` references. |
| `container` | string | yes      | The container item ID. Supports `{slot}` references. |

```json
{
  "type": "not_item_in_container",
  "item": "gold_coin",
  "container": "wooden_chest"
}
```

### 3.14 `container_has_contents`

A container must have at least one visible item inside it.

| Field       | Type   | Required | Description |
|-------------|--------|----------|-------------|
| `type`      | string | yes      | `"container_has_contents"` |
| `container` | string | yes      | The container item ID. Supports `{slot}` references. |

```json
{
  "type": "container_has_contents",
  "container": "wooden_chest"
}
```

### 3.15 `container_empty`

A container must have no visible items inside it.

| Field       | Type   | Required | Description |
|-------------|--------|----------|-------------|
| `type`      | string | yes      | `"container_empty"` |
| `container` | string | yes      | The container item ID. Supports `{slot}` references. |

```json
{
  "type": "container_empty",
  "container": "wooden_chest"
}
```

### 3.16 `has_quantity`

An item must have at least a minimum number of charges/uses remaining.

| Field   | Type    | Required | Description |
|---------|---------|----------|-------------|
| `type`  | string  | yes      | `"has_quantity"` |
| `item`  | string  | yes      | The item ID. Supports `{slot}` references. |
| `min`   | integer | no       | The minimum quantity required. Defaults to `1`. |

```json
{
  "type": "has_quantity",
  "item": "healing_herbs",
  "min": 3
}
```

### 3.17 `toggle_state`

An item's toggle state must match a specific value.

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `type`  | string | yes      | `"toggle_state"` |
| `item`  | string | yes      | The item ID. Supports `{slot}` references. |
| `state` | string | yes      | The required toggle state (e.g., `"on"`, `"off"`, `"open"`). Supports `{slot}` references. Items without a toggle state are treated as `"off"`. |

```json
{
  "type": "toggle_state",
  "item": "wall_switch",
  "state": "on"
}
```

### Slot References in Preconditions

Any string field in a precondition can reference a captured slot by wrapping the slot name in curly braces. The engine substitutes the resolved value before evaluation.

```json
{
  "type": "has_item",
  "item": "{item}"
}
```

If the player typed `use torch on brazier` and the pattern is `use {item} on {target}`, then `{item}` resolves to the item ID matching "torch" (e.g., `wooden_torch`).

---

## 4. Effect Types

Effects are JSON objects with a `type` field and type-specific parameters. Effects execute in array order. If any effect fails (e.g., trying to remove an item the player doesn't have), the engine logs a warning but continues executing remaining effects.

### 4.1 `move_item`

Moves an item from one location to another. Locations can be a room ID, `"_inventory"` (player's inventory), or `"_current"` (player's current room).

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"move_item"` |
| `item` | string | yes      | The item ID to move. Supports `{slot}` references. |
| `from` | string | yes      | Source location: a room ID, `"_inventory"`, or `"_current"`. |
| `to`   | string | yes      | Destination location: a room ID, `"_inventory"`, or `"_current"`. |

```json
{
  "type": "move_item",
  "item": "silver_chalice",
  "from": "altar_room",
  "to": "_inventory"
}
```

### 4.2 `remove_item`

Permanently removes an item from the game. The item ceases to exist — it is not moved, it is destroyed.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"remove_item"` |
| `item` | string | yes      | The item ID to destroy. Supports `{slot}` references. |

```json
{
  "type": "remove_item",
  "item": "rusty_key"
}
```

### 4.3 `set_flag`

Sets a world-state flag. Flags are boolean markers used by preconditions (`has_flag`, `not_flag`) to track permanent state changes.

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `type`  | string | yes      | `"set_flag"` |
| `flag`  | string | yes      | The flag name to set. |
| `value` | boolean | no      | The value to set. Defaults to `true`. Set to `false` to unset a flag. |

```json
{
  "type": "set_flag",
  "flag": "dungeon_door_opened"
}
```

Unsetting a flag:

```json
{
  "type": "set_flag",
  "flag": "torch_lit",
  "value": false
}
```

### 4.4 `unlock`

Unlocks a lock, allowing passage through the associated exit.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"unlock"` |
| `lock` | string | yes      | The lock ID to unlock. |

```json
{
  "type": "unlock",
  "lock": "dungeon_door_lock"
}
```

### 4.5 `move_player`

Moves the player to a different room.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"move_player"` |
| `room` | string | yes      | The destination room ID. |

```json
{
  "type": "move_player",
  "room": "throne_room"
}
```

### 4.6 `spawn_item`

Creates a new item instance in a location. Used when an item should appear that didn't exist before (e.g., an NPC hands you something, or a puzzle produces a reward).

| Field         | Type   | Required | Description |
|---------------|--------|----------|-------------|
| `type`        | string | yes      | `"spawn_item"` |
| `item`        | string | yes      | The item ID to create. This item must be defined in the items table (it exists in the database but was not yet placed in the world). |
| `location`    | string | yes      | Where to place it: a room ID, `"_inventory"`, `"_current"`, or a container item ID. If the location matches an existing container item, the spawned item is placed inside that container. |

```json
{
  "type": "spawn_item",
  "item": "enchanted_amulet",
  "location": "_inventory"
}
```

### 4.7 `change_health`

Modifies the player's health by a relative amount.

| Field    | Type    | Required | Description |
|----------|---------|----------|-------------|
| `type`   | string  | yes      | `"change_health"` |
| `amount` | integer | yes      | The amount to add (positive) or subtract (negative). Health is clamped to `[0, max_health]`. |

```json
{
  "type": "change_health",
  "amount": -10
}
```

Healing:

```json
{
  "type": "change_health",
  "amount": 25
}
```

### 4.8 `add_score`

Adds points to the player's score.

| Field    | Type    | Required | Description |
|----------|---------|----------|-------------|
| `type`   | string  | yes      | `"add_score"` |
| `points` | integer | yes      | The number of points to add. Must be positive. |

```json
{
  "type": "add_score",
  "points": 10
}
```

### 4.9 `reveal_exit`

Makes a hidden exit visible and traversable. The exit must already exist in the database with a `hidden` flag.

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `type`  | string | yes      | `"reveal_exit"` |
| `exit`  | string | yes      | The exit ID to reveal. |

```json
{
  "type": "reveal_exit",
  "exit": "library_secret_passage"
}
```

### 4.10 `solve_puzzle`

Marks a puzzle as solved. This is a permanent state change that can be checked by `puzzle_solved` preconditions on other commands.

| Field    | Type   | Required | Description |
|----------|--------|----------|-------------|
| `type`   | string | yes      | `"solve_puzzle"` |
| `puzzle` | string | yes      | The puzzle ID to mark as solved. |

```json
{
  "type": "solve_puzzle",
  "puzzle": "crystal_alignment"
}
```

### 4.11 `discover_quest`

Discovers a quest by setting its discovery flag. This causes the quest to appear in the player's quest log on the next engine tick.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"discover_quest"` |
| `quest` | string | yes      | The quest ID to discover. |

```json
{
  "type": "discover_quest",
  "quest": "the_hermits_bargain"
}
```

### 4.12 `print`

Displays a message to the player. This is the primary way commands communicate results.

| Field     | Type   | Required | Description |
|-----------|--------|----------|-------------|
| `type`    | string | yes      | `"print"` |
| `message` | string | yes      | The text to display. Supports `{slot}` references for dynamic text. |

```json
{
  "type": "print",
  "message": "The rusty key turns with a grinding screech. The dungeon door swings open, revealing darkness beyond."
}
```

With slot reference:

```json
{
  "type": "print",
  "message": "You show the {item} to the merchant. His eyes widen."
}
```

### 4.13 `open_container`

Opens a container, allowing items inside to be seen and taken.

| Field       | Type   | Required | Description |
|-------------|--------|----------|-------------|
| `type`      | string | yes      | `"open_container"` |
| `container` | string | yes      | The container item ID. Supports `{slot}` references. |

```json
{
  "type": "open_container",
  "container": "wooden_chest"
}
```

### 4.14 `move_item_to_container`

Places an item inside a container. If the container rejects the item (e.g., full or wrong type), a rejection message is returned.

| Field       | Type   | Required | Description |
|-------------|--------|----------|-------------|
| `type`      | string | yes      | `"move_item_to_container"` |
| `item`      | string | yes      | The item ID. Supports `{slot}` references. |
| `container` | string | yes      | The container item ID. Supports `{slot}` references. |

```json
{
  "type": "move_item_to_container",
  "item": "gold_coin",
  "container": "leather_pouch"
}
```

### 4.15 `take_item_from_container`

Removes an item from its container and places it in the player's inventory.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"take_item_from_container"` |
| `item` | string | yes      | The item ID. Supports `{slot}` references. |

```json
{
  "type": "take_item_from_container",
  "item": "gold_coin"
}
```

### 4.16 `consume_quantity`

Consumes a number of charges or uses from a quantity-tracked item.

| Field    | Type    | Required | Description |
|----------|---------|----------|-------------|
| `type`   | string  | yes      | `"consume_quantity"` |
| `item`   | string  | yes      | The item ID. Supports `{slot}` references. |
| `amount` | integer | no       | Number of charges to consume. Defaults to `1`. |

```json
{
  "type": "consume_quantity",
  "item": "healing_herbs",
  "amount": 1
}
```

### 4.17 `restore_quantity`

Restores charges or uses on a quantity-tracked item.

| Field    | Type    | Required | Description |
|----------|---------|----------|-------------|
| `type`   | string  | yes      | `"restore_quantity"` |
| `item`   | string  | yes      | The item ID. Supports `{slot}` references. |
| `amount` | integer | no       | Number of charges to restore. Defaults to `1`. |
| `source` | string  | no       | An optional source item ID. Supports `{slot}` references. |

```json
{
  "type": "restore_quantity",
  "item": "lantern",
  "amount": 5,
  "source": "oil_flask"
}
```

### 4.18 `set_toggle_state`

Changes an item's toggle state to a new value (e.g., "on"/"off", "open"/"closed").

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `type`  | string | yes      | `"set_toggle_state"` |
| `item`  | string | yes      | The item ID. Supports `{slot}` references. |
| `state` | string | yes      | The new toggle state. Supports `{slot}` references. |

```json
{
  "type": "set_toggle_state",
  "item": "wall_switch",
  "state": "on"
}
```

### 4.19 `move_npc`

Relocates an NPC to a different room.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"move_npc"` |
| `npc`  | string | yes      | The NPC ID. Supports `{slot}` references. |
| `room` | string | yes      | The destination room ID. Supports `{slot}` references. |

```json
{
  "type": "move_npc",
  "npc": "old_wizard",
  "room": "tower_top"
}
```

### 4.20 `make_visible`

Makes a hidden item visible. The item remains in its current location but becomes visible to the player.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"make_visible"` |
| `item` | string | yes      | The item ID. Supports `{slot}` references. |

```json
{
  "type": "make_visible",
  "item": "hidden_lever"
}
```

### 4.21 `make_hidden`

Makes a visible item hidden. The item remains in its current location but becomes invisible to the player.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"make_hidden"` |
| `item` | string | yes      | The item ID. Supports `{slot}` references. |

```json
{
  "type": "make_hidden",
  "item": "trapdoor"
}
```

### 4.22 `make_takeable`

Makes an item takeable. Useful for items that start as scenery and become collectible after an interaction.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"make_takeable"` |
| `item` | string | yes      | The item ID. Supports `{slot}` references. |

```json
{
  "type": "make_takeable",
  "item": "loose_brick"
}
```

### 4.23 `fail_quest`

Marks a quest as failed.

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `type`  | string | yes      | `"fail_quest"` |
| `quest` | string | yes      | The quest ID to fail. Supports `{slot}` references. |

```json
{
  "type": "fail_quest",
  "quest": "rescue_the_prisoner"
}
```

### 4.24 `complete_quest`

Marks a quest as completed. If the quest has a `completion_flag`, that flag is set. If the quest has a `score_value`, points are awarded.

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `type`  | string | yes      | `"complete_quest"` |
| `quest` | string | yes      | The quest ID to complete. Supports `{slot}` references. |

```json
{
  "type": "complete_quest",
  "quest": "seal_the_mountain_gate"
}
```

### 4.25 `kill_npc`

Kills a specific NPC, marking them as dead.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"kill_npc"` |
| `npc`  | string | yes      | The NPC ID. Supports `{slot}` references. |

```json
{
  "type": "kill_npc",
  "npc": "cave_troll"
}
```

### 4.26 `remove_npc`

Permanently removes an NPC from the game.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"remove_npc"` |
| `npc`  | string | yes      | The NPC ID. Supports `{slot}` references. |

```json
{
  "type": "remove_npc",
  "npc": "phantom"
}
```

### 4.27 `lock_exit`

Locks an exit, preventing traversal until unlocked.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"lock_exit"` |
| `exit` | string | yes      | The exit ID to lock. Supports `{slot}` references. |

```json
{
  "type": "lock_exit",
  "exit": "bridge_crossing"
}
```

### 4.28 `hide_exit`

Hides an exit, making it invisible and non-traversable until revealed again.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"hide_exit"` |
| `exit` | string | yes      | The exit ID to hide. Supports `{slot}` references. |

```json
{
  "type": "hide_exit",
  "exit": "secret_passage"
}
```

### 4.29 `change_description`

Changes the description text of any entity (room, item, NPC).

| Field    | Type   | Required | Description |
|----------|--------|----------|-------------|
| `type`   | string | yes      | `"change_description"` |
| `entity` | string | yes      | The entity ID. Supports `{slot}` references. |
| `text`   | string | yes      | The new description text. Supports `{slot}` references. |

```json
{
  "type": "change_description",
  "entity": "old_bookshelf",
  "text": "The bookshelf stands ajar, revealing a dark passage behind it."
}
```

### 4.30 `kill_target` (Interaction Only)

Kills the target NPC in an interaction response. Spawns a lootable body container.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"kill_target"` |

```json
{
  "type": "kill_target"
}
```

### 4.31 `damage_target` (Interaction Only)

Deals damage to the target NPC in an interaction response.

| Field    | Type    | Required | Description |
|----------|---------|----------|-------------|
| `type`   | string  | yes      | `"damage_target"` |
| `amount` | integer | yes      | Amount of damage to deal. |

```json
{
  "type": "damage_target",
  "amount": 25
}
```

### 4.32 `destroy_target` (Interaction Only)

Destroys the target container in an interaction response, scattering its contents into the room.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"destroy_target"` |

```json
{
  "type": "destroy_target"
}
```

### 4.33 `open_target` (Interaction Only)

Opens the target container in an interaction response.

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `type` | string | yes      | `"open_target"` |

```json
{
  "type": "open_target"
}
```

### Slot References in Effects

Just as with preconditions, any string field in an effect can use `{slot_name}` to reference a value captured from the pattern. The engine substitutes the resolved value before execution.

---

## 5. One-Shot Commands

Some commands should only fire once. A key can only unlock a door once. A quest discovery only happens once. An NPC's first greeting is different from subsequent ones.

Setting `"one_shot": true` on a command causes the engine to:

1. Execute the command normally the first time all preconditions are met.
2. After execution, set an internal `executed` flag on that command in the database.
3. On subsequent attempts, the engine skips this command. If the command has a `done_message`, that message is displayed as a fallback (the engine still verifies preconditions, excluding `not_flag` checks, before showing it). If no `done_message` is set, the command is silently skipped and resolution continues to lower-priority commands.

The `executed` flag is stored per-command in the commands table. It persists across save/load because the `.zork` file IS the save.

### When to Use One-Shot

- **Key-and-lock puzzles** — the key is consumed and the door opens. Should not repeat.
- **Quest discoveries** — finding the hermit's journal for the first time should only add the side quest once.
- **NPC quest hand-offs** — the wizard gives you the amulet once. Not every time you talk to him.
- **Puzzle solutions** — solving the mirror puzzle awards points once.
- **Trap triggers** — the floor collapses once.

### When NOT to Use One-Shot

- **Repeatable interactions** — looking at an item, reading a sign, talking to a generic NPC.
- **Consumable item use** — drinking a healing potion. The command itself repeats; the item's existence (or absence) naturally prevents it from firing once the potion is gone.
- **Navigation** — `go north` must always work.

### Example

```json
{
  "id": "read_hermits_journal",
  "verb": "read",
  "pattern": "read {target}",
  "preconditions": [
    { "type": "in_room", "room": "abandoned_hut" },
    { "type": "item_in_room", "item": "hermits_journal", "room": "_current" }
  ],
  "effects": [
    { "type": "discover_quest", "quest": "the_hermits_bargain" },
    { "type": "add_score", "points": 5 },
    { "type": "print", "message": "The journal describes a hermit trapped beyond the briar grove, willing to trade a hidden shortcut for a silver mirror." }
  ],
  "one_shot": true
}
```

The first time the player reads the journal, they discover the side quest, gain 5 points, and see the message. If they type `read journal` again, the engine skips this command. A separate, non-one-shot command can provide a shorter reminder message for repeat reads.

---

## 6. Chaining Effects

A single command can have multiple effects. The effects array is processed sequentially, top to bottom. This enables complex interactions in a single player action.

### Execution Order Matters

Effects execute in array order. This matters when one effect's outcome influences the narrative coherence of subsequent effects. Always place `print` effects at the position that makes narrative sense — often last, but sometimes interleaved.

### Example: Multi-Effect Sequence

```json
{
  "id": "drink_healing_potion",
  "verb": "use",
  "pattern": "use {item}",
  "preconditions": [
    { "type": "has_item", "item": "healing_potion" }
  ],
  "effects": [
    { "type": "remove_item", "item": "healing_potion" },
    { "type": "change_health", "amount": 30 },
    { "type": "add_score", "points": 2 },
    { "type": "print", "message": "You uncork the vial and drink. Warmth floods through you as your wounds begin to close." }
  ],
  "one_shot": false
}
```

Note: `one_shot` is `false` here. The command repeats — but it requires `has_item: healing_potion`, so once the potion is removed by the first effect, the precondition will naturally fail on subsequent attempts unless the player finds another potion.

### Atomicity

All effects in a command execute within a single database transaction. If any effect raises an error, the entire command is rolled back — including the one-shot executed marker. The game state never enters an inconsistent state where some effects applied and others didn't.

---

## 7. Worked Examples

### 7.1 Locked Door Puzzle

**Scenario**: The player finds a rusty key in the cellar. The dungeon entrance has a locked iron door. Using the key on the door consumes the key, unlocks the door, reveals the exit northward, and prints a message.

```json
{
  "id": "use_rusty_key_on_dungeon_door",
  "verb": "use",
  "pattern": "use {item} on {target}",
  "preconditions": [
    { "type": "in_room", "room": "dungeon_entrance" },
    { "type": "has_item", "item": "rusty_key" },
    { "type": "not_flag", "flag": "dungeon_door_opened" }
  ],
  "effects": [
    { "type": "remove_item", "item": "rusty_key" },
    { "type": "unlock", "lock": "dungeon_door_lock" },
    { "type": "reveal_exit", "exit": "dungeon_entrance_to_dungeon_hall" },
    { "type": "set_flag", "flag": "dungeon_door_opened" },
    { "type": "add_score", "points": 10 },
    { "type": "print", "message": "The rusty key turns with a grinding screech. The iron door shudders, then swings inward. A cold draft rushes out from the darkness beyond." }
  ],
  "failure_message": "You need the right key for this door.",
  "one_shot": true
}
```

**Why `one_shot: true`**: The key is consumed and the door is permanently open. Even though the preconditions would naturally prevent re-firing (the key is gone, the flag is set), `one_shot` makes the intent explicit and avoids wasted pattern-matching cycles.

**Why `not_flag` precondition**: Belt-and-suspenders. If something else could set the flag (e.g., an NPC opens the door for you), this command won't fire redundantly.

### 7.2 Combination Puzzle

**Scenario**: The player has a cracked lens and an ornate frame, both found in different rooms. Combining them creates a magnifying glass needed for a later puzzle.

```json
{
  "id": "combine_lens_and_frame",
  "verb": "combine",
  "pattern": "combine {item} with {item2}",
  "preconditions": [
    { "type": "has_item", "item": "cracked_lens" },
    { "type": "has_item", "item": "ornate_frame" }
  ],
  "effects": [
    { "type": "remove_item", "item": "cracked_lens" },
    { "type": "remove_item", "item": "ornate_frame" },
    { "type": "spawn_item", "item": "magnifying_glass", "location": "_inventory" },
    { "type": "set_flag", "flag": "crafted_magnifying_glass" },
    { "type": "add_score", "points": 15 },
    { "type": "print", "message": "You fit the cracked lens into the ornate frame. It holds — barely. The magnifying glass won't win any beauty contests, but it works." }
  ],
  "one_shot": true
}
```

**Note on order-independence**: The pattern is `combine {item} with {item2}`, but the preconditions check for specific item IDs, not slot values. This means the player can type `combine lens with frame` or `combine frame with lens` — the engine will match the pattern either way, and the preconditions check for both items in inventory regardless of which slot captured which. To support both orderings explicitly, generate a second command with the items swapped in preconditions, or rely on the engine's alias resolution to map both inputs to the same command.

### 7.3 NPC Conversation Trigger

**Scenario**: The player talks to an old wizard for the first time. The wizard reveals the existence of a larger task, gives the player an enchanted amulet, and sets a flag that unlocks new dialogue options elsewhere.

```json
{
  "id": "talk_to_wizard_first_time",
  "verb": "talk",
  "pattern": "talk to {npc}",
  "preconditions": [
    { "type": "npc_in_room", "npc": "old_wizard", "room": "_current" },
    { "type": "not_flag", "flag": "spoke_to_wizard" }
  ],
  "effects": [
    { "type": "set_flag", "flag": "spoke_to_wizard" },
    { "type": "discover_quest", "quest": "seal_the_mountain_gate" },
    { "type": "spawn_item", "item": "enchanted_amulet", "location": "_inventory" },
    { "type": "add_score", "points": 10 },
    { "type": "print", "message": "The old wizard studies you for a long moment. \"You have the look,\" he says. \"The look of someone who doesn't know what they've walked into.\" He tells you of the Sealed King — a ruler entombed beneath the mountain centuries ago, bound by three locks that no single key can open. He presses a cold amulet into your hand. \"You'll need this. Don't ask me why. You'll know when the time comes.\"" }
  ],
  "one_shot": true
}
```

A companion command handles subsequent conversations:

```json
{
  "id": "talk_to_wizard_again",
  "verb": "talk",
  "pattern": "talk to {npc}",
  "preconditions": [
    { "type": "npc_in_room", "npc": "old_wizard", "room": "_current" },
    { "type": "has_flag", "flag": "spoke_to_wizard" }
  ],
  "effects": [
    { "type": "print", "message": "The wizard glances up from his book. \"Still here? The mountain won't unseal itself. Go.\"" }
  ],
  "one_shot": false
}
```

**Command priority**: The engine evaluates the first-time command before the repeat command. Since `not_flag: spoke_to_wizard` fails after the first conversation, the engine falls through to the repeat command on subsequent interactions.

### 7.4 Hidden Passage

**Scenario**: The player examines a bookshelf in the library. A hidden passage is revealed behind it, leading to a secret study.

```json
{
  "id": "examine_library_bookshelf",
  "verb": "look",
  "pattern": "look at {target}",
  "preconditions": [
    { "type": "in_room", "room": "library" },
    { "type": "item_in_room", "item": "old_bookshelf", "room": "_current" },
    { "type": "not_flag", "flag": "bookshelf_moved" }
  ],
  "effects": [
    { "type": "set_flag", "flag": "bookshelf_moved" },
    { "type": "reveal_exit", "exit": "library_to_secret_study" },
    { "type": "add_score", "points": 20 },
    { "type": "print", "message": "You run your fingers along the bookshelf's edge. One volume — \"A Treatise on Hidden Things\" — doesn't budge when you pull it. Instead, the entire shelf swings outward with a low groan, revealing a narrow passage cut into the stone behind it." }
  ],
  "one_shot": true
}
```

A follow-up command for re-examining the bookshelf after the passage is revealed:

```json
{
  "id": "examine_library_bookshelf_after",
  "verb": "look",
  "pattern": "look at {target}",
  "preconditions": [
    { "type": "in_room", "room": "library" },
    { "type": "item_in_room", "item": "old_bookshelf", "room": "_current" },
    { "type": "has_flag", "flag": "bookshelf_moved" }
  ],
  "effects": [
    { "type": "print", "message": "The bookshelf stands ajar, the passage behind it gaping like a dark mouth. Dust motes drift in the thin light." }
  ],
  "one_shot": false
}
```

### 7.5 Multi-Step Puzzle Chain

**Scenario**: A two-step puzzle. First, the player pulls a lever in the mechanism room, which sets a flag. Then, the player pushes a statue in the adjacent hall. The statue command checks for the lever flag. Only when both steps are done does a hidden passage open.

**Step 1: Pull the lever**

```json
{
  "id": "pull_mechanism_lever",
  "verb": "pull",
  "pattern": "pull {target}",
  "preconditions": [
    { "type": "in_room", "room": "mechanism_room" },
    { "type": "item_in_room", "item": "iron_lever", "room": "_current" },
    { "type": "not_flag", "flag": "lever_pulled" }
  ],
  "effects": [
    { "type": "set_flag", "flag": "lever_pulled" },
    { "type": "print", "message": "You heave the lever downward. Somewhere deep in the walls, gears grind and chains rattle. Something has shifted — but not here." }
  ],
  "one_shot": true
}
```

**Step 2: Push the statue (requires lever)**

```json
{
  "id": "push_hall_statue",
  "verb": "push",
  "pattern": "push {target}",
  "preconditions": [
    { "type": "in_room", "room": "great_hall" },
    { "type": "item_in_room", "item": "stone_statue", "room": "_current" },
    { "type": "has_flag", "flag": "lever_pulled" },
    { "type": "not_flag", "flag": "statue_moved" }
  ],
  "effects": [
    { "type": "set_flag", "flag": "statue_moved" },
    { "type": "reveal_exit", "exit": "great_hall_to_hidden_crypt" },
    { "type": "solve_puzzle", "puzzle": "lever_and_statue" },
    { "type": "add_score", "points": 25 },
    { "type": "print", "message": "The statue slides across the floor with surprising ease — the mechanism below has unlocked its base. Behind it, a narrow staircase descends into the earth. Cold air rises from below, carrying the faint scent of dust and something older." }
  ],
  "failure_message": "The statue won't budge. It feels like something is holding it in place from below.",
  "one_shot": true
}
```

**Step 2 (without lever): Push the statue before pulling the lever**

```json
{
  "id": "push_hall_statue_locked",
  "verb": "push",
  "pattern": "push {target}",
  "preconditions": [
    { "type": "in_room", "room": "great_hall" },
    { "type": "item_in_room", "item": "stone_statue", "room": "_current" },
    { "type": "not_flag", "flag": "lever_pulled" },
    { "type": "not_flag", "flag": "statue_moved" }
  ],
  "effects": [
    { "type": "print", "message": "You throw your weight against the statue. It doesn't move — not even a fraction. Something beneath the floor is holding it firmly in place." }
  ],
  "one_shot": false
}
```

**Design notes on multi-step chains**:

- Flags are the connective tissue. Step 1 sets `lever_pulled`. Step 2 requires `lever_pulled`.
- The `failure_message` on the main push command provides a hint ("holding it in place from below") that nudges the player toward finding the mechanism room.
- The separate "locked" variant gives explicit feedback when the player tries pushing the statue before the lever. This is not strictly necessary (the `failure_message` on the primary command would fire), but it allows for more specific narrative text that guides the player without being heavy-handed.
- The `solve_puzzle` effect on step 2 marks the entire multi-step puzzle as complete for scoring and progression tracking.

---

## Appendix A: Quick Reference Tables

### All Precondition Types

| Type | Required Fields | Description |
|------|----------------|-------------|
| `in_room` | `room` | Player is in this room |
| `has_item` | `item` | Player has this item in inventory |
| `has_flag` | `flag` | World flag is set |
| `not_flag` | `flag` | World flag is NOT set |
| `item_in_room` | `item`, `room` | Item exists in this room |
| `npc_in_room` | `npc`, `room` | Living NPC exists in this room |
| `lock_unlocked` | `lock` | Lock is in unlocked state |
| `puzzle_solved` | `puzzle` | Puzzle has been solved |
| `health_above` | `threshold` | Player health > threshold |
| `item_accessible` | `item` | Item is visible and reachable (in inventory, current room, or inside an open container in either) |
| `container_open` | `container` | Container is in open state |
| `item_in_container` | `item`, `container` | Item is inside this container |
| `not_item_in_container` | `item`, `container` | Item is NOT inside this container |
| `container_has_contents` | `container` | Container has at least one item |
| `container_empty` | `container` | Container is empty |
| `has_quantity` | `item`, `min` | Item has at least this many charges remaining |
| `toggle_state` | `item`, `state` | Item toggle is in this state |

### All Effect Types

| Type | Required Fields | Description |
|------|----------------|-------------|
| `move_item` | `item`, `from`, `to` | Move item between locations |
| `remove_item` | `item` | Permanently destroy item |
| `set_flag` | `flag` | Set (or unset) a world flag |
| `unlock` | `lock` | Unlock a lock |
| `move_player` | `room` | Teleport player to room |
| `spawn_item` | `item`, `location` | Place a pre-defined item into the world |
| `change_health` | `amount` | Modify player health (+ or -) |
| `add_score` | `points` | Add to player score |
| `reveal_exit` | `exit` | Make a hidden exit visible |
| `solve_puzzle` | `puzzle` | Mark puzzle as solved |
| `discover_quest` | `quest` | Set a quest's discovery flag |
| `print` | `message` | Display text to the player |
| `open_container` | `container` | Open a container |
| `move_item_to_container` | `item`, `container` | Place item inside container |
| `take_item_from_container` | `item` | Remove item from its container to player inventory |
| `consume_quantity` | `item` | Use up consumable charges (amount defaults to 1) |
| `restore_quantity` | `item` | Refill consumable charges (amount defaults to 1) |
| `set_toggle_state` | `item`, `state` | Change an item's toggle state |
| `move_npc` | `npc`, `room` | Relocate an NPC to a different room |
| `make_visible` | `item` | Make a hidden item visible |
| `make_hidden` | `item` | Make a visible item hidden |
| `make_takeable` | `item` | Make an item takeable |
| `fail_quest` | `quest` | Mark a quest as failed |
| `complete_quest` | `quest` | Mark a quest as completed (sets completion flag, awards score) |
| `kill_npc` | `npc` | Kill a specific NPC |
| `remove_npc` | `npc` | Permanently remove an NPC from the game |
| `lock_exit` | `exit` | Lock an exit |
| `hide_exit` | `exit` | Hide an exit |
| `change_description` | `entity`, `text` | Change the description of any entity |

### Target-Aware Effects (Interaction Responses Only)

These effects are only valid inside `interaction` blocks where an item is used on a target:

| Type | Required Fields | Description |
|------|----------------|-------------|
| `kill_target` | _(none)_ | Kill the target NPC, spawning a lootable body |
| `damage_target` | `amount` | Deal damage to the target NPC |
| `destroy_target` | _(none)_ | Destroy the target container, scattering contents |
| `open_target` | _(none)_ | Open the target container |

### Validator Constraints

Every `on` block (command) must produce at least one **effect** or include a **success message**. A command with neither will fail validation. Global fallback commands should use a `success` message that explains why the verb does nothing in the current context.

### Special Location Constants

| Constant | Meaning |
|----------|---------|
| `"_current"` | The room the player is currently in |
| `"_inventory"` | The player's inventory |
