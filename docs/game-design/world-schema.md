# AnyZork World Schema Reference

> This document defines every database entity in a `.zork` file. It is the authoritative reference for LLMs generating game worlds — if it's not in this schema, the engine can't use it.

## Schema Overview

A `.zork` file is a SQLite database containing these tables:

| Table | Purpose |
|---|---|
| `rooms` | Every location the player can visit |
| `exits` | Connections between rooms (directional or named) |
| `items` | Objects the player can interact with |
| `npcs` | Non-player characters |
| `locks` | Gates that block exits until conditions are met |
| `puzzles` | Multi-step challenges with preconditions and rewards |
| `lore` | Discoverable narrative content at three tiers |
| `commands` | DSL rules that define every possible player action |
| `flags` | Boolean or string state variables that track world state |
| `player` | Single-row table tracking the player's runtime state |
| `dialogue` | NPC dialogue lines gated by state |
| `score_entries` | Log of scored events (populated at runtime) |
| `metadata` | Game-level metadata (title, author prompt, version, seed) |

### Naming Conventions

- All `id` fields use `snake_case`: `rusty_key`, `dungeon_entrance`, `old_wizard`.
- IDs are globally unique within their table.
- Foreign key references use the exact `id` string from the referenced table.
- Boolean fields use `0` (false) and `1` (true).

### Relationship Map

```
rooms ──< exits ──< locks
  │                   │
  │                   ├── references items (key_item_id)
  │                   └── references puzzles (puzzle_id)
  │
  ├──< items (room_id = current location)
  ├──< npcs (room_id = current location)
  ├──< lore (location_id)
  └──< commands (context_room_id, optional)

items ──< lore (item_id)
      ──< commands (references in preconditions/effects)

npcs ──< dialogue (npc_id)
     ──< lore (npc_id)

puzzles ──< commands (puzzle_id)

flags ──< referenced by commands, locks, puzzles, dialogue, lore
```

---

## Table: `rooms`

**Purpose**: Defines every discrete location in the game world. Rooms are the fundamental spatial unit.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | TEXT PRIMARY KEY | Yes | Unique identifier. Use descriptive snake_case: `castle_throne_room`, `dark_forest_clearing`. |
| `name` | TEXT | Yes | Display name shown to the player: "Throne Room", "Forest Clearing". |
| `description` | TEXT | Yes | Full prose description shown on first visit and when the player types `look`. Should weave in visible items, exits, and atmosphere. 3-6 sentences. |
| `short_description` | TEXT | Yes | Abbreviated description shown on revisits. 1-2 sentences that orient the player. |
| `first_visit_text` | TEXT | No | One-time text shown before the description on the very first visit. Used for triggered events, cutscenes, or dramatic reveals. |
| `region` | TEXT | Yes | Region grouping: "Castle", "Forest", "Caves". Used for theming and progression tracking. |
| `is_dark` | INTEGER | Yes | `0` = lit, `1` = dark (requires light source to see). Default `0`. |
| `is_start` | INTEGER | Yes | `1` for the starting room (exactly one room must have this). All others `0`. |
| `visited` | INTEGER | Yes | Runtime state. Always initialize to `0`. Engine sets to `1` on first visit. |

### Example Row

```json
{
  "id": "castle_gatehouse",
  "name": "Castle Gatehouse",
  "description": "A squat stone building straddles the road, its iron portcullis raised just high enough to duck under. Arrow slits line both walls, dark and watchful. A faded banner bearing a silver stag hangs from a rusted bracket above the passage. To the north, the castle courtyard opens up. A narrow staircase spirals upward along the east wall.",
  "short_description": "The gatehouse passage. The portcullis hangs overhead. North leads to the courtyard; stairs climb east.",
  "first_visit_text": "As you step beneath the portcullis, a raven launches from the battlements above, its cry echoing off the stone. Something about this place feels watched.",
  "region": "Castle",
  "is_dark": 0,
  "is_start": 1,
  "visited": 0
}
```

---

## Table: `exits`

**Purpose**: Defines every connection between rooms. Each exit is a one-way link; bidirectional connections require two exit rows.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | TEXT PRIMARY KEY | Yes | Unique identifier: `castle_gatehouse_to_courtyard`. |
| `from_room_id` | TEXT REFERENCES rooms(id) | Yes | The room this exit leads FROM. |
| `to_room_id` | TEXT REFERENCES rooms(id) | Yes | The room this exit leads TO. |
| `direction` | TEXT | Yes | How the player activates this exit. Standard directions: `north`, `south`, `east`, `west`, `northeast`, `northwest`, `southeast`, `southwest`, `up`, `down`. Custom exits: any short phrase like `enter cave`, `climb ladder`, `cross bridge`. |
| `description` | TEXT | No | Optional text describing the exit, shown in room descriptions or via `look`. Example: "A narrow staircase spirals upward along the east wall." |
| `is_locked` | INTEGER | Yes | `0` = passable, `1` = locked (requires a lock entry to define how to unlock). Default `0`. |
| `is_hidden` | INTEGER | Yes | `0` = visible in room description, `1` = hidden until revealed by a command effect. Default `0`. |

### Example Rows

