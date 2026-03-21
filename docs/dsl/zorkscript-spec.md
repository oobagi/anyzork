# ZorkScript Language Specification

## Status

Draft -- v0.1

## 1. Overview

ZorkScript is a textual DSL for authoring AnyZork game worlds. It compiles to
the same SQLite schema (`.zork` file) consumed by the deterministic runtime
engine. No engine changes are required.

### Why not JSON?

ZorkScript replaced an older JSON authoring template because LLMs generating
that format hit three recurring problems:

1. **Token cost.** Deeply nested JSON with repeated keys (`"type"`, `"flag"`,
   `"item"`) wastes tokens on structure, not content.
2. **Structural errors.** Missing commas, unmatched brackets, and trailing
   commas are the most common LLM JSON failures.
3. **Opacity.** `{"type": "has_flag", "flag": "X"}` carries no meaning to a
   human scanning the file. `require has_flag(X)` does.

ZorkScript is line-oriented, keyword-driven, and block-structured. It maps
1:1 to the existing engine vocabulary with zero new game mechanics.

### Design principles

- Keywords ARE the documentation.
- Every construct compiles to existing DB tables. The language is sugar.
- Minimize nesting. Two levels maximum.
- Prefer words over punctuation.
- String literals use double quotes. Identifiers are bare `snake_case` words.
- Comments start with `#`.


## 2. Lexical Conventions

```
# This is a comment. Comments run to end of line.

# Identifiers: bare snake_case words
dungeon_entrance
rusty_key
old_wizard

# String literals: double-quoted, backslash escapes \" and \\
"The door creaks open."
"She says, \"Follow me.\""

# Numbers: integer literals, optionally negative
100
-10

# Booleans: true, false (bare keywords)
true
false
```

### Reserved keywords

```
game player room exit item npc lock puzzle flag quest objective
command trigger dialogue option interaction
require effect on when in
true false
```

### Blocks

Blocks use curly braces. Indentation is not significant but recommended at
2 spaces for readability.

```
room dungeon_entrance {
  ...
}
```


## 3. Top-Level Structure

A ZorkScript file has two required top-level blocks and any number of entity
declarations in any order.

```zorkscript
game {
  title       "The Sealed King"
  author      "A wizard's prompt goes here."
  intro_text  "You awaken in a stone corridor..."
  win_text    "The mountain gate seals shut behind you."
  lose_text   "Darkness takes you."
  max_score   100
  realism     "medium"
  win_conditions  [sealed_king_defeated]
  lose_conditions [player_died]
}

player {
  start_room  dungeon_entrance
  hp          100
  max_hp      100
}

# Entity declarations follow in any order.
room dungeon_entrance { ... }
item rusty_key { ... }
# ...
```

### `game` block

Compiles to the `metadata` table (single row).

| Field             | Type          | Required | Notes |
|-------------------|---------------|----------|-------|
| `title`           | string        | yes      | |
| `author`          | string        | yes      | Maps to `author_prompt` |
| `intro_text`      | string        | no       | |
| `win_text`        | string        | no       | |
| `lose_text`       | string        | no       | |
| `max_score`       | integer       | no       | Default 0 |
| `realism`         | string        | no       | `"low"`, `"medium"`, `"high"`. Default `"medium"` |
| `win_conditions`  | id-list       | yes      | `[flag_id, ...]` |
| `lose_conditions` | id-list       | no       | `[flag_id, ...]` |

### `player` block

Compiles to the `player` table (single row).

| Field        | Type      | Required | Notes |
|--------------|-----------|----------|-------|
| `start_room` | id        | yes      | References a room id |
| `hp`         | integer   | no       | Default 100 |
| `max_hp`     | integer   | no       | Default 100 |


## 4. Entity Declarations

### 4.1 Rooms

```zorkscript
room cellar {
  name        "The Cellar"
  description "Damp stone walls sweat in the lamplight. A rusted shelf
               holds forgotten jars. Water drips from somewhere above."
  short_description "A damp cellar beneath the house."
  first_visit "The smell hits you first -- mildew and something sharper."
  region      "house"
  is_dark     false
  is_start    false
}
```

Compiles to the `rooms` table.

| Field               | Type    | Required | Default |
|---------------------|---------|----------|---------|
| `name`              | string  | yes      | |
| `description`       | string  | yes      | |
| `short_description` | string  | yes      | |
| `first_visit`       | string  | no       | Maps to `first_visit_text` |
| `region`            | string  | yes      | |
| `is_dark`           | boolean | no       | false |
| `is_start`          | boolean | no       | false |

### 4.2 Exits

```zorkscript
exit cellar_to_hall {
  from      cellar
  to        hall
  direction north
  description "A narrow staircase climbs upward."
  is_locked false
  is_hidden false
}
```

Compiles to the `exits` table.

| Field         | Type    | Required | Default |
|---------------|---------|----------|---------|
| `from`        | id      | yes      | Maps to `from_room_id` |
| `to`          | id      | yes      | Maps to `to_room_id` |
| `direction`   | string  | yes      | One of: `north`, `south`, `east`, `west`, `up`, `down` |
| `description` | string  | no       | |
| `is_locked`   | boolean | no       | false |
| `is_hidden`   | boolean | no       | false |

### 4.3 Items

