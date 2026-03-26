# ZorkScript Language Specification

## Status

Draft -- v0.1

## 1. Overview

ZorkScript is a textual DSL for authoring AnyZork game worlds. It compiles to
a `.zork` archive (zip containing `manifest.toml` + `.zorkscript` source files)
consumed by the deterministic runtime engine. No engine changes are required.

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
command trigger dialogue option interaction on when
require effect in
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
  intro       "You awaken in a stone corridor..."
  win_text    "The mountain gate seals shut behind you."
  lose_text   "Darkness takes you."
  max_score   100
  realism     "medium"
  win         [sealed_king_defeated]
  lose        [player_died]
}

player {
  start  dungeon_entrance
  hp     100
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
| `intro_text`      | string        | no       | Shorthand: `intro` |
| `win_text`        | string        | no       | |
| `lose_text`       | string        | no       | |
| `max_score`       | integer       | no       | Default 0 |
| `realism`         | string        | no       | `"low"`, `"medium"`, `"high"`. Default `"medium"` |
| `win_conditions`  | id-list       | yes      | `[flag_id, ...]`. Shorthand: `win` |
| `lose_conditions` | id-list       | no       | `[flag_id, ...]`. Shorthand: `lose` |

### `player` block

Compiles to the `player` table (single row).

| Field        | Type      | Required | Notes |
|--------------|-----------|----------|-------|
| `start_room` | id        | yes      | References a room id. Shorthand: `start` |
| `hp`         | integer   | no       | Default 100 |
| `max_hp`     | integer   | no       | Default 100 |


## 4. Entity Declarations

### 4.1 Rooms

```zorkscript
room cellar {
  name        "The Cellar"
  description "Damp stone walls sweat in the lamplight. A rusted shelf
               holds forgotten jars. Water drips from somewhere above."
  short       "A damp cellar beneath the house."
  first_visit "The smell hits you first -- mildew and something sharper."
  dark        false
  start       false

  exit north -> hall
  exit down  -> vault (locked) "A trapdoor in the floor."
}
```

Compiles to the `rooms` table.

| Field               | Type    | Required | Default |
|---------------------|---------|----------|---------|
| `name`              | string  | yes      | |
| `description`       | string  | yes      | |
| `short_description` | string  | yes      | Shorthand: `short` |
| `first_visit`       | string  | no       | Maps to `first_visit_text` |
| `is_dark`           | boolean | no       | false. Shorthand: `dark` |
| `is_start`          | boolean | no       | false. Shorthand: `start` |

#### Inline exits

Exits can be declared inline inside a room block. The exit ID is
auto-generated as `{from_room}_{direction}`.

```zorkscript
exit north -> hall                        # cellar_north
exit down  -> vault (locked)              # cellar_down, is_locked = true
exit east  -> secret_room (hidden) "A crack in the wall."
```

Parenthetical modifiers: `(locked)`, `(hidden)`, or `(locked, hidden)`.
An optional trailing string sets the exit description.

### 4.2 Exits

Exits can also be declared as standalone blocks. Use this form when you
need an explicit exit ID.

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
  name        "Rusty Key"
  description "A small iron key, red with rust."
  examine     "The teeth are worn but intact. It might still work."
  in          cellar
  takeable    true
  visible     true

  # Optional messaging
  take_msg    "You pocket the key. It leaves rust on your fingers."
  room_desc   "A rusty key lies on the shelf."
  home        cellar
}
```

Compiles to the `items` table. The `examine` field maps to
`examine_description`.

Items support all fields from the schema. The most common fields are
listed below. Shorthand aliases (preferred in new code) are shown in
the Notes column.

| Field                 | Type    | Required | Default | Notes |
|-----------------------|---------|----------|---------|-------|
| `name`                | string  | yes      | | |
| `description`         | string  | yes      | | |
| `examine_description` | string  | yes      | | Shorthand: `examine` or `examine_text` |
| `room_id`             | id      | no       | null (not placed yet) | Shorthand: `in`. Auto-reclassified to `container_id` if the target is an item. |
| `container_id`        | id      | no       | null | |
| `is_takeable`         | boolean | no       | true | Shorthand: `takeable` |
| `is_visible`          | boolean | no       | true | Shorthand: `visible` |
| `is_consumed_on_use`  | boolean | no       | false | Shorthand: `consumable` |
| `take_message`        | string  | no       | | Shorthand: `take_msg` |
| `drop_message`        | string  | no       | | Shorthand: `drop_msg` |
| `room_description`    | string  | no       | | Shorthand: `room_desc`. **Required** when `home` is set. Shown when item is in home room. |
| `drop_description`    | string  | no       | | Shorthand: `drop_desc`. Shown when item is away from home. |
| `read_description`    | string  | no       | | Shorthand: `read_text` |
| `home_room_id`        | id      | no       | | Shorthand: `home`. When set, `room_desc` is **required** (compile-time error). |
| `category`            | string  | no       | | |
| `item_tags`           | list    | no       | `["weapon", "light_source", ...]` | Shorthand: `tags` |
| `requires_item_id`    | id      | no       | | Shorthand: `requires`. Item dependency (e.g. flashlight requires batteries). |
| `requires_message`    | string  | no       | | Shorthand: `requires_msg` |

#### Container items

```zorkscript
item wooden_chest {
  name        "Wooden Chest"
  description "A heavy oak chest bound with iron bands."
  examine     "The lock is old but sturdy."
  in          cellar
  takeable    false
  container   true
  locked      true
  key         rusty_key
  consume_key true
  category    "furniture"
  open_msg    "The lid creaks open."
  unlock_msg  "The lock clicks and falls away."
  lock_msg    "The chest is locked."
  search_msg  "You rummage through the chest."
}
```

Container-specific fields:

| Field              | Type    | Default | Notes |
|--------------------|---------|---------|-------|
| `is_container`     | boolean | false   | Shorthand: `container` |
| `is_open`          | boolean | false   | Shorthand: `open` |
| `has_lid`          | boolean | | |
| `is_locked`        | boolean | false   | Shorthand: `locked` |
| `key_item_id`      | id      | | Shorthand: `key` |
| `consume_key`      | boolean | | |
| `open_message`     | string  | | Shorthand: `open_msg` |
| `unlock_message`   | string  | | Shorthand: `unlock_msg` |
| `lock_message`     | string  | | Shorthand: `lock_msg` |
| `search_message`   | string  | | Shorthand: `search_msg` |
| `accepts_items`    | list    | | Shorthand: `accepts` |
| `reject_message`   | string  | | Shorthand: `reject_msg` |

#### Toggleable items

```zorkscript
item oil_lamp {
  name          "Oil Lamp"
  description   "A brass lamp with a wick."
  examine       "The oil reservoir is half full."
  in            cellar
  toggle        true
  toggle_state  "off"
  on_msg        "The flame catches and steadies."
  off_msg       "You snuff the flame."
  tags          ["light_source"]
}
```

Toggle-specific fields:

| Field                | Type    | Default | Notes |
|----------------------|---------|---------|-------|
| `is_toggleable`      | boolean | false   | Shorthand: `toggle` |
| `toggle_state`       | string  | | Shorthand: `toggle_default` |
| `toggle_on_message`  | string  | | Shorthand: `on_msg` |
| `toggle_off_message` | string  | | Shorthand: `off_msg` |
| `toggle_states`      | list    | | Shorthand: `states`. Multi-state toggles. |
| `toggle_messages`    | list    | | Shorthand: `state_msgs`. Messages per state. |

#### Quantity items

```zorkscript
item revolver {
  name           "Revolver"
  description    "A six-shot revolver."
  examine        "Four rounds remain."
  in             study
  quantity       4
  max_quantity   6
  quantity_unit  "rounds"
  depleted_msg   "Click. Empty."
  quantity_desc  "The {name} has {quantity} {unit} remaining."
  tags           ["weapon", "firearm"]
}
```

Quantity-specific fields:

| Field                  | Type    | Default | Notes |
|------------------------|---------|---------|-------|
| `quantity`             | integer | | |
| `max_quantity`         | integer | | |
| `quantity_unit`        | string  | | Shorthand: `quantity_unit` |
| `depleted_message`     | string  | | Shorthand: `depleted_msg` |
| `quantity_description` | string  | | Shorthand: `quantity_desc` |

### 4.4 NPCs

```zorkscript
npc old_wizard {
  name        "The Old Wizard"
  description "A stooped figure in threadbare robes."
  examine     "His eyes are sharp despite his age."
  in          tower_study
  home        tower_study
  room_desc   "An old wizard sits hunched over a heavy tome, muttering to himself."
  dialogue    "He peers at you over his spectacles."
  category    "character"
}
```

Compiles to the `npcs` table.

NPCs support `home`, `room_desc`, and `drop_desc` identically to items.
When an NPC is in its home room, the engine renders `room_desc` as authored
prose blended into the room description. When the NPC is in a different room
(e.g., moved via `move_npc`), the engine uses `drop_desc` if available, or
falls back to the generic "Nearby, {name} lingers." message.

**Required**: When `home` is set, `room_desc` is mandatory (compile-time error).
NPCs without `home` receive the "Nearby..." fallback in all rooms.

**Template NPCs**: NPCs defined without an `in` field are *templates* -- they
exist in limbo (no room) until spawned at runtime via `spawn_npc(npc_id, room_id)`.
Use this for enemies that appear during events, reinforcements, or wave spawns.
For multiple instances, define numbered templates (`shadow_1`, `shadow_2`, etc.).

```zorkscript
-- Template NPC: no "in" field means it starts in limbo
npc shadow_creature {
  name "Shadow Creature"
  description "A writhing mass of darkness."
  examine "Its form shifts and writhes."
  dialogue "It hisses at you."
  category "enemy"
  hp 30
}