```json
[
  {
    "id": "gatehouse_to_courtyard",
    "from_room_id": "castle_gatehouse",
    "to_room_id": "castle_courtyard",
    "direction": "north",
    "description": "The passage opens into a wide courtyard.",
    "is_locked": 0,
    "is_hidden": 0
  },
  {
    "id": "courtyard_to_gatehouse",
    "from_room_id": "castle_courtyard",
    "to_room_id": "castle_gatehouse",
    "direction": "south",
    "description": "The gatehouse lies to the south.",
    "is_locked": 0,
    "is_hidden": 0
  },
  {
    "id": "gatehouse_to_watchtower",
    "from_room_id": "castle_gatehouse",
    "to_room_id": "castle_watchtower",
    "direction": "up",
    "description": "A narrow staircase spirals upward.",
    "is_locked": 1,
    "is_hidden": 0
  }
]
```

### Notes

- **Always create exit pairs** for bidirectional connections. If the player can go north from A to B, create a south exit from B to A.
- **One-way exits** are valid but should be used sparingly and with narrative justification (falling through a trapdoor, sliding down a chute). The player should be warned or it should be obvious.
- **Hidden exits** start with `is_hidden = 1` and are revealed by a command effect (`reveal_exit`). The player cannot see or use them until revealed.

---

## Table: `items`

**Purpose**: Every object in the game world — things the player can take, examine, use, or observe.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | TEXT PRIMARY KEY | Yes | Unique identifier: `rusty_key`, `silver_chalice`. |
| `name` | TEXT | Yes | Display name: "rusty key", "silver chalice". Lowercase, as it appears in prose. |
| `description` | TEXT | Yes | Short description shown when the item is listed in a room or inventory. 1 sentence. |
| `examine_description` | TEXT | Yes | Detailed description shown when the player examines the item. 2-4 sentences. This is where clues are embedded. |
| `room_id` | TEXT REFERENCES rooms(id) | No | Current location. `NULL` if in player inventory or not yet spawned. |
| `is_takeable` | INTEGER | Yes | `1` = player can pick this up. `0` = scenery (can examine but not take). |
| `is_visible` | INTEGER | Yes | `1` = appears in room descriptions. `0` = hidden until spawned by a command effect. Default `1`. |
| `is_consumed_on_use` | INTEGER | Yes | `1` = removed from inventory/room after use. `0` = persists. Default `0`. |
| `take_message` | TEXT | No | Custom message when the player takes the item. If NULL, engine uses default: "Taken." |
| `drop_message` | TEXT | No | Custom message when the player drops the item. If NULL, engine uses default: "Dropped." |
| `weight` | INTEGER | No | Optional weight for inventory-limit games. Default `1`. |
| `category` | TEXT | No | Optional grouping: `key`, `tool`, `weapon`, `treasure`, `document`, `scenery`. Helps the engine with generic commands. |
| `room_description` | TEXT | No | A prose sentence describing how the item appears in its room. Appended dynamically to the room description at render time. When the item is taken or removed, the sentence disappears automatically. Example: `"A rusty iron key hangs from a hook beside the window."` Takeable items should ALWAYS use this field instead of being mentioned in the base room description, so the text stays accurate when the item is no longer present. Scenery items (`is_takeable = 0`) may use this field or be mentioned in the base room description, since they never move. |

### Example Rows

```json
[
  {
    "id": "rusty_key",
    "name": "rusty key",
    "description": "A small iron key, spotted with rust.",
    "examine_description": "The key is old and pitted with corrosion, but the teeth are still intact. The bow is stamped with a maker's mark — a stag's head, the same crest as the banner above the gatehouse. This must open something in the castle.",
    "room_id": "castle_watchtower",
    "is_takeable": 1,
    "is_visible": 1,
    "is_consumed_on_use": 1,
    "take_message": "You pocket the key. It's lighter than it looks.",
    "drop_message": "You set the key down carefully.",
    "weight": 1,
    "category": "key"
  },
  {
    "id": "courtyard_fountain",
    "name": "stone fountain",
    "description": "A cracked stone fountain stands in the center of the courtyard, long dry.",
    "examine_description": "The fountain basin is shaped like a shallow bowl, its rim carved with ivy motifs. At the center, a stone figure of a woman holds an empty urn overhead. Around the base, you notice faint scratches — letters? They read: 'WHEN THE MOON DRINKS, THE PATH OPENS.' The basin is bone dry.",
    "room_id": "castle_courtyard",
    "is_takeable": 0,
    "is_visible": 1,
    "is_consumed_on_use": 0,
    "take_message": null,
    "drop_message": null,
    "weight": null,
    "category": "scenery"
  },
  {
    "id": "moonstone",
    "name": "moonstone",
    "description": "A smooth, luminous white stone that seems to glow faintly.",
    "examine_description": "The stone is perfectly round and cool to the touch, as though it carries the chill of a winter night. In the right light, it seems to shimmer with an inner radiance. It's about the size of a plum — it would fit perfectly in a cupped hand, or a shallow basin.",
    "room_id": null,
    "is_takeable": 1,
    "is_visible": 0,
    "is_consumed_on_use": 1,
    "take_message": "You cradle the moonstone. It pulses gently against your palm.",
    "drop_message": "You set the moonstone down. Its glow dims slightly.",
    "weight": 1,
    "category": "tool"
  }
]
```

### Notes

- Items with `room_id = NULL` and `is_visible = 0` are **not yet in the world**. They are spawned by command effects (`spawn_item`).
- Items with `room_id = NULL` and `is_visible = 1` are **in the player's inventory** at game start (rare — used for starting equipment).
- The `examine_description` is the most important field for gameplay. This is where clues live. Make it specific and evocative.

---

## Table: `npcs`