```zorkscript
item rusty_key {
  name              "Rusty Key"
  description       "A small iron key, red with rust."
  examine           "The teeth are worn but intact. It might still work."
  room_id           cellar
  is_takeable       true
  is_visible        true

  # Optional messaging
  take_message      "You pocket the key. It leaves rust on your fingers."
  room_description  "A rusty key lies on the shelf."
}
```

Compiles to the `items` table. The `examine` field maps to
`examine_description`.

Items support all fields from the schema. The most common fields:

| Field                 | Type    | Required | Default |
|-----------------------|---------|----------|---------|
| `name`                | string  | yes      | |
| `description`         | string  | yes      | |
| `examine`             | string  | yes      | Maps to `examine_description` |
| `room_id`             | id      | no       | null (not placed yet) |
| `container_id`        | id      | no       | null |
| `is_takeable`         | boolean | no       | true |
| `is_visible`          | boolean | no       | true |
| `is_consumed_on_use`  | boolean | no       | false |
| `take_message`        | string  | no       | |
| `drop_message`        | string  | no       | |
| `room_description`    | string  | no       | |
| `read_description`    | string  | no       | |
| `category`            | string  | no       | |
| `item_tags`           | list    | no       | `["weapon", "light_source", ...]` |

#### Container items

```zorkscript
item wooden_chest {
  name          "Wooden Chest"
  description   "A heavy oak chest bound with iron bands."
  examine       "The lock is old but sturdy."
  room_id       cellar
  is_takeable   false
  is_container  true
  is_open       false
  has_lid       true
  is_locked     true
  key_item_id   rusty_key
  consume_key   true
  open_message  "The lid creaks open."
  unlock_message "The lock clicks and falls away."
}
```

#### Toggleable items

```zorkscript
item oil_lamp {
  name              "Oil Lamp"
  description       "A brass lamp with a wick."
  examine           "The oil reservoir is half full."
  room_id           cellar
  is_toggleable     true
  toggle_state      "off"
  toggle_on_message  "The flame catches and steadies."
  toggle_off_message "You snuff the flame."
}
```

#### Quantity items

```zorkscript
item revolver {
  name                "Revolver"
  description         "A six-shot revolver."
  examine             "Four rounds remain."
  room_id             study
  quantity            4
  max_quantity        6
  quantity_unit       "rounds"
  depleted_message    "Click. Empty."
  quantity_description "The {name} has {quantity} {unit} remaining."
  item_tags           ["weapon", "firearm"]
}
```

### 4.4 NPCs

```zorkscript
npc old_wizard {
  name              "The Old Wizard"
  description       "A stooped figure in threadbare robes."
  examine           "His eyes are sharp despite his age."
  room_id           tower_study
  default_dialogue  "He peers at you over his spectacles."
  category          "character"
}
```

Compiles to the `npcs` table.

| Field              | Type    | Required | Default |
|--------------------|---------|----------|---------|
| `name`             | string  | yes      | |
| `description`      | string  | yes      | |
| `examine`          | string  | yes      | Maps to `examine_description` |
| `room_id`          | id      | yes      | |
| `default_dialogue` | string  | yes      | |
| `is_alive`         | boolean | no       | true |
| `is_blocking`      | boolean | no       | false |
| `blocked_exit_id`  | id      | no       | |
| `unblock_flag`     | id      | no       | |
| `hp`               | integer | no       | |
| `damage`           | integer | no       | |
| `category`         | string  | no       | |

### 4.5 Locks

```zorkscript
lock dungeon_door_lock {
  type            "key"
  target_exit     dungeon_entrance_to_hall
  key_item_id     rusty_key
  locked_message  "The iron door is locked."
  unlock_message  "The lock clicks open."
  consume_key     true
}
```

Compiles to the `locks` table. The `type` field maps to `lock_type`.
The `target_exit` field maps to `target_exit_id`.

| Field            | Type    | Required | Default |
|------------------|---------|----------|---------|
| `type`           | string  | yes      | `"key"`, `"puzzle"`, `"flag"`, `"combination"`, `"npc"` |
| `target_exit`    | id      | yes      | Maps to `target_exit_id` |
| `key_item_id`    | id      | no       | For key-type locks |
| `puzzle_id`      | id      | no       | For puzzle-type locks |
| `combination`    | string  | no       | For combination-type locks |
| `required_flags` | id-list | no       | For flag-type locks |
| `locked_message` | string  | yes      | |
| `unlock_message` | string  | yes      | |
| `is_locked`      | boolean | no       | true |
| `consume_key`    | boolean | no       | true |

### 4.6 Puzzles

```zorkscript
puzzle lever_and_statue {
  name            "The Lever and the Statue"
  description     "Two mechanisms work in tandem."
  room_id         mechanism_room
  difficulty      2
  score_value     25
  is_optional     false
  solution_steps  ["Pull the lever in the mechanism room",
                   "Push the statue in the great hall"]
  hint_text       ["Something clicks deep in the walls.",
                   "The statue seems anchored from below."]
}
```

Compiles to the `puzzles` table.

| Field            | Type       | Required | Default |
|------------------|------------|----------|---------|
| `name`           | string     | yes      | |
| `description`    | string     | yes      | |
| `room_id`        | id         | yes      | |
| `difficulty`     | integer    | no       | 1 |
| `score_value`    | integer    | no       | 0 |
| `is_optional`    | boolean    | no       | false |
| `is_solved`      | boolean    | no       | false |
| `solution_steps` | string-list| no       | JSON array |
| `hint_text`      | string-list| no       | JSON array |