-- Spawn it during gameplay
when flag_set(defense_started) {
  effect spawn_npc(shadow_creature, inn_balcony)
  message "A shadow creature materializes on the balcony!"
}
```

| Field              | Type    | Required | Default | Notes |
|--------------------|---------|----------|---------|-------|
| `name`             | string  | yes      | | |
| `description`      | string  | yes      | | |
| `examine_description` | string | yes   | | Shorthand: `examine` or `examine_text` |
| `room_id`          | id      | no       | (template) | Shorthand: `in`. Omit to create a template NPC (spawned at runtime via `spawn_npc`). |
| `default_dialogue` | string  | yes      | | Shorthand: `dialogue` |
| `is_alive`         | boolean | no       | true | |
| `is_blocking`      | boolean | no       | false | Set automatically by `blocking` directive |
| `blocked_exit_id`  | id      | no       | | Set automatically by `blocking` directive |
| `unblock_flag`     | id      | no       | Field name: `unblock` |
| `hp`               | integer | no       | | |
| `damage`           | integer | no       | | |
| `category`         | string  | no       | | |
| `home_room_id`     | id      | no       | | Shorthand: `home`. When set, `room_desc` is **required**. |
| `room_description` | string  | no       | | Shorthand: `room_desc`. Shown when NPC is in home room. |
| `drop_description` | string  | no       | | Shorthand: `drop_desc`. Shown when NPC is away from home. |
| `disposition`      | string  | no       | `"neutral"` | `"hostile"`, `"friendly"`, `"neutral"`. Hostile NPCs refuse dialogue. Changed at runtime via `set_disposition` effect. |

#### Blocking NPCs

An NPC can block an exit using the `blocking` directive. The parser
resolves the exit by `from -> to direction` and sets `is_blocking` and
`blocked_exit_id` automatically.

```zorkscript
npc guard {
  name     "The Guard"
  ...
  blocking gate_room -> courtyard north
  unblock  guard_bribed
}
```

#### Inline dialogue (`talk` blocks)

Dialogue trees can be declared inline inside an NPC block using `talk`
sub-blocks. The first `talk` block is automatically marked as the root
dialogue node. Node IDs are generated as `{npc_id}_{label}`.

```zorkscript
npc guard {
  name        "The Guard"
  description "A heavyset man in dented armor."
  examine     "His eyes are bloodshot."
  in          gate_room
  dialogue    "He barely looks up."
  category    "character"
  blocking    gate_room -> courtyard north
  unblock     guard_bribed

  talk root {
    "Another rat from the cells. Go back."
    option "I have something for you." -> bribe {
      require_item silver_key
    }
    option "What's beyond the gate?" -> gate_info
    option "I'll find another way."
  }

  talk gate_info {
    "Courtyard. Sunlight. None of which concerns you."
    option "I'll be back." -> root
    option "Forget it."
  }

  talk bribe {
    "His eyes fix on the key. He pockets it. 'Fine. Go.'"
    effect remove_item(silver_key)
    effect add_score(10)
    sets [guard_bribed]
  }
}
```

Talk block syntax:
- The first string in the block is the `content`.
- `option "text" -> label` adds a dialogue option pointing to another
  talk block on the same NPC. Use `-> end` for terminal options. Omit
  the arrow entirely for terminal options too.
- Options can have a sub-block with `require_flag`, `exclude_flag`,
  `require_item`, `set_flags`, `required_flags`, `excluded_flags`,
  `required_items`.
- `sets [flag1, flag2]` sets flags when the dialogue node is visited.
- `effect name(args)` executes effects when the node is visited, using
  the same syntax and effect types as `on` and `when` blocks. Effects
  fire before the player sees options. Multiple `effect` lines are
  allowed.

Option IDs are auto-generated as `{node_id}_opt_{index}`.

### 4.5 Locks

Locks can reference their target exit by ID or by route.

```zorkscript
# By exit ID
lock dungeon_door_lock {
  type         "key"
  target_exit  dungeon_entrance_to_hall
  key          rusty_key
  locked       "The iron door is locked."
  unlocked     "The lock clicks open."
  consume      true
}