**Purpose**: Non-player characters that the player can interact with.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | TEXT PRIMARY KEY | Yes | Unique identifier: `old_wizard`, `gate_guard`. |
| `name` | TEXT | Yes | Display name: "Aldric the Wanderer", "Gate Guard". |
| `description` | TEXT | Yes | Short description shown when the NPC is present in a room. 1-2 sentences. |
| `examine_description` | TEXT | Yes | Detailed description when the player examines the NPC. 2-4 sentences. |
| `room_id` | TEXT REFERENCES rooms(id) | Yes | The room the NPC currently occupies. |
| `is_alive` | INTEGER | Yes | `1` = alive/active, `0` = dead/defeated/gone. Default `1`. |
| `is_blocking` | INTEGER | Yes | `1` = the NPC blocks one or more exits from their room until a condition is met. `0` = does not block. Default `0`. |
| `blocked_exit_id` | TEXT REFERENCES exits(id) | No | If `is_blocking = 1`, the exit this NPC blocks. |
| `unblock_flag` | TEXT | No | If `is_blocking = 1`, the flag that must be set to make the NPC stand aside. |
| `default_dialogue` | TEXT | Yes | What the NPC says if the player talks to them and no specific dialogue matches. |
| `hp` | INTEGER | No | Hit points for combat-enabled NPCs. `NULL` for non-combatant NPCs. |
| `damage` | INTEGER | No | Damage per attack for combat-enabled NPCs. `NULL` for non-combatants. |

### Example Row

```json
{
  "id": "gate_guard",
  "name": "Gate Guard",
  "description": "A burly guard in dented armor stands watch by the north door, halberd planted firmly.",
  "examine_description": "The guard is broad-shouldered and alert despite the late hour. His tabard bears the silver stag of the castle. He watches you with professional suspicion, but there's a weariness in his eyes. He keeps glancing at a signet ring on his finger — it seems too fine for a common guard.",
  "room_id": "castle_courtyard",
  "is_alive": 1,
  "is_blocking": 1,
  "blocked_exit_id": "courtyard_to_keep",
  "unblock_flag": "guard_convinced",
  "default_dialogue": "The guard shakes his head. 'No one enters the keep without the Captain's seal. Those are my orders.'",
  "hp": null,
  "damage": null
}
```

---

## Table: `dialogue`

**Purpose**: NPC dialogue lines that are triggered by topics or gated by game state flags.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | TEXT PRIMARY KEY | Yes | Unique identifier: `guard_about_captain`. |
| `npc_id` | TEXT REFERENCES npcs(id) | Yes | The NPC who says this. |
| `topic` | TEXT | No | The keyword the player asks about: `ask guard about captain`. If `NULL`, this is a `talk to` response (not topic-specific). |
| `content` | TEXT | Yes | The dialogue text shown to the player. |
| `required_flags` | TEXT | No | JSON array of flag conditions that must be true for this line to be available. If `NULL`, always available. Example: `["has_signet_ring"]`. |
| `set_flags` | TEXT | No | JSON array of flags to set when this dialogue is delivered. Example: `["learned_captain_name"]`. Used to gate subsequent content. |
| `priority` | INTEGER | Yes | When multiple dialogue entries match, the highest priority wins. Default `0`. |

### Example Rows

```json
[
  {
    "id": "guard_talk_default",
    "npc_id": "gate_guard",
    "topic": null,
    "content": "'State your business,' the guard says flatly. 'The keep is closed to visitors by order of Captain Maren.'",
    "required_flags": null,
    "set_flags": ["learned_captain_name"],
    "priority": 0
  },
  {
    "id": "guard_about_captain",
    "npc_id": "gate_guard",
    "topic": "captain",
    "content": "The guard's expression softens slightly. 'Captain Maren's not been the same since the incident in the east tower. She spends her nights up there now, poring over old documents. If you want her seal, you'll have to speak with her — but good luck getting up there. The stairs collapsed a fortnight ago.'",
    "required_flags": ["learned_captain_name"],
    "set_flags": ["knows_about_east_tower"],
    "priority": 0
  },
  {
    "id": "guard_shown_seal",
    "npc_id": "gate_guard",
    "topic": null,
    "content": "The guard examines the seal, then nods slowly. 'That's the Captain's mark, all right. Go on through — but mind yourself in there.'",
    "required_flags": ["has_captain_seal"],
    "set_flags": ["guard_convinced"],
    "priority": 10
  }
]
```

### Notes

- When the player types `talk to <npc>`, the engine finds all dialogue entries for that NPC where `topic` is `NULL` and `required_flags` are satisfied, then picks the one with the highest `priority`.
- When the player types `ask <npc> about <topic>`, the engine matches the `topic` field.
- The `set_flags` mechanism allows dialogue to unlock further dialogue, new information, and puzzle progression.

---

## Table: `locks`