### 4.7 Flags

```zorkscript
flag dungeon_door_opened {
  description "The dungeon door has been opened"
  value       false
}
```

Compiles to the `flags` table. The `value` is stored as a string
(`"true"` / `"false"`).

| Field         | Type    | Required | Default |
|---------------|---------|----------|---------|
| `description` | string  | no       | |
| `value`       | boolean | no       | false |

### 4.8 Quests

```zorkscript
quest seal_the_gate {
  name            "Seal the Mountain Gate"
  description     "Find the three keys and seal the gate."
  quest_type      "main"
  discovery_flag  met_wizard
  completion_flag gate_sealed
  score_value     50
  sort_order      0

  objective obj_find_amulet {
    description     "Retrieve the enchanted amulet."
    completion_flag has_amulet
    order_index     0
    is_optional     false
    bonus_score     10
  }

  objective obj_find_crystal {
    description     "Find the crystal shard."
    completion_flag has_crystal
    order_index     1
    is_optional     false
    bonus_score     10
  }

  objective obj_explore_crypt {
    description     "Explore the hidden crypt."
    completion_flag explored_crypt
    order_index     2
    is_optional     true
    bonus_score     5
  }
}
```

Compiles to the `quests` and `quest_objectives` tables. Objectives are
nested inside the quest block.

Quest fields:

| Field             | Type    | Required | Default |
|-------------------|---------|----------|---------|
| `name`            | string  | yes      | |
| `description`     | string  | yes      | |
| `quest_type`      | string  | yes      | `"main"` or `"side"` |
| `discovery_flag`  | id      | no       | |
| `completion_flag` | id      | yes      | |
| `score_value`     | integer | no       | 0 |
| `sort_order`      | integer | no       | 0 |

Objective fields:

| Field             | Type    | Required | Default |
|-------------------|---------|----------|---------|
| `description`     | string  | yes      | |
| `completion_flag` | id      | yes      | |
| `order_index`     | integer | no       | 0 |
| `is_optional`     | boolean | no       | false |
| `bonus_score`     | integer | no       | 0 |


## 5. Command Blocks

Commands define player-initiated actions. Each command is a pattern-matching
rule with preconditions and effects.

### Basic syntax

```zorkscript
command use_key_on_door {
  verb    "use"
  pattern "use {item} on {target}"

  in_rooms [dungeon_entrance]
  one_shot true

  require has_item(rusty_key)
  require in_room(dungeon_entrance)
  require not_flag(dungeon_door_opened)

  on_fail "You need the right key for this door."

  effect remove_item(rusty_key)
  effect unlock(dungeon_door_lock)
  effect reveal_exit(dungeon_entrance_to_hall)
  effect set_flag(dungeon_door_opened)
  effect add_score(10)
  effect print("The rusty key turns with a grinding screech. The door swings open.")
}
```

### Structure

| Field       | Type        | Required | Notes |
|-------------|-------------|----------|-------|
| `verb`      | string      | yes      | First word of input. Lowercased. |
| `pattern`   | string      | yes      | Full pattern with `{slot}` placeholders |
| `in_rooms`  | id-list     | no       | Maps to `context_room_ids`. Omit for global. |
| `one_shot`  | boolean     | no       | Default false |
| `priority`  | integer     | no       | Default 0. Higher = evaluated first. |
| `puzzle_id` | id          | no       | Associate with a puzzle. |
| `require`   | precondition| 0+       | All must pass for the command to fire. |
| `on_fail`   | string      | no       | Maps to `failure_message` |
| `on_done`   | string      | no       | Maps to `done_message` (for re-fired one-shots) |
| `effect`    | effect      | 1+       | Executed in order when preconditions pass. |

### Precondition syntax

Each `require` line is a function-call-style expression. Arguments are
bare identifiers or string literals.

```zorkscript
# Entity state checks
require in_room(dungeon_entrance)
require has_item(rusty_key)
require has_item({item})                   # slot reference
require has_flag(spoke_to_wizard)
require not_flag(bridge_destroyed)
require item_in_room(ancient_tome, _current)
require item_accessible(old_bookshelf)
require npc_in_room(old_wizard, _current)
require lock_unlocked(dungeon_door_lock)
require puzzle_solved(mirror_alignment)
require health_above(0)

# Container checks
require container_open(wooden_chest)
require item_in_container(gold_coin, wooden_chest)
require not_item_in_container(gem, locked_box)
require container_has_contents(wooden_chest)
require container_empty(wooden_chest)

# Item state checks
require has_quantity(revolver, 1)           # min quantity
require toggle_state(oil_lamp, "on")
```

#### Precondition reference