# By exit route (preferred with inline exits)
lock portcullis_lock {
  exit     gate_room -> courtyard north
  type     "flag"
  flags    [door_raised]
  locked   "The portcullis is lowered."
  unlocked "The portcullis rises."
}
```

Compiles to the `locks` table.

| Field            | Type    | Required | Default | Notes |
|------------------|---------|----------|---------|-------|
| `lock_type`      | string  | yes      | | `"key"`, `"puzzle"`, `"flag"`, `"combination"`, `"npc"`. Shorthand: `type` |
| `target_exit_id` | id      | yes      | | Shorthand: `target_exit`. Or use `exit from -> to direction` route syntax. |
| `key_item_id`    | id      | no       | | For key-type locks. Shorthand: `key` |
| `puzzle_id`      | id      | no       | | For puzzle-type locks. Shorthand: `puzzle` |
| `combination`    | string  | no       | | For combination-type locks |
| `required_flags` | id-list | no       | | For flag-type locks. Shorthand: `flags` |
| `locked_message` | string  | yes      | | Shorthand: `locked` |
| `unlock_message` | string  | yes      | | Shorthand: `unlocked` |
| `is_locked`      | boolean | no       | true | |
| `consume_key`    | boolean | no       | true | Shorthand: `consume` |

### 4.6 Puzzles

```zorkscript
puzzle lever_and_statue {
  name        "The Lever and the Statue"
  description "Two mechanisms work in tandem."
  in          mechanism_room
  difficulty  2
  score       25
  is_optional false
  steps       ["Pull the lever in the mechanism room",
               "Push the statue in the great hall"]
  hint        ["Something clicks deep in the walls.",
               "The statue seems anchored from below."]
}
```

Compiles to the `puzzles` table.

| Field            | Type       | Required | Default | Notes |
|------------------|------------|----------|---------|-------|
| `name`           | string     | yes      | | |
| `description`    | string     | yes      | | |
| `room_id`        | id         | yes      | | Shorthand: `in` |
| `difficulty`     | integer    | no       | 1 | |
| `score_value`    | integer    | no       | 0 | Shorthand: `score` |
| `is_optional`    | boolean    | no       | false | |
| `is_solved`      | boolean    | no       | false | |
| `solution_steps` | string-list| no       | JSON array | Shorthand: `steps` |
| `hint_text`      | string-list| no       | JSON array | Shorthand: `hint` |

### 4.7 Flags

Flags support both a single-line form and a block form.

```zorkscript
# Single-line form (preferred)
flag dungeon_door_opened "The dungeon door has been opened"