**Purpose**: Defines the gates that block exits. Each lock specifies what type it is and what unlocks it.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | TEXT PRIMARY KEY | Yes | Unique identifier: `keep_door_lock`. |
| `lock_type` | TEXT | Yes | One of: `key`, `puzzle`, `combination`, `state`, `npc`. |
| `target_exit_id` | TEXT REFERENCES exits(id) | Yes | The exit this lock gates. |
| `key_item_id` | TEXT REFERENCES items(id) | No | For `key` type: the item that unlocks it. |
| `puzzle_id` | TEXT REFERENCES puzzles(id) | No | For `puzzle` type: the puzzle whose completion unlocks it. |
| `combination` | TEXT | No | For `combination` type: the correct code/phrase. |
| `required_flags` | TEXT | No | For `state` type: JSON array of flags that must all be true. Example: `["crystal_placed_1", "crystal_placed_2", "crystal_placed_3"]`. |
| `locked_message` | TEXT | Yes | Shown when the player tries to pass while locked. Should hint at the solution type without spoiling it. |
| `unlock_message` | TEXT | Yes | Shown when the lock is opened. |
| `is_locked` | INTEGER | Yes | Runtime state. Initialize to `1`. Engine sets to `0` when unlocked. |
| `consume_key` | INTEGER | Yes | For `key` type: `1` = key is destroyed on use, `0` = key is kept. Default `1`. |

### Example Rows

```json
[
  {
    "id": "watchtower_stair_lock",
    "lock_type": "key",
    "target_exit_id": "gatehouse_to_watchtower",
    "key_item_id": "iron_ring_key",
    "puzzle_id": null,
    "combination": null,
    "required_flags": null,
    "locked_message": "The stairway is blocked by an iron gate. It has a heavy lock — you'd need the right key.",
    "unlock_message": "The key turns with a grinding screech. The gate swings open, revealing the staircase beyond.",
    "is_locked": 1,
    "consume_key": 0
  },
  {
    "id": "fountain_passage_lock",
    "lock_type": "puzzle",
    "target_exit_id": "courtyard_to_undercroft",
    "key_item_id": null,
    "puzzle_id": "moonstone_fountain_puzzle",
    "combination": null,
    "required_flags": null,
    "locked_message": "The fountain basin is dry and solid. There seems to be no passage here — yet the inscription suggests otherwise.",
    "unlock_message": "Water surges up through cracks in the stone, filling the basin. The fountain figure tilts, and the base of the fountain slides aside, revealing steps descending into darkness.",
    "is_locked": 1,
    "consume_key": 0
  },
  {
    "id": "vault_combination_lock",
    "lock_type": "combination",
    "target_exit_id": "study_to_vault",
    "key_item_id": null,
    "puzzle_id": null,
    "combination": "7-3-9",
    "required_flags": null,
    "locked_message": "The vault door has a combination dial with three numbers. You'll need to find the correct sequence.",
    "unlock_message": "Click. Click. Click. The tumblers align and the vault door swings open with a hiss of stale air.",
    "is_locked": 1,
    "consume_key": 0
  }
]
```

### Notes

- Every exit with `is_locked = 1` MUST have a corresponding lock row.
- For `npc` type locks, the NPC's `is_blocking` and `unblock_flag` fields handle the gating directly. The lock row exists to provide the `locked_message` and `unlock_message` and to tie into the engine's unified lock-checking system.
- For `state` type locks, the engine checks all `required_flags` after every command. When all are true, it automatically unlocks the exit and shows the `unlock_message`.

---

## Table: `puzzles`

**Purpose**: Defines multi-step challenges. Puzzles are the primary progression mechanic.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | TEXT PRIMARY KEY | Yes | Unique identifier: `moonstone_fountain_puzzle`. |
| `name` | TEXT | Yes | Human-readable name: "The Moonstone Fountain". |
| `description` | TEXT | Yes | Internal description of the puzzle — what the player must do. Not shown to the player directly. Used by the generator for consistency checking. |
| `room_id` | TEXT REFERENCES rooms(id) | Yes | The primary room where this puzzle is encountered. |
| `is_solved` | INTEGER | Yes | Runtime state. Initialize to `0`. Engine sets to `1` when solved. |
| `solution_steps` | TEXT | Yes | JSON array describing the ordered steps to solve the puzzle. Each step is a human-readable string. Used for validation, not runtime logic (the commands table handles actual execution). |
| `hint_text` | TEXT | No | JSON array of progressive hints, from vague to specific. Shown one at a time when the player types `hint`. |
| `difficulty` | INTEGER | Yes | Relative difficulty: `1` = easy (single step, clue nearby), `2` = medium (2-3 steps, clues in adjacent rooms), `3` = hard (multi-step, clues across regions). |
| `score_value` | INTEGER | Yes | Points awarded on completion. |
| `is_optional` | INTEGER | Yes | `0` = required for critical path / win condition. `1` = optional side content. |

### Example Row

```json
{
  "id": "moonstone_fountain_puzzle",
  "name": "The Moonstone Fountain",
  "description": "The player must find the moonstone in the east tower and use it on the dry fountain in the courtyard. The inscription on the fountain ('WHEN THE MOON DRINKS, THE PATH OPENS') is the clue. Using the moonstone on the fountain fills it with water and reveals a hidden passage to the undercroft.",
  "room_id": "castle_courtyard",
  "is_solved": 0,
  "solution_steps": [
    "Find the moonstone in the east tower study",
    "Read the inscription on the courtyard fountain (examine fountain)",
    "Use the moonstone on the fountain"
  ],
  "hint_text": [
    "The fountain inscription mentions the moon. Is there something moon-related in the castle?",
    "You noticed a glowing stone in the east tower. Perhaps it's connected to the fountain?",
    "Try using the moonstone on the fountain in the courtyard."
  ],
  "difficulty": 2,
  "score_value": 20,
  "is_optional": 0
}
```

### Notes