| Precondition              | Arguments                   | Compiles to |
|---------------------------|-----------------------------|-------------|
| `in_room(R)`              | room id                     | `{"type": "in_room", "room": R}` |
| `has_item(I)`             | item id or `{slot}`         | `{"type": "has_item", "item": I}` |
| `has_flag(F)`             | flag id                     | `{"type": "has_flag", "flag": F}` |
| `not_flag(F)`             | flag id                     | `{"type": "not_flag", "flag": F}` |
| `item_in_room(I, R)`      | item id, room id or `_current` | `{"type": "item_in_room", "item": I, "room": R}` |
| `item_accessible(I)`      | item id                     | `{"type": "item_accessible", "item": I}` |
| `npc_in_room(N, R)`       | npc id, room id or `_current`  | `{"type": "npc_in_room", "npc": N, "room": R}` |
| `lock_unlocked(L)`        | lock id                     | `{"type": "lock_unlocked", "lock": L}` |
| `puzzle_solved(P)`        | puzzle id                   | `{"type": "puzzle_solved", "puzzle": P}` |
| `health_above(T)`         | integer threshold           | `{"type": "health_above", "threshold": T}` |
| `container_open(C)`       | container item id           | `{"type": "container_open", "container": C}` |
| `item_in_container(I, C)` | item id, container id       | `{"type": "item_in_container", "item": I, "container": C}` |
| `not_item_in_container(I, C)` | item id, container id   | `{"type": "not_item_in_container", "item": I, "container": C}` |
| `container_has_contents(C)` | container item id         | `{"type": "container_has_contents", "container": C}` |
| `container_empty(C)`      | container item id           | `{"type": "container_empty", "container": C}` |
| `has_quantity(I, N)`       | item id, min quantity       | `{"type": "has_quantity", "item": I, "min": N}` |
| `toggle_state(I, S)`      | item id, state string       | `{"type": "toggle_state", "item": I, "state": S}` |

### Effect syntax

Each `effect` line is a function-call-style expression.

```zorkscript
effect move_item(silver_chalice, altar_room, _inventory)
effect remove_item(rusty_key)
effect set_flag(dungeon_door_opened)
effect set_flag(torch_lit, false)
effect unlock(dungeon_door_lock)
effect move_player(throne_room)
effect spawn_item(enchanted_amulet, _inventory)
effect change_health(-10)
effect change_health(25)
effect add_score(10)
effect reveal_exit(library_secret_passage)
effect solve_puzzle(crystal_alignment)
effect discover_quest(the_hermits_bargain)
effect print("The door swings open with a grinding screech.")
effect open_container(wooden_chest)
effect move_item_to_container(gold_coin, wooden_chest)
effect take_item_from_container(gem)
effect consume_quantity(revolver, 1)
effect restore_quantity(revolver, 6)
effect set_toggle_state(oil_lamp, "on")
effect fail_quest(village_rescue)
effect complete_quest(the_hermits_bargain)
effect kill_npc(tower_guard)
effect remove_npc(shady_merchant)
effect lock_exit(mine_shaft_north)
effect hide_exit(lower_cavern_east)
effect change_description(lower_cavern, "The cavern is knee-deep in rushing water.")
```

#### Effect reference

| Effect                         | Arguments                  | Compiles to |
|--------------------------------|----------------------------|-------------|
| `move_item(I, FROM, TO)`      | item, source, destination  | `{"type": "move_item", "item": I, "from": FROM, "to": TO}` |
| `remove_item(I)`              | item id                    | `{"type": "remove_item", "item": I}` |
| `set_flag(F)`                 | flag id                    | `{"type": "set_flag", "flag": F}` |
| `set_flag(F, V)`              | flag id, boolean           | `{"type": "set_flag", "flag": F, "value": V}` |
| `unlock(L)`                   | lock id                    | `{"type": "unlock", "lock": L}` |
| `move_player(R)`              | room id                    | `{"type": "move_player", "room": R}` |
| `spawn_item(I, LOC)`          | item id, location          | `{"type": "spawn_item", "item": I, "location": LOC}` |
| `change_health(N)`            | integer (+ or -)           | `{"type": "change_health", "amount": N}` |
| `add_score(N)`                | integer                    | `{"type": "add_score", "points": N}` |
| `reveal_exit(E)`              | exit id                    | `{"type": "reveal_exit", "exit": E}` |
| `solve_puzzle(P)`             | puzzle id                  | `{"type": "solve_puzzle", "puzzle": P}` |
| `discover_quest(Q)`           | quest id                   | `{"type": "discover_quest", "quest": Q}` |
| `print(MSG)`                  | string literal             | `{"type": "print", "message": MSG}` |
| `open_container(C)`           | container item id          | `{"type": "open_container", "container": C}` |
| `move_item_to_container(I, C)`| item id, container id      | `{"type": "move_item_to_container", "item": I, "container": C}` |
| `take_item_from_container(I)` | item id                    | `{"type": "take_item_from_container", "item": I}` |
| `consume_quantity(I, N)`      | item id, amount            | `{"type": "consume_quantity", "item": I, "amount": N}` |
| `restore_quantity(I, N)`      | item id, amount            | `{"type": "restore_quantity", "item": I, "amount": N}` |
| `set_toggle_state(I, S)`      | item id, state string      | `{"type": "set_toggle_state", "item": I, "state": S}` |
| `fail_quest(Q)`               | quest id                   | `{"type": "fail_quest", "quest": Q}` |
| `complete_quest(Q)`           | quest id                   | `{"type": "complete_quest", "quest": Q}` |
| `kill_npc(NPC)`               | npc id                     | `{"type": "kill_npc", "npc": NPC}` |
| `remove_npc(NPC)`             | npc id                     | `{"type": "remove_npc", "npc": NPC}` |
| `lock_exit(E)`                | exit id                    | `{"type": "lock_exit", "exit": E}` |
| `hide_exit(E)`                | exit id                    | `{"type": "hide_exit", "exit": E}` |
| `change_description(ID, TXT)` | entity id, string literal  | `{"type": "change_description", "entity": ID, "text": TXT}` |