# Block form
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

The quest type can be specified with a `main:` or `side:` prefix before
the quest ID, or with a `quest_type` field inside the block.

Objectives use an inline shorthand: `objective "description" -> flag`.

```zorkscript
quest main:seal_the_gate {
  name        "Seal the Mountain Gate"
  description "Find the three keys and seal the gate."
  discovery   met_wizard
  completion  gate_sealed
  failure     wizard_killed
  fail_message "The wizard is dead. The gate can never be sealed."
  score       50
  sort_order  0

  objective "Retrieve the enchanted amulet" -> has_amulet (bonus: 10)
  objective "Find the crystal shard" -> has_crystal (bonus: 10)
  objective "Explore the hidden crypt" -> explored_crypt (optional, bonus: 5)
}
```

Compiles to the `quests` and `quest_objectives` tables. Objectives are
nested inside the quest block.

Quest fields:

| Field             | Type    | Required | Default | Notes |
|-------------------|---------|----------|---------|-------|
| `name`            | string  | yes      | | |
| `description`     | string  | yes      | | |
| `quest_type`      | string  | yes      | | `"main"` or `"side"`. Can use prefix syntax: `quest main:id` |
| `discovery_flag`  | id      | no       | | Shorthand: `discovery` |
| `completion_flag` | id      | yes      | | Shorthand: `completion` |
| `failure_flag`    | id      | no       | | Shorthand: `failure`. When this flag is set, quest transitions to failed and objectives lock. |
| `fail_message`    | string  | no       | | Authored flavor text displayed when the quest fails. Falls back to `description` if omitted. |
| `score_value`     | integer | no       | 0 | Shorthand: `score` |
| `sort_order`      | integer | no       | 0 | |

Objective inline syntax:

```
objective "description" -> completion_flag (modifiers)
```

Modifiers (in parentheses, comma-separated):
- `optional` -- marks the objective as optional
- `bonus: N` -- sets the bonus score
- `order: N` -- overrides the auto-assigned order index

Objective IDs are auto-generated as `{quest_id}_obj_{index}`.

The older named-block form is also supported:

```zorkscript
objective obj_find_amulet {
  description     "Retrieve the enchanted amulet."
  completion_flag has_amulet
  order_index     0
  is_optional     false
  bonus_score     10
}
```


## 5. Command Blocks

Commands define player-initiated actions. Each command is a pattern-matching
rule with preconditions and effects.

There are two forms: the named `command` block and the shorthand `on` block.

### Named `command` block

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

### Shorthand `on` block

The `on` form auto-generates an ID and extracts the verb from the
pattern. Use this for concise command definitions.

```zorkscript
on "pull {target}" in [supply_closet] {
  require not_flag(lever_pulled)

  effect set_flag(lever_pulled)
  effect add_score(15)

  success "You heave the lever down. Chains rattle."
  fail    "The lever is already down."
  once
}

# Global fallback (no room scope)
on "pull {target}" {
  success "There's nothing here you can pull."
}
```

`on` block fields:

| Field     | Type         | Notes |
|-----------|--------------|-------|
| pattern   | string       | The quoted pattern after `on`. Verb is extracted automatically. |
| `in`      | id or id-list| Optional room scope. `in room_id` or `in [room1, room2]`. |
| `require` | precondition | 0+. Same syntax as `command`. |
| `effect`  | effect       | 0+. Same syntax as `command`. |
| `success` | string       | Maps to `success_message`. |
| `fail`    | string       | Maps to `failure_message`. |
| `done`    | string       | Maps to `done_message`. |
| `priority`| integer      | Default 0. |
| `once`    | keyword      | Sets `one_shot` to true. |

### `command` block structure

| Field       | Type        | Required | Notes |
|-------------|-------------|----------|-------|
| `verb`              | string      | yes      | First word of input. Lowercased. Auto-extracted from `pattern` if omitted. |
| `pattern`           | string      | yes      | Full pattern with `{slot}` placeholders |
| `in_rooms`          | id-list     | no       | Maps to `context_room_ids`. Omit for global. |
| `one_shot`          | boolean     | no       | Default false |
| `priority`          | integer     | no       | Default 0. Higher = evaluated first. |
| `puzzle_id`         | id          | no       | Associate with a puzzle. |
| `require`           | precondition| 0+       | All must pass for the command to fire. |
| `success_message`   | string      | no       | Displayed on success. |
| `on_fail`           | string      | no       | Maps to `failure_message` |
| `on_done`           | string      | no       | Maps to `done_message` (for re-fired one-shots) |
| `effect`            | effect      | 1+       | Executed in order when preconditions pass. |

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

# NPC disposition checks
require npc_disposition(guard, "hostile")
require npc_disposition(old_wizard, "friendly")

# Variable checks
require var_check(jaheira_approval, >=, 50)
require var_check(turn_count, ==, 0)
require var_check(cave_floods, <, 3)
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
| `npc_disposition(N, D)`   | npc id, disposition string  | `{"type": "npc_disposition", "npc": N, "disposition": D}` |
| `var_check(N, OP, V)`    | variable name, operator, integer | `{"type": "var_check", "name": N, "operator": OP, "value": V}` |