- The `solution_steps` field is for **documentation and validation**, not runtime execution. The actual puzzle logic is implemented through `commands` rows that check preconditions and apply effects.
- Every puzzle should have at least one command that, when successfully executed, sets the puzzle's `is_solved` flag to `1`.
- The `hint_text` array is shown sequentially — the first hint on the first `hint` request, the second on the second, etc.

---

## Table: `commands`

**Purpose**: The heart of the engine. Every player action that changes game state is defined as a command rule with preconditions and effects. The engine pattern-matches player input against these rules and executes the first match.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | TEXT PRIMARY KEY | Yes | Unique identifier: `use_moonstone_on_fountain`. |
| `verb` | TEXT | Yes | The action verb: `use`, `take`, `drop`, `give`, `talk`, `attack`, `examine`, `enter`, `pull`, `push`, `open`, `read`, `combine`, etc. |
| `pattern` | TEXT | Yes | The full input pattern to match. Uses `{placeholder}` syntax for variable parts. Examples: `use {item} on {target}`, `pull {target}`, `enter {code}`, `give {item} to {npc}`. |
| `preconditions` | TEXT | Yes | JSON array of conditions that must ALL be true for this command to execute. See Precondition Types below. |
| `effects` | TEXT | Yes | JSON array of state changes to apply when the command executes. See Effect Types below. |
| `success_message` | TEXT | Yes | Text shown to the player when the command executes successfully. |
| `failure_message` | TEXT | Yes | Text shown when preconditions are not met. Should be informative — hint at what's missing. |
| `context_room_id` | TEXT REFERENCES rooms(id) | No | If set, this command only works in this specific room. If `NULL`, works anywhere. |
| `puzzle_id` | TEXT REFERENCES puzzles(id) | No | If set, this command is part of a puzzle. When it succeeds, it contributes to that puzzle's solution. |
| `priority` | INTEGER | Yes | When multiple commands match the same input, the highest priority wins. Default `0`. Use higher priority for specific overrides. |
| `is_enabled` | INTEGER | Yes | `1` = active, `0` = disabled. Commands can be enabled/disabled by effects. Default `1`. |

### Precondition Types

Preconditions are JSON objects in the `preconditions` array. Each has a `type` and relevant parameters.

| Type | Parameters | Description |
|---|---|---|
| `player_has_item` | `item_id` | Player has this item in inventory. |
| `player_in_room` | `room_id` | Player is in this specific room. |
| `item_in_room` | `item_id`, `room_id` | This item is in this room (not in inventory). |
| `flag_set` | `flag_id` | This flag is set (truthy). |
| `flag_not_set` | `flag_id` | This flag is NOT set. |
| `flag_equals` | `flag_id`, `value` | This flag equals a specific value. |
| `npc_alive` | `npc_id` | This NPC is alive. |
| `npc_in_room` | `npc_id`, `room_id` | This NPC is in this room. |
| `puzzle_solved` | `puzzle_id` | This puzzle has been solved. |
| `puzzle_not_solved` | `puzzle_id` | This puzzle has NOT been solved. |
| `exit_locked` | `exit_id` | This exit is currently locked. |
| `exit_unlocked` | `exit_id` | This exit is currently unlocked. |
| `player_hp_above` | `value` | Player HP is above this value (for combat). |

### Effect Types

Effects are JSON objects in the `effects` array. Each has a `type` and relevant parameters.

| Type | Parameters | Description |
|---|---|---|
| `add_item` | `item_id` | Add item to player inventory (set `room_id = NULL`). |
| `remove_item` | `item_id` | Remove item from player inventory entirely (consumed). |
| `move_item` | `item_id`, `room_id` | Move item to a specific room. |
| `spawn_item` | `item_id` | Make a hidden item visible (`is_visible = 1`) and place it in its designated room. |
| `set_flag` | `flag_id`, `value` | Set a flag to a value. If `value` is omitted, set to `"true"`. |
| `clear_flag` | `flag_id` | Remove / unset a flag. |
| `unlock_exit` | `exit_id` | Unlock an exit (`is_locked = 0`). |
| `lock_exit` | `exit_id` | Lock an exit (`is_locked = 1`). |
| `reveal_exit` | `exit_id` | Make a hidden exit visible (`is_hidden = 0`). |
| `move_player` | `room_id` | Teleport the player to a room. |
| `add_score` | `value`, `reason` | Add points to the player's score. `reason` is logged. |
| `print` | `text` | Display additional text to the player (beyond `success_message`). |
| `solve_puzzle` | `puzzle_id` | Mark a puzzle as solved. |
| `enable_command` | `command_id` | Enable a disabled command. |
| `disable_command` | `command_id` | Disable a command. |
| `damage_npc` | `npc_id`, `value` | Reduce an NPC's HP. If HP reaches 0, set `is_alive = 0`. |
| `damage_player` | `value` | Reduce player HP. |
| `heal_player` | `value` | Restore player HP. |
| `kill_npc` | `npc_id` | Set NPC's `is_alive` to `0`. |
| `set_npc_dialogue` | `npc_id`, `dialogue_id` | Change an NPC's active dialogue (for post-event conversation changes). |
| `end_game` | `result` | Trigger game end. `result` is `"win"` or `"lose"`. |

### Example Rows

**Simple item use:**