### Slot references

Pattern slots (`{item}`, `{target}`, `{npc}`) can be referenced anywhere
an identifier appears in `require` or `effect` lines:

```zorkscript
command use_generic {
  verb    "use"
  pattern "use {item} on {target}"

  require has_item({item})
  effect  print("You use the {item} on the {target}.")
}
```

The compiler emits the slot reference as the literal string `"{item}"` in the
JSON, preserving the engine's existing substitution behavior.


## 6. Trigger Blocks

Triggers are reactive rules that fire when the engine emits an event. They
share the same precondition/effect vocabulary as commands.

```zorkscript
trigger enter_hut_intro {
  on       room_enter
  when     room_id = hut
  one_shot true

  require not_flag(met_hagrid)

  effect set_flag(met_hagrid)
  effect print("A thunderous knock shakes the door.")

  message "Hagrid has arrived."
}
```

### Structure

| Field     | Type        | Required | Notes |
|-----------|-------------|----------|-------|
| `on`      | string      | yes      | Event type. See below. |
| `when`    | key=value   | 0+       | Event data filters. Compiled to `event_data` JSON. |
| `one_shot`| boolean     | no       | Default false |
| `priority`| integer     | no       | Default 0. Higher = evaluated first. |
| `require` | precondition| 0+       | Same syntax as commands. |
| `effect`  | effect      | 0+       | Same syntax as commands. |
| `message` | string      | no       | Display text when trigger fires. |

### Event types

| Event Type      | `when` fields       | Fired when... |
|-----------------|---------------------|---------------|
| `room_enter`    | `room_id`           | Player enters a room |
| `flag_set`      | `flag`              | A flag is set to true |
| `dialogue_node` | `node_id`           | A dialogue node is visited |
| `item_taken`    | `item_id`           | Player takes an item |
| `item_dropped`  | `item_id`, `room_id`| Player drops an item |

### `when` clause compilation

Each `when` line becomes a key-value pair in the `event_data` JSON object:

```zorkscript
when room_id = hut
when item_id = rusty_key
```

Compiles to:

```json
{"event_data": {"room_id": "hut"}}
{"event_data": {"item_id": "rusty_key"}}
```


## 7. Dialogue Trees

Dialogue is declared with two block types: `dialogue` nodes and `option`
branches.

```zorkscript
dialogue wizard_intro {
  npc       old_wizard
  content   "You have the look of someone who doesn't know what they've walked into."
  is_root   true
  set_flags [spoke_to_wizard]
}

dialogue wizard_quest {
  npc       old_wizard
  content   "The Sealed King sleeps beneath the mountain. Three locks bind him."
}

option opt_ask_more {
  node      wizard_intro
  text      "Tell me more."
  next_node wizard_quest
  sort_order 0
}

option opt_leave {
  node      wizard_intro
  text      "I should go."
  sort_order 1
  # next_node omitted = terminal (ends conversation)
}

option opt_show_amulet {
  node        wizard_quest
  text        "I found this amulet."
  require_items    [enchanted_amulet]
  require_flags    [spoke_to_wizard]
  exclude_flags    [showed_amulet]
  set_flags        [showed_amulet]
  sort_order  0
}
```

### `dialogue` block

Compiles to `dialogue_nodes` table.

| Field       | Type       | Required | Default |
|-------------|------------|----------|---------|
| `npc`       | id         | yes      | Maps to `npc_id` |
| `content`   | string     | yes      | |
| `is_root`   | boolean    | no       | false |
| `set_flags` | id-list    | no       | JSON array of flag ids |

### `option` block

Compiles to `dialogue_options` table.

| Field           | Type       | Required | Default |
|-----------------|------------|----------|---------|
| `node`          | id         | yes      | Maps to `node_id` |
| `text`          | string     | yes      | |
| `next_node`     | id         | no       | Maps to `next_node_id`. Omit for terminal. |
| `require_flags` | id-list    | no       | Maps to `required_flags` JSON array |
| `exclude_flags` | id-list    | no       | Maps to `excluded_flags` JSON array |
| `require_items` | id-list    | no       | Maps to `required_items` JSON array |
| `set_flags`     | id-list    | no       | JSON array of flag ids |
| `sort_order`    | integer    | no       | 0 |


## 8. Interaction Responses

Interaction responses define generic tag-to-category reaction templates for
the item dynamics system. Every item should have `tags` and every item/NPC
should have a `category` for interactions to fire.

```zorkscript
interaction weapon_on_character {
  tag      "weapon"
  target   "character"
  response "You strike {target} with the {item}. They collapse."
  consumes 1
  effect   kill_target()
  effect   set_flag(npc_killed)
  effect   add_score(-10)
}
```

Use `target "*"` for wildcard fallbacks that match any category.

Compiles to the `interaction_responses` table.