Operators for `var_check`: `==`, `!=`, `>`, `<`, `>=`, `<=`. Variables
that have not been set default to `0`.

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
effect make_visible(hidden_gem)
effect make_hidden(decoy_item)
effect make_takeable(mounted_sword)
effect move_npc(old_wizard, tower_study)
effect spawn_npc(shadow_creature, inn_balcony)
effect set_disposition(guard, "hostile")
effect force_dialogue(old_wizard, wizard_angry)
effect set_var(jaheira_approval, 0)
effect change_var(jaheira_approval, 10)
effect change_var(cave_floods, -1)
effect schedule_trigger(bomb_explodes, 3)
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
| `make_visible(I)`            | item id                    | `{"type": "make_visible", "item": I}` |
| `make_hidden(I)`             | item id                    | `{"type": "make_hidden", "item": I}` |
| `make_takeable(I)`           | item id                    | `{"type": "make_takeable", "item": I}` |
| `move_npc(NPC, R)`           | npc id, room id or `_current` | `{"type": "move_npc", "npc": NPC, "room": R}` |
| `spawn_npc(NPC, R)`         | npc id, room id or `_current` | `{"type": "spawn_npc", "npc": NPC, "room": R}` |
| `set_disposition(NPC, D)`   | npc id, disposition string | `{"type": "set_disposition", "npc": NPC, "disposition": D}` |
| `force_dialogue(NPC, NODE)` | npc id, dialogue node id   | `{"type": "force_dialogue", "npc": NPC, "node": NODE}` |
| `set_var(N, V)`            | variable name, integer     | `{"type": "set_var", "name": N, "value": V}` |
| `change_var(N, D)`         | variable name, integer delta (+ or -) | `{"type": "change_var", "name": N, "delta": D}` |
| `schedule_trigger(ID, N)` | trigger id, integer turns  | `{"type": "schedule_trigger", "trigger": ID, "turns": N}` |

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

There are two forms: the named `trigger` block and the shorthand `when`
block.

### Named `trigger` block

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

| Field     | Type        | Required | Notes |
|-----------|-------------|----------|-------|
| `on`      | string      | yes      | Event type. See below. |
| `when`    | key=value   | 0+       | Event data filters. Compiled to `event_data` JSON. |
| `one_shot`| boolean     | no       | Default false |
| `priority`| integer     | no       | Default 0. Higher = evaluated first. |
| `require` | precondition| 0+       | Same syntax as commands. |
| `effect`  | effect      | 0+       | Same syntax as commands. |
| `message` | string      | no       | Display text when trigger fires. |

### Shorthand `when` block

The `when` form uses function-call syntax for the event and
auto-generates an ID as `when_{event}_{arg}`.

```zorkscript
when room_enter(courtyard) {
  require has_flag(guard_bribed)

  effect set_flag(escaped_dungeon)
  effect add_score(15)

  message "You climb the stairs into blinding sunlight. Free."
  once
}
```

`when` block fields:

| Field     | Type         | Notes |
|-----------|--------------|-------|
| event     | func-call    | `event_type(event_arg)` after `when`. |
| `require` | precondition | 0+. Same syntax as `trigger`. |
| `effect`  | effect       | 0+. Same syntax as `trigger`. |
| `message` | string       | Display text when trigger fires. |
| `priority`| integer      | Default 0. |
| `once`    | keyword      | Sets `one_shot` to true. |

### Event types

| Event Type       | `when` fields       | Fired when... |
|------------------|---------------------|---------------|
| `room_enter`     | `room_id`           | Player enters a room |
| `flag_set`       | `flag`              | A flag is set to true |
| `dialogue_node`  | `node_id`           | A dialogue node is visited |
| `item_taken`     | `item_id`           | Player takes an item |
| `item_dropped`   | `item_id`           | Player drops an item |
| `command_exec`   | `command_id`        | A DSL command executes successfully |
| `on_item_stolen` | `npc_id`            | Player takes an item from a room while an NPC is present (theft) |
| `on_attacked`    | `npc_id`            | Player attacks an NPC (via weapon interaction or `attack` verb) |
| `turn_count`     | `n`                 | Player's move counter reaches exactly N |
| `scheduled`      | `trigger_id`        | A `schedule_trigger` deadline arrives |

### `when` clause compilation (named `trigger` form)

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

In the shorthand `when` form, the event argument is mapped automatically:
`when room_enter(hut)` compiles to `{"event_type": "room_enter", "event_data": {"room_id": "hut"}}`.

### Trap blocks

A `trap` is a first-class trigger subtype for environmental hazards. It compiles
to a regular trigger row with an additional `disarm_flag` column.

```zorkscript
trap spike_pit {
  on       room_enter
  when     room_id = dungeon_corridor
  disarm   spike_pit_disarmed

  require not_flag(spike_pit_disarmed)

  effect change_health(-25)
  effect set_flag(spike_pit_triggered)

  message "The floor gives way beneath you! Spikes tear at your legs."
  once
}
```

| Field     | Type        | Required | Notes |
|-----------|-------------|----------|-------|
| `on`      | string      | yes      | Event type (`room_enter`, `item_taken`, `command_exec`, etc). |
| `when`    | key=value   | 0+       | Event data filters. Same as `trigger`. |
| `disarm`  | string      | no       | Flag ID. When this flag is set, the trap is skipped. |
| `require` | precondition| 0+       | Same syntax as triggers/commands. |
| `effect`  | effect      | 0+       | Same syntax as triggers/commands. |
| `message` | string      | no       | Display text when the trap fires. |
| `priority`| integer     | no       | Default 0. Higher = evaluated first. |
| `once`    | keyword     | no       | Sets `one_shot` to true (fire only once). |