```json
{
  "id": "use_rusty_key_on_gate",
  "verb": "use",
  "pattern": "use rusty key on iron gate",
  "preconditions": [
    {"type": "player_has_item", "item_id": "rusty_key"},
    {"type": "player_in_room", "room_id": "castle_gatehouse"},
    {"type": "exit_locked", "exit_id": "gatehouse_to_watchtower"}
  ],
  "effects": [
    {"type": "remove_item", "item_id": "rusty_key"},
    {"type": "unlock_exit", "exit_id": "gatehouse_to_watchtower"},
    {"type": "add_score", "value": 5, "reason": "Unlocked the watchtower staircase"}
  ],
  "success_message": "You fit the rusty key into the lock. It resists for a moment, then turns with a grinding screech. The iron gate swings open, revealing the staircase beyond.",
  "failure_message": "You don't have anything that would open this gate.",
  "context_room_id": "castle_gatehouse",
  "puzzle_id": null,
  "priority": 0,
  "is_enabled": 1
}
```

**Multi-step puzzle (final step):**

```json
{
  "id": "use_moonstone_on_fountain",
  "verb": "use",
  "pattern": "use moonstone on fountain",
  "preconditions": [
    {"type": "player_has_item", "item_id": "moonstone"},
    {"type": "player_in_room", "room_id": "castle_courtyard"},
    {"type": "puzzle_not_solved", "puzzle_id": "moonstone_fountain_puzzle"}
  ],
  "effects": [
    {"type": "remove_item", "item_id": "moonstone"},
    {"type": "unlock_exit", "exit_id": "courtyard_to_undercroft"},
    {"type": "reveal_exit", "exit_id": "courtyard_to_undercroft"},
    {"type": "solve_puzzle", "puzzle_id": "moonstone_fountain_puzzle"},
    {"type": "set_flag", "flag_id": "fountain_activated"},
    {"type": "add_score", "value": 20, "reason": "Solved the Moonstone Fountain puzzle"}
  ],
  "success_message": "You place the moonstone into the fountain basin. It sinks into a perfectly shaped depression you hadn't noticed before. Water surges up through cracks in the stone, filling the basin with luminous, silver-white water. The fountain figure tilts on a hidden pivot, and the base grinds aside, revealing stone steps descending into darkness.",
  "failure_message": "You're not sure how to use that here.",
  "context_room_id": "castle_courtyard",
  "puzzle_id": "moonstone_fountain_puzzle",
  "priority": 0,
  "is_enabled": 1
}
```

**Combination lock:**

```json
{
  "id": "enter_vault_code",
  "verb": "enter",
  "pattern": "enter 7-3-9",
  "preconditions": [
    {"type": "player_in_room", "room_id": "study"},
    {"type": "exit_locked", "exit_id": "study_to_vault"}
  ],
  "effects": [
    {"type": "unlock_exit", "exit_id": "study_to_vault"},
    {"type": "add_score", "value": 15, "reason": "Cracked the vault combination"}
  ],
  "success_message": "Click. Click. Click. The tumblers align and the vault door swings open with a hiss of stale air.",
  "failure_message": "The dial spins freely but nothing happens. That's not the right combination.",
  "context_room_id": "study",
  "puzzle_id": null,
  "priority": 0,
  "is_enabled": 1
}
```

**Give item to NPC:**

```json
{
  "id": "give_seal_to_guard",
  "verb": "give",
  "pattern": "give captain seal to guard",
  "preconditions": [
    {"type": "player_has_item", "item_id": "captain_seal"},
    {"type": "npc_in_room", "npc_id": "gate_guard", "room_id": "castle_courtyard"},
    {"type": "npc_alive", "npc_id": "gate_guard"}
  ],
  "effects": [
    {"type": "remove_item", "item_id": "captain_seal"},
    {"type": "set_flag", "flag_id": "guard_convinced"},
    {"type": "unlock_exit", "exit_id": "courtyard_to_keep"},
    {"type": "add_score", "value": 10, "reason": "Gained entry to the keep"}
  ],
  "success_message": "The guard examines the seal, turning it over in his calloused hands. His eyes widen. 'That's the Captain's mark, all right. Go on through — but mind yourself in there.' He steps aside and pushes the heavy door open.",
  "failure_message": "The guard folds his arms. 'I'll need to see proper authorization before I let anyone through.'",
  "context_room_id": "castle_courtyard",
  "puzzle_id": null,
  "priority": 0,
  "is_enabled": 1
}
```

### Notes

- **Pattern matching**: the engine normalizes player input (lowercase, trim whitespace) and matches against `pattern`. The `{placeholder}` tokens match any word or phrase. Synonym handling (e.g., `get` = `take`) is handled by the engine, not the commands table.
- **Priority**: when multiple commands match, the highest priority wins. Use this for state-dependent overrides — e.g., a priority-10 command that handles "use moonstone on fountain" after the puzzle is already solved (to give a "you've already done that" message).
- **Failure messages**: the engine shows the `failure_message` of the command whose pattern matches but whose preconditions fail. If no pattern matches at all, the engine shows a generic "I don't understand that" message.

---

## Table: `flags`

**Purpose**: Boolean or string state variables that track world state changes. Flags are the glue between commands, dialogue, locks, and puzzles.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | TEXT PRIMARY KEY | Yes | Unique identifier: `guard_convinced`, `has_lantern_lit`. |
| `value` | TEXT | Yes | Current value. Initialize to `"false"` for booleans or to the appropriate default string. |
| `description` | TEXT | No | Internal documentation of what this flag represents. Not shown to the player. |

### Example Rows