| Field      | Type    | Required | Default |
|------------|---------|----------|---------|
| `tag`      | string  | yes      | |
| `target`   | string  | yes      | Use `"*"` for wildcard |
| `response` | string  | yes      | Template with `{item}` and `{target}` |
| `consumes` | integer | no       | 0 |
| `score`    | integer | no       | 0 |
| `sets_flag`| id      | no       | |
| `effect`   | effect  | no       | Repeatable. All standard + target-aware effects |

Target-aware effects (only available in interactions):
- `kill_target()` — kill the target NPC, spawn lootable body
- `damage_target(N)` — deal N damage to target NPC
- `destroy_target()` — break target container, scatter contents
- `open_target()` — open target container

All standard effects are also available in interactions. Particularly useful:
- `kill_npc(npc_id)` — kill a specific NPC by ID (not the target; e.g., a bystander)
- `remove_npc(npc_id)` — remove an NPC from the world entirely
- `fail_quest(quest_id)` — mark a quest as failed (e.g., killing a quest-giver)
- `complete_quest(quest_id)` — force-complete a quest
- `lock_exit(exit_id)` — re-lock a previously unlocked exit
- `hide_exit(exit_id)` — re-hide a previously revealed exit
- `change_description(entity_id, "text")` — change an item or room description at runtime


## 9. Worked Example: JSON vs ZorkScript

A small but complete game: two rooms, a locked door, a key, and a puzzle.

### JSON (current format)

```json
{
  "format": "anyzork.import.v1",
  "game": {
    "title": "The Iron Door",
    "author_prompt": "A two-room escape puzzle.",
    "intro_text": "You wake in a stone cellar. The only exit is an iron door.",
    "win_text": "Daylight. You are free.",
    "max_score": 20,
    "realism": "medium",
    "win_conditions": ["escaped"]
  },
  "player": {
    "start_room_id": "cellar",
    "hp": 100,
    "max_hp": 100
  },
  "rooms": [
    {
      "id": "cellar",
      "name": "The Cellar",
      "description": "Damp stone walls sweat in the lamplight. A shelf holds forgotten jars. A heavy iron door blocks the north wall.",
      "short_description": "A damp cellar.",
      "first_visit_text": "The smell hits you first.",
      "region": "underground",
      "is_dark": false,
      "is_start": true
    },
    {
      "id": "courtyard",
      "name": "The Courtyard",
      "description": "Open sky above crumbling walls. Weeds push through cracked flagstones.",
      "short_description": "A crumbling courtyard.",
      "first_visit_text": "Fresh air. Finally.",
      "region": "surface",
      "is_dark": false,
      "is_start": false
    }
  ],
  "exits": [
    {
      "id": "cellar_north",
      "from_room_id": "cellar",
      "to_room_id": "courtyard",
      "direction": "north",
      "description": "A heavy iron door.",
      "is_locked": true,
      "is_hidden": false
    }
  ],
  "items": [
    {
      "id": "iron_key",
      "name": "Iron Key",
      "description": "A blackened iron key.",
      "examine_description": "Heavy and cold. The teeth are sharp.",
      "room_id": "cellar",
      "is_takeable": true,
      "is_visible": true,
      "room_description": "An iron key lies half-hidden under a jar."
    }
  ],
  "npcs": [],
  "dialogue_nodes": [],
  "dialogue_options": [],
  "locks": [
    {
      "id": "cellar_door_lock",
      "lock_type": "key",
      "target_exit_id": "cellar_north",
      "key_item_id": "iron_key",
      "locked_message": "The iron door is locked.",
      "unlock_message": "The lock grinds open.",
      "is_locked": true,
      "consume_key": true
    }
  ],
  "puzzles": [
    {
      "id": "escape_cellar",
      "name": "Escape the Cellar",
      "description": "Find the key and unlock the door.",
      "room_id": "cellar",
      "difficulty": 1,
      "score_value": 10,
      "solution_steps": ["Take the iron key", "Use it on the door"],
      "hint_text": ["Look under the jars."]
    }
  ],
  "flags": [
    {
      "id": "door_unlocked",
      "description": "The cellar door has been unlocked",
      "value": false
    },
    {
      "id": "escaped",
      "description": "Player has escaped the cellar",
      "value": false
    }
  ],
  "interactions": [
    {
      "id": "unlock_iron_door",
      "type": "read_item",
      "command": "use iron key on door",
      "item_id": "iron_key",
      "context_room_ids": ["cellar"],
      "required_flags": [],
      "excluded_flags": ["door_unlocked"],
      "required_items": ["iron_key"],
      "set_flags": ["door_unlocked"],
      "give_items": [],
      "unlock_lock_ids": ["cellar_door_lock"],
      "reveal_exit_ids": [],
      "discover_quest_ids": [],
      "solve_puzzle_ids": ["escape_cellar"],
      "success_message": "The lock grinds and the door swings open.",
      "failure_message": "You need the right key.",
      "priority": 10,
      "one_shot": true
    }
  ],
  "quests": [],
  "triggers": [
    {
      "id": "reach_courtyard",
      "event_type": "room_enter",
      "event_data": {"room_id": "courtyard"},
      "preconditions": [
        {"type": "not_flag", "flag": "escaped"}
      ],
      "effects": [
        {"type": "set_flag", "flag": "escaped", "value": true},
        {"type": "add_score", "points": 10}
      ],
      "message": "Daylight washes over you. You made it out.",
      "priority": 0,
      "one_shot": true,
      "executed": false,
      "is_enabled": true
    }
  ]
}
```