The `disarm` field (alias: `disarm_flag`) is checked at runtime *before*
preconditions. If the named flag is set in game state, the trap silently
does nothing.

### `command_exec` event type

The `command_exec` event fires after a DSL command executes successfully.
Use `command_id` in event data to target a specific command:

```zorkscript
trap cursed_lever {
  on       command_exec
  when     command_id = pull_lever

  effect change_health(-10)
  message "The lever sends a shock through your body!"
  once
}
```


### Reactive NPC triggers

NPCs react deterministically to player behavior using `on_item_stolen` and
`on_attacked` events combined with the `set_disposition` and `force_dialogue`
effects.

#### Theft detection

When a player takes an item from a room, every living NPC in that room
fires an `on_item_stolen` event. Use triggers to change NPC disposition
and force a reaction dialogue:

```zorkscript
when on_item_stolen(shopkeeper) {
  effect set_disposition(shopkeeper, "hostile")
  effect force_dialogue(shopkeeper, shopkeeper_angry)
  message "The shopkeeper catches you red-handed!"
  once
}
```

#### Attack reaction

`on_attacked` fires from **two independent paths**:

1. **The `attack` verb** -- `attack <npc>` always emits the event, whether the
   player is bare-handed or wielding a weapon.
2. **Weapon-on-NPC interactions** -- `use <weapon> on <npc>` (or any interaction
   matrix match where a weapon-tagged item targets an NPC) also emits the event.

Both paths include `npc_id`, `item_id`, and `room_id` in the event data
(`item_id` is empty for bare-handed attacks).

> **`once` flag note:** Because the event can fire from either path, a trigger
> marked `once` will fire on whichever happens first and then suppress on the
> other. If your game supports both `attack guard` and `use sword on guard`,
> design your triggers accordingly (e.g., use a flag guard instead of `once` if
> you need to react to both paths independently).

```zorkscript
when on_attacked(guard) {
  effect set_disposition(guard, "hostile")
  effect set_flag(guard_hostile)
  message "The guard draws his sword!"
}
```

#### NPC disposition

Every NPC has a `disposition` field: `"neutral"` (default), `"friendly"`,
or `"hostile"`. When hostile, the engine blocks dialogue initiation
(the player sees "X refuses to speak with you.").

Use the `set_disposition(npc, disposition)` effect to change disposition
at runtime, and the `npc_disposition(npc, disposition)` precondition to
gate commands and triggers on current disposition.

```zorkscript
npc guard {
  name        "The Guard"
  description "A stern soldier."
  examine     "He watches you intently."
  in          gate_room
  dialogue    "State your business."
  disposition "neutral"
  category    "character"
}
```

#### Forced dialogue

The `force_dialogue(npc, node)` effect jumps the player into a specific
dialogue node, rendering it immediately. If the node has options, the
dialogue loop continues from there.

```zorkscript
trigger thief_caught {
  on       on_item_stolen
  when     npc_id = merchant

  effect set_disposition(merchant, "hostile")
  effect force_dialogue(merchant, merchant_accuses)

  message "The merchant slams a fist on the counter."
  once
}
```


### Variables

Variables are general-purpose integer counters stored in the `variables`
table. Unlike flags (which are boolean), variables hold any integer value
and support arithmetic. Use them for NPC approval ratings, skill checks,
environmental counters, and any numeric state that flags cannot represent.

Variables are created on first use -- there is no declaration block. A
variable that has never been set reads as `0`.

#### Setting and changing variables

```zorkscript
# Set a variable to an exact value
effect set_var(jaheira_approval, 0)

# Increment or decrement a variable
effect change_var(jaheira_approval, 10)
effect change_var(cave_floods, -1)
```

`set_var(name, value)` creates the variable if it does not exist, or
overwrites it if it does. `change_var(name, delta)` adds `delta` to the
current value (creating the variable at `delta` if it does not exist).

#### Checking variables

```zorkscript
require var_check(jaheira_approval, >=, 50)
require var_check(turn_count, ==, 0)
require var_check(cave_floods, <, 3)
```

`var_check(name, operator, value)` compares the variable against an
integer threshold. Supported operators: `==`, `!=`, `>`, `<`, `>=`, `<=`.

#### Example: NPC approval gating

A player must accumulate approval before an NPC will help them:

```zorkscript
on "compliment jaheira" {
  effect change_var(jaheira_approval, 10)
  effect print("Jaheira nods approvingly.")
  success "You compliment Jaheira."
}

on "ask jaheira for help" {
  require var_check(jaheira_approval, >=, 50)
  effect set_flag(jaheira_joined)
  success "Jaheira agrees to help you."
  fail "Jaheira is not interested in helping you."
}
```

#### Example: environmental counter

Track how many times a cave floods before it becomes impassable:

```zorkscript
when room_enter(flooded_cave) {
  effect change_var(cave_floods, 1)
  effect print("Water rushes through the cave.")
}

on "cross the cave" in [flooded_cave] {
  require var_check(cave_floods, <, 3)
  effect move_player(far_shore)
  success "You wade through the rising water."
  fail "The water is too deep to cross."
}
```

#### Example: skill check threshold

Gate a command on a numeric skill level:

```zorkscript
on "pick lock" in [treasury_door] {
  require var_check(lockpick_skill, >=, 5)
  effect unlock(treasury_lock)
  effect add_score(15)
  success "The lock yields to your practiced hands."
  fail "Your fingers fumble. You lack the skill."
}
```

### Turn-based triggers