```json
[
  {
    "id": "guard_convinced",
    "value": "false",
    "description": "Set to true when the player shows the captain's seal to the gate guard. Unblocks the keep entrance."
  },
  {
    "id": "fountain_activated",
    "value": "false",
    "description": "Set to true when the moonstone is used on the fountain. Opens the undercroft passage."
  },
  {
    "id": "learned_captain_name",
    "value": "false",
    "description": "Set to true when the player first talks to the guard and hears Captain Maren's name. Unlocks the 'ask about captain' dialogue topic."
  },
  {
    "id": "lantern_lit",
    "value": "false",
    "description": "Set to true when the player lights the lantern. Required to see in dark rooms."
  },
  {
    "id": "vault_code_digit_1",
    "value": "",
    "description": "First digit of the vault combination, learned from the ledger in the library. Used for combination puzzle tracking."
  }
]
```

### Notes

- Flags are the **universal state mechanism**. Every conditional in the game — dialogue gates, lock conditions, command preconditions, lore visibility — references flags.
- The generator should pre-populate all flags with their initial values. The engine never creates flags at runtime — it only reads and modifies existing ones.
- Use descriptive, specific flag IDs. `quest_1_done` is bad. `rescued_merchant_daughter` is good.
- Boolean flags use string values `"true"` and `"false"`. The engine treats `"true"` as truthy and everything else as falsy for `flag_set` / `flag_not_set` checks. The `flag_equals` check does exact string comparison.

---

## Table: `lore`

**Purpose**: Discoverable narrative content layered across three tiers. Lore enriches the world and rewards exploration.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | TEXT PRIMARY KEY | Yes | Unique identifier: `gatehouse_banner_lore`. |
| `tier` | TEXT | Yes | One of: `surface`, `engaged`, `deep`. |
| `title` | TEXT | Yes | Internal title for organization: "The Silver Stag Banner". |
| `content` | TEXT | Yes | The lore text itself. This is what the player reads. |
| `delivery_method` | TEXT | Yes | How the player encounters it: `room_description`, `examine`, `dialogue`, `inscription`, `book`, `puzzle_reward`, `item_description`. |
| `location_id` | TEXT REFERENCES rooms(id) | No | Room where this lore is found. `NULL` if delivered through dialogue or item examination anywhere. |
| `item_id` | TEXT REFERENCES items(id) | No | Item this lore is attached to. `NULL` if not item-based. |
| `npc_id` | TEXT REFERENCES npcs(id) | No | NPC who delivers this lore. `NULL` if not dialogue-based. |
| `required_flags` | TEXT | No | JSON array of flags that must be set for this lore to be accessible. `NULL` = always available. |
| `is_discovered` | INTEGER | Yes | Runtime state. Initialize to `0`. Engine sets to `1` when the player encounters it. |
| `score_value` | INTEGER | Yes | Points awarded on discovery. Surface = `0`, engaged = `2-5`, deep = `10-20`. |

### Example Rows

```json
[
  {
    "id": "stag_banner_surface",
    "tier": "surface",
    "title": "The Silver Stag Banner",
    "content": "The banner bearing the silver stag — the crest of the castle's ruling family — hangs above the gatehouse, faded but defiant.",
    "delivery_method": "room_description",
    "location_id": "castle_gatehouse",
    "item_id": null,
    "npc_id": null,
    "required_flags": null,
    "is_discovered": 0,
    "score_value": 0
  },
  {
    "id": "sword_inscription_engaged",
    "tier": "engaged",
    "title": "Captain Aldric's Sword",
    "content": "The inscription on the blade reads: 'Forged for Captain Aldric, who held the bridge at Thornwall against the Pale Host, and fell on the third day.' Aldric must have been the previous captain — before Maren.",
    "delivery_method": "examine",
    "location_id": null,
    "item_id": "old_sword",
    "npc_id": null,
    "required_flags": null,
    "is_discovered": 0,
    "score_value": 3
  },
  {
    "id": "true_history_deep",
    "tier": "deep",
    "title": "The Truth About Thornwall",
    "content": "The sealed chronicle reveals the truth: Aldric did not fall defending the bridge. He opened the gates to the Pale Host deliberately, hoping to end the siege and save the remaining civilians. The 'heroic last stand' was a story told afterward to preserve morale. Maren knows the truth — it's why she spends her nights in the tower, reading the old records. She's trying to decide whether to tell the people.",
    "delivery_method": "puzzle_reward",
    "location_id": "castle_sealed_chamber",
    "item_id": null,
    "npc_id": null,
    "required_flags": ["sealed_chamber_opened", "read_all_chronicles"],
    "is_discovered": 0,
    "score_value": 15
  }
]
```

---

## Table: `player`

**Purpose**: Single-row table tracking the player's runtime state. There is always exactly one row.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | INTEGER PRIMARY KEY | Yes | Always `1`. |
| `current_room_id` | TEXT REFERENCES rooms(id) | Yes | The room the player is currently in. Initialize to the `is_start = 1` room. |
| `hp` | INTEGER | Yes | Current hit points. Default `100`. For games without combat, this is still present but never modified. |
| `max_hp` | INTEGER | Yes | Maximum hit points. Default `100`. |
| `score` | INTEGER | Yes | Current score. Initialize to `0`. |
| `moves` | INTEGER | Yes | Number of commands entered. Initialize to `0`. Incremented by the engine on every valid command. |
| `game_state` | TEXT | Yes | One of: `playing`, `won`, `lost`. Initialize to `playing`. |

### Example Row

```json
{
  "id": 1,
  "current_room_id": "castle_gatehouse",
  "hp": 100,
  "max_hp": 100,
  "score": 0,
  "moves": 0,
  "game_state": "playing"
}
```