**JSON: ~120 lines, ~2,800 tokens.**

### ZorkScript (equivalent)

```zorkscript
game {
  title       "The Iron Door"
  author      "A two-room escape puzzle."
  intro_text  "You wake in a stone cellar. The only exit is an iron door."
  win_text    "Daylight. You are free."
  max_score   20
  realism     "medium"
  win_conditions [escaped]
}

player {
  start_room cellar
  hp         100
  max_hp     100
}

# -- World --

room cellar {
  name        "The Cellar"
  description "Damp stone walls sweat in the lamplight. A shelf holds
               forgotten jars. A heavy iron door blocks the north wall."
  short_description "A damp cellar."
  first_visit "The smell hits you first."
  region      "underground"
  is_start    true
}

room courtyard {
  name        "The Courtyard"
  description "Open sky above crumbling walls. Weeds push through
               cracked flagstones."
  short_description "A crumbling courtyard."
  first_visit "Fresh air. Finally."
  region      "surface"
}

exit cellar_north {
  from      cellar
  to        courtyard
  direction north
  description "A heavy iron door."
  is_locked true
}

item iron_key {
  name              "Iron Key"
  description       "A blackened iron key."
  examine           "Heavy and cold. The teeth are sharp."
  room_id           cellar
  room_description  "An iron key lies half-hidden under a jar."
}

lock cellar_door_lock {
  type           "key"
  target_exit    cellar_north
  key_item_id    iron_key
  locked_message "The iron door is locked."
  unlock_message "The lock grinds open."
  consume_key    true
}

puzzle escape_cellar {
  name           "Escape the Cellar"
  description    "Find the key and unlock the door."
  room_id        cellar
  difficulty     1
  score_value    10
  solution_steps ["Take the iron key", "Use it on the door"]
  hint_text      ["Look under the jars."]
}

flag door_unlocked { description "The cellar door has been unlocked" }
flag escaped       { description "Player has escaped the cellar" }

# -- Logic --

command unlock_iron_door {
  verb    "use"
  pattern "use iron key on door"

  in_rooms [cellar]
  one_shot true

  require has_item(iron_key)
  require not_flag(door_unlocked)

  on_fail "You need the right key."

  effect set_flag(door_unlocked)
  effect unlock(cellar_door_lock)
  effect solve_puzzle(escape_cellar)
  effect print("The lock grinds and the door swings open.")
}

trigger reach_courtyard {
  on       room_enter
  when     room_id = courtyard
  one_shot true

  require not_flag(escaped)

  effect set_flag(escaped)
  effect add_score(10)

  message "Daylight washes over you. You made it out."
}
```

**ZorkScript: ~80 lines, ~1,100 tokens.**

Token reduction: roughly **60%** for equivalent content.


## 10. Compilation Model

### What the compiler does

The ZorkScript compiler is a straightforward transpiler. It parses the
textual DSL and inserts rows into the existing SQLite schema. There is no
intermediate representation, no optimization pass, and no code generation.

```
ZorkScript source
      |
      v
  [Parser]  -- block-oriented, line-by-line
      |
      v
  [Entity builder]  -- maps keywords to table columns
      |
      v
  [DB writer]  -- INSERT into existing schema tables
      |
      v
  .zork file (SQLite)
```

### Parsing strategy

1. **Tokenize** -- split on whitespace, respecting quoted strings and
   bracket-delimited lists.
2. **Block detection** -- recognize `keyword id {` as the start of a block.
   Track brace depth.
3. **Field extraction** -- inside a block, each line is `field_name value`.
   Values are strings, numbers, booleans, identifiers, or bracket-lists.
4. **Nested blocks** -- only `quest > objective` uses nesting. All other
   blocks are flat.
5. **Function-call syntax** -- `require` and `effect` lines parse as
   `name(arg1, arg2, ...)`.

### Field name mapping

Some ZorkScript field names are abbreviated for readability. The compiler
maps them to their DB column names:

| ZorkScript        | DB column             | Table |
|-------------------|-----------------------|-------|
| `author`          | `author_prompt`       | metadata |
| `first_visit`     | `first_visit_text`    | rooms |
| `examine`         | `examine_description` | items, npcs |
| `from`            | `from_room_id`        | exits |
| `to`              | `to_room_id`          | exits |
| `type` (in lock)  | `lock_type`           | locks |
| `target_exit`     | `target_exit_id`      | locks |
| `npc` (in dialogue)| `npc_id`             | dialogue_nodes |
| `node` (in option)| `node_id`             | dialogue_options |
| `next_node`       | `next_node_id`        | dialogue_options |
| `require_flags`   | `required_flags`      | dialogue_options |
| `exclude_flags`   | `excluded_flags`      | dialogue_options |
| `require_items`   | `required_items`      | dialogue_options |
| `in_rooms`        | `context_room_ids`    | commands |
| `on_fail`         | `failure_message`     | commands |
| `on_done`         | `done_message`        | commands |
| `on` (in trigger) | `event_type`          | triggers |

### ID-list syntax

Square brackets with comma-separated bare identifiers:

```
[cellar, hall, tower]
```

Compiles to a JSON array: `["cellar", "hall", "tower"]`.

### String-list syntax

Square brackets with comma-separated quoted strings:

```
["Take the key", "Open the door"]
```