Two event types support time-delayed game logic based on the player's
move counter.

#### `turn_count(N)` -- absolute move trigger

Fires when the player's move counter reaches exactly `N`. Useful for
timed events that happen at a fixed point in the game.

```zorkscript
when turn_count(5) {
  require has_flag(bomb_armed)
  effect kill_npc(everyone_nearby)
  message "The bomb detonates."
  once
}
```

#### `schedule_trigger(trigger_id, turns)` -- deferred trigger

Arms a named trigger to fire after `turns` player moves from the
current move. The trigger is identified by its `trigger_id`, which must
match a `when scheduled(trigger_id)` block.

```zorkscript
on "light fuse" in [armory] {
  require has_item(lighter)
  effect schedule_trigger(bomb_explodes, 3)
  success "The fuse is lit."
  once
}

when scheduled(bomb_explodes) {
  effect change_description(armory, "Rubble and smoke.")
  effect kill_npc(armory_guard)
  message "BOOM."
  once
}
```

When `schedule_trigger(bomb_explodes, 3)` executes, the engine records
that the `bomb_explodes` trigger should fire 3 moves later. On the
target move, the engine emits a `scheduled` event with
`trigger_id = bomb_explodes`, which matches the `when scheduled(bomb_explodes)`
block and fires its effects.


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
| `effects`   | effect-list| no       | JSON array of effects (same syntax as `on`/`when` blocks) |

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

| Field      | Type    | Required | Default | Notes |
|------------|---------|----------|---------|-------|
| `tag`      | string  | yes      | | Maps to `item_tag` |
| `target`   | string  | yes      | Use `"*"` for wildcard | Maps to `target_category` |
| `response` | string  | yes      | Template with `{item}` and `{target}` | |
| `consumes` | integer | no       | 0 | |
| `score`    | integer | no       | 0 | Maps to `score_change` |
| `sets_flag`| id      | no       | | Maps to `flag_to_set` |
| `effect`   | effect  | no       | | Repeatable. All standard + target-aware effects |

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
      "is_dark": false,
      "is_start": true
    },
    {
      "id": "courtyard",
      "name": "The Courtyard",
      "description": "Open sky above crumbling walls. Weeds push through cracked flagstones.",
      "short_description": "A crumbling courtyard.",
      "first_visit_text": "Fresh air. Finally.",
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
  intro       "You wake in a stone cellar. The only exit is an iron door."
  win_text    "Daylight. You are free."
  max_score   20
  realism     "medium"
  win         [escaped]
}

player {
  start  cellar
  hp     100
}

# -- World --

room cellar {
  name        "The Cellar"
  description "Damp stone walls sweat in the lamplight. A shelf holds
               forgotten jars. A heavy iron door blocks the north wall."
  short       "A damp cellar."
  first_visit "The smell hits you first."
  start       true

  exit north -> courtyard (locked) "A heavy iron door."
}

room courtyard {
  name        "The Courtyard"
  description "Open sky above crumbling walls. Weeds push through
               cracked flagstones."
  short       "A crumbling courtyard."
  first_visit "Fresh air. Finally."

  exit south -> cellar
}

item iron_key {
  name        "Iron Key"
  description "A blackened iron key."
  examine     "Heavy and cold. The teeth are sharp."
  in          cellar
  room_desc   "An iron key lies half-hidden under a jar."
}

lock cellar_door_lock {
  exit     cellar -> courtyard north
  type     "key"
  key      iron_key
  locked   "The iron door is locked."
  unlocked "The lock grinds open."
  consume  true
}