---

## Table: `score_entries`

**Purpose**: Log of individual scoring events, allowing the engine to display a score breakdown and prevent double-scoring.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | Yes | Auto-generated. |
| `reason` | TEXT | Yes | Description of why points were awarded: "Solved the Moonstone Fountain puzzle". |
| `value` | INTEGER | Yes | Points awarded. |
| `move_number` | INTEGER | Yes | The move count when this score was earned. |

### Notes

- This table starts **empty**. It is populated at runtime by `add_score` effects.
- The engine checks for duplicate `reason` strings to prevent awarding the same score twice.

---

## Table: `metadata`

**Purpose**: Game-level information. Single-row table.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | INTEGER PRIMARY KEY | Yes | Always `1`. |
| `title` | TEXT | Yes | The game's title: "The Silver Stag". |
| `author_prompt` | TEXT | Yes | The original user prompt that generated this game. |
| `seed` | TEXT | No | The seed used for generation, if any. |
| `version` | TEXT | Yes | Schema version: `"1.0"`. |
| `created_at` | TEXT | Yes | ISO 8601 timestamp of generation. |
| `max_score` | INTEGER | Yes | The maximum achievable score (sum of all score sources). |
| `win_conditions` | TEXT | Yes | JSON array of flag conditions that trigger the win. Example: `["curse_lifted", "escaped_castle"]`. |
| `lose_conditions` | TEXT | No | JSON array of flag/state conditions that trigger a loss. Example: `["player_hp_zero"]`. `NULL` if no lose conditions. |
| `intro_text` | TEXT | Yes | Opening text shown when the game starts, before the first room description. Sets the scene. |
| `win_text` | TEXT | Yes | Text shown when the player wins. |
| `lose_text` | TEXT | No | Text shown when the player loses. `NULL` if no lose conditions. |
| `region_count` | INTEGER | Yes | Number of distinct regions in the game. |
| `room_count` | INTEGER | Yes | Total number of rooms. |

### Example Row

```json
{
  "id": 1,
  "title": "The Silver Stag",
  "author_prompt": "A medieval castle mystery where a captain is hiding a dark secret",
  "seed": "42",
  "version": "1.0",
  "created_at": "2026-03-17T14:30:00Z",
  "max_score": 150,
  "win_conditions": ["truth_revealed", "escaped_castle"],
  "lose_conditions": null,
  "intro_text": "The road ends at a castle you've never seen on any map. The gates stand open — not welcoming, but uncaring. No banners fly from the battlements save one: a silver stag on a field of black, hanging limp in the still air. You came looking for answers about the disappearances in the valley below. The answers, it seems, are inside.",
  "win_text": "You step through the castle gates for the last time, the chronicle tucked under your arm. The truth about Thornwall — about Captain Aldric, about Captain Maren, about the Pale Host — is heavier than the leather-bound book that contains it. But the valley deserves to know. The silver stag banner flutters once as you pass beneath it, as if in farewell.",
  "lose_text": null,
  "region_count": 3,
  "room_count": 12
}
```

---

## Generation Checklist

When populating a `.zork` database, the LLM must verify:

### Structural Integrity
- [ ] Exactly one room has `is_start = 1`.
- [ ] Every `exits.from_room_id` and `exits.to_room_id` references an existing room.
- [ ] Every bidirectional connection has two exit rows (A-to-B and B-to-A).
- [ ] Every exit with `is_locked = 1` has a corresponding `locks` row.
- [ ] Every `locks.key_item_id` references an existing item.
- [ ] Every `locks.puzzle_id` references an existing puzzle.
- [ ] Every `locks.target_exit_id` references an existing exit.
- [ ] Every item's `room_id` (when not NULL) references an existing room.
- [ ] Every NPC's `room_id` references an existing room.
- [ ] Every NPC's `blocked_exit_id` (when not NULL) references an existing exit.
- [ ] Every dialogue's `npc_id` references an existing NPC.
- [ ] Every command's `context_room_id` (when not NULL) references an existing room.
- [ ] Every command's `puzzle_id` (when not NULL) references an existing puzzle.
- [ ] All flag IDs referenced in preconditions, effects, required_flags, and set_flags exist in the `flags` table.

### Gameplay Integrity
- [ ] All rooms are reachable from the start room (no orphan rooms).
- [ ] All locked exits have their keys/solutions reachable BEFORE the lock is encountered.
- [ ] No softlocks — the game is winnable regardless of the order the player explores.
- [ ] Every puzzle has at least one command that triggers its `solve_puzzle` effect.
- [ ] Every item referenced in a command's preconditions or effects exists in the `items` table.
- [ ] The win conditions reference flags that are set by achievable command effects.
- [ ] `metadata.max_score` equals the sum of all `add_score` effect values and `lore.score_value` entries.

### Content Quality
- [ ] Room descriptions mention visible exits naturally. Takeable items use `room_description` instead of being baked into the room's base description. Scenery items may appear in either.
- [ ] Examine descriptions contain clues for at least one puzzle.
- [ ] NPC dialogue provides information the player needs (directly or indirectly).
- [ ] Lore exists at all three tiers with at least 2 entries per tier.
- [ ] Hint text exists for puzzles rated difficulty 2 or higher.
- [ ] Failure messages are specific and informative, not generic.
- [ ] The intro text sets the scene and implies a goal.
- [ ] The win text provides narrative closure.