Compiles to a JSON array: `["Take the key", "Open the door"]`.

### Multi-line strings

A string literal that continues on the next line (indented) is
concatenated with a single space:

```zorkscript
description "Damp stone walls sweat in the lamplight. A shelf holds
             forgotten jars. A heavy iron door blocks the north wall."
```

Produces the single string:
`"Damp stone walls sweat in the lamplight. A shelf holds forgotten jars. A heavy iron door blocks the north wall."`


## 11. Formal Grammar (EBNF)

```ebnf
program        = { top_level } ;
top_level      = game_block | player_block | entity_block ;

game_block     = "game" "{" { field } "}" ;
player_block   = "player" "{" { field } "}" ;

entity_block   = entity_kw IDENT "{" block_body "}" ;
entity_kw      = "room" | "exit" | "item" | "npc" | "lock" | "puzzle"
               | "flag" | "quest" | "command" | "trigger"
               | "dialogue" | "option" | "interaction" ;

block_body     = { field | nested_block | require_line | effect_line | when_line } ;
nested_block   = "objective" IDENT "{" { field } "}" ;

field          = IDENT value ;
value          = STRING | NUMBER | BOOLEAN | IDENT | id_list | string_list ;

require_line   = "require" func_call ;
effect_line    = "effect" func_call ;
when_line      = "when" IDENT "=" value ;

func_call      = IDENT "(" arg_list ")" ;
arg_list       = [ arg { "," arg } ] ;
arg            = STRING | NUMBER | BOOLEAN | IDENT | slot_ref ;
slot_ref       = "{" IDENT "}" ;

id_list        = "[" [ IDENT { "," IDENT } ] "]" ;
string_list    = "[" [ STRING { "," STRING } ] "]" ;

IDENT          = /[a-z_][a-z0-9_]*/ ;
STRING         = /"([^"\\]|\\.)*"/ ;
NUMBER         = /-?[0-9]+/ ;
BOOLEAN        = "true" | "false" ;
COMMENT        = /#[^\n]*/ ;
```

Whitespace (spaces, tabs, newlines) is insignificant except inside string
literals and as token separators. Comments are stripped during tokenization.


## 12. Token Efficiency Analysis

Comparison using the worked example from section 9.

| Metric                  | JSON       | ZorkScript | Savings |
|-------------------------|------------|------------|---------|
| Lines                   | ~120       | ~80        | 33%     |
| Characters              | ~3,400     | ~2,100     | 38%     |
| Estimated tokens (GPT-4)| ~2,800     | ~1,100     | 61%     |
| Structural punctuation  | ~180 chars | ~40 chars  | 78%     |

The savings come from three sources:

1. **Eliminated redundancy.** JSON repeats `"type"`, `"flag"`, `"item"` etc.
   as string keys on every precondition and effect object. ZorkScript uses
   function-call syntax: `has_flag(X)` vs `{"type": "has_flag", "flag": "X"}`.

2. **Eliminated structural noise.** JSON requires commas between array/object
   entries, colons between keys and values, and matching brackets at every
   level. ZorkScript uses line breaks as separators and braces only for
   top-level blocks.

3. **Eliminated empty arrays.** The JSON format requires `"npcs": []`,
   `"dialogue_nodes": []`, etc. even when empty. ZorkScript simply omits
   declarations that do not exist.

### LLM prompt overhead

The ZorkScript grammar reference (sections 3-8 of this document, stripped of
examples) is approximately **90 lines**. Combined with one worked example
(section 9, ZorkScript only), the total prompt payload for an LLM is roughly
**100 lines / ~1,500 tokens**.

The current JSON authoring template is **356 lines / ~5,000 tokens**.

Prompt overhead reduction: roughly **70%**.


## 13. Relation to the Import System

ZorkScript is the supported authored input for `anyzork import`. The older
JSON compatibility path has been removed from the shipped app, so the import
surface is now deliberately narrow:

1. **ZorkScript import** (`anyzork import game.zorkscript`)
2. **Standard output**: a compiled SQLite `.zork` game file

### What the compiler must NOT do

- Invent new table columns or game mechanics.
- Reorder effects (order is semantically meaningful).
- Merge or deduplicate entities.
- Validate game logic (that is the validator's job, after compilation).


## Appendix A: Complete Precondition and Effect Vocabulary

For quick reference, the full set of precondition and effect types that
ZorkScript wraps.

### Precondition types (17)

```
in_room, has_item, has_flag, not_flag, item_in_room, item_accessible,
npc_in_room, lock_unlocked, puzzle_solved, health_above, container_open,
item_in_container, not_item_in_container, container_has_contents,
container_empty, has_quantity, toggle_state
```

### Effect types (25)

```
move_item, remove_item, set_flag, unlock, move_player, spawn_item,
change_health, add_score, reveal_exit, solve_puzzle, discover_quest,
print, open_container, move_item_to_container, take_item_from_container,
consume_quantity, restore_quantity, set_toggle_state, fail_quest,
complete_quest, kill_npc, remove_npc, lock_exit, hide_exit,
change_description
```

### Event types (5)

```
room_enter, flag_set, dialogue_node, item_taken, item_dropped
```

### Special location constants

| Constant     | Meaning |
|-------------|---------|
| `_current`   | The room the player is currently in |
| `_inventory` | The player's inventory |