puzzle escape_cellar {
  name        "Escape the Cellar"
  description "Find the key and unlock the door."
  in          cellar
  difficulty  1
  score       10
  steps       ["Take the iron key", "Use it on the door"]
  hint        ["Look under the jars."]
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

**ZorkScript: ~65 lines, ~1,000 tokens.**

Token reduction: roughly **65%** for equivalent content.


## 10. Compilation Model

### What the compiler does

The ZorkScript compiler is a straightforward transpiler. It parses the
textual DSL and inserts rows into a SQLite compilation cache. There is no
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
  .zork archive (zip)
```

### Parsing strategy

1. **Tokenize** -- split on whitespace, respecting quoted strings and
   bracket-delimited lists.
2. **Block detection** -- recognize `keyword id {` as the start of a block.
   Track brace depth.
3. **Field extraction** -- inside a block, each line is `field_name value`.
   Values are strings, numbers, booleans, identifiers, or bracket-lists.
4. **Nested blocks** -- `quest > objective`, `room > exit`, and
   `npc > talk > option` use nesting. All other blocks are flat.
5. **Function-call syntax** -- `require` and `effect` lines parse as
   `name(arg1, arg2, ...)`.

### Field name mapping

Some ZorkScript field names are abbreviated for readability. The compiler
maps them to their DB column names:

| ZorkScript        | DB column             | Table |
|-------------------|-----------------------|-------|
| `author`          | `author_prompt`       | metadata |
| `intro`           | `intro_text`          | metadata |
| `win`             | `win_conditions`      | metadata |
| `lose`            | `lose_conditions`     | metadata |
| `start`           | `start_room_id`       | player |
| `start_room`      | `start_room_id`       | player |
| `short`           | `short_description`   | rooms |
| `first_visit`     | `first_visit_text`    | rooms |
| `dark`            | `is_dark`             | rooms |
| `examine`         | `examine_description` | items, npcs |
| `in`              | `room_id`             | items, npcs, puzzles |
| `takeable`        | `is_takeable`         | items |
| `visible`         | `is_visible`          | items |
| `container`       | `is_container`        | items |
| `toggle`          | `is_toggleable`       | items |
| `tags`            | `item_tags`           | items |
| `home`            | `home_room_id`        | items, npcs |
| `room_desc`       | `room_description`    | items, npcs |
| `drop_desc`       | `drop_description`    | items, npcs |
| `from`            | `from_room_id`        | exits |
| `to`              | `to_room_id`          | exits |
| `type` (in lock)  | `lock_type`           | locks |
| `target_exit`     | `target_exit_id`      | locks |
| `key` (in lock)   | `key_item_id`         | locks |
| `locked` (in lock)| `locked_message`      | locks |
| `unlocked`        | `unlock_message`      | locks |
| `flags` (in lock) | `required_flags`      | locks |
| `consume`         | `consume_key`         | locks |
| `score`           | `score_value`         | puzzles, quests |
| `steps`           | `solution_steps`      | puzzles |
| `hint`            | `hint_text`           | puzzles |
| `completion`      | `completion_flag`     | quests |
| `discovery`       | `discovery_flag`      | quests |
| `dialogue`        | `default_dialogue`    | npcs |
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
| `tag`             | `item_tag`            | interaction_responses |
| `target`          | `target_category`     | interaction_responses |

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
top_level      = game_block | player_block | entity_block
               | on_block | when_block | flag_line ;

game_block     = "game" "{" { field } "}" ;
player_block   = "player" "{" { field } "}" ;

entity_block   = entity_kw IDENT "{" block_body "}" ;
entity_kw      = "room" | "exit" | "item" | "npc" | "lock" | "puzzle"
               | "quest" | "command" | "trigger"
               | "dialogue" | "option" | "interaction" ;

block_body     = { field | nested_block | require_line | effect_line
               | when_line | inline_exit | talk_block | inline_obj } ;

nested_block   = "objective" IDENT "{" { field } "}" ;
inline_obj     = "objective" STRING [ "->" IDENT ] [ "(" obj_mods ")" ] ;
obj_mods       = obj_mod { "," obj_mod } ;
obj_mod        = "optional" | "bonus" [ ":" ] NUMBER | "order" [ ":" ] NUMBER ;

inline_exit    = "exit" IDENT "->" IDENT [ "(" exit_mods ")" ] [ STRING ] ;
exit_mods      = exit_mod { "," exit_mod } ;
exit_mod       = "locked" | "hidden" ;

talk_block     = "talk" IDENT "{" [ STRING ] { talk_field } "}" ;
talk_field     = "content" STRING | "sets" id_list
               | effect_line
               | "option" STRING [ "->" IDENT ] [ "{" { field } "}" ]
               | field ;

on_block       = "on" STRING [ "in" ( IDENT | id_list ) ] "{" on_body "}" ;
on_body        = { require_line | effect_line | "once"
               | "success" STRING | "fail" STRING | "done" STRING
               | "priority" NUMBER | field } ;

when_block     = "when" func_call "{" when_body "}" ;
when_body      = { require_line | effect_line | "once"
               | "message" STRING | "priority" NUMBER | field } ;

flag_line      = "flag" IDENT [ STRING ]
               | "flag" IDENT "{" { field } "}" ;

field          = IDENT value ;
value          = STRING | NUMBER | BOOLEAN | IDENT | list ;

require_line   = "require" func_call ;
effect_line    = "effect" func_call ;
when_line      = "when" IDENT "=" value ;

func_call      = IDENT "(" arg_list ")" ;
arg_list       = [ arg { "," arg } ] ;
arg            = STRING | NUMBER | BOOLEAN | IDENT | slot_ref ;
slot_ref       = "{" IDENT "}" ;

list           = "[" [ value { "," value } ] "]" ;

IDENT          = /[a-zA-Z_][a-zA-Z0-9_]*/ ;
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
| Lines                   | ~120       | ~65        | 46%     |
| Characters              | ~3,400     | ~1,800     | 47%     |
| Estimated tokens (GPT-4)| ~2,800     | ~1,000     | 64%     |
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
2. **Standard output**: a compiled `.zork` game archive

### What the compiler must NOT do

- Invent new table columns or game mechanics.
- Reorder effects (order is semantically meaningful).
- Merge or deduplicate entities.
- Validate game logic (that is the validator's job, after compilation).


## Appendix A: Complete Precondition and Effect Vocabulary

For quick reference, the full set of precondition and effect types that
ZorkScript wraps.

### Precondition types (19)

```
in_room, has_item, has_flag, not_flag, item_in_room, item_accessible,
npc_in_room, lock_unlocked, puzzle_solved, health_above, container_open,
item_in_container, not_item_in_container, container_has_contents,
container_empty, has_quantity, toggle_state, npc_disposition, var_check
```

### Effect types (34)

```
move_item, remove_item, set_flag, unlock, move_player, spawn_item,
change_health, add_score, reveal_exit, solve_puzzle, discover_quest,
print, open_container, move_item_to_container, take_item_from_container,
consume_quantity, restore_quantity, set_toggle_state, make_visible,
make_hidden, make_takeable, move_npc, spawn_npc, fail_quest, complete_quest,
kill_npc, remove_npc, lock_exit, hide_exit, change_description,
set_disposition, force_dialogue, set_var, change_var, schedule_trigger
```

### Target-aware effect types (4, interaction responses only)

```
kill_target, damage_target, destroy_target, open_target
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
