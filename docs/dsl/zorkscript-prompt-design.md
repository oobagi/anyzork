# ZorkScript Prompt Design

> Design doc for the LLM authoring prompt that replaces the 356-line JSON import template. This document specifies the prompt structure, the ZorkScript surface grammar, game mechanic coverage requirements, and quality gates.

## 1. Problem Statement

The current `IMPORT_SPEC_AUTHORING_TEMPLATE` in `anyzork/importer.py` is 356 lines of dense JSON schema documentation sent to external LLMs (Claude, GPT, Gemini). It must explain:

- 18 effect types with exact parameter names
- 16 precondition types with exact parameter names
- 5 event types for triggers
- 6 interaction types with exact field shapes
- Exact nested object shapes for every entity type
- A long forbidden-aliases list ("do not use `text` for `content`", etc.)
- Minimum density targets
- Content quality rules
- Worked examples in verbose JSON

**Failure modes of the current approach:**

1. **Token bloat.** 356 lines of schema documentation consumes context the model needs for generation. Smaller models (Gemini Flash, GPT-4o-mini) feel this acutely.
2. **Field-name errors.** Despite explicit "do not rename" warnings, models routinely invent `location_room_id` for `room_id`, `text` for `content`, `response_text` for `success_message`. The normalization code in the importer (`_normalize_items`, `_normalize_dialogue`, `_normalize_locks`, etc.) is a growing patchwork of LLM-error workarounds.
3. **Structural errors.** Models misshape nested objects: flat preconditions without `type` keys, shorthand effects like `{ "set_flag": "x" }` instead of `{ "type": "set_flag", "flag": "x" }`.
4. **Interaction-command impedance mismatch.** The public `interactions` abstraction exists to shield authors from the raw command DSL, but it introduces its own field vocabulary (`set_flags`, `give_items`, `unlock_lock_ids`, `reveal_exit_ids`, `discover_quest_ids`, `solve_puzzle_ids`, `move_player_room_id`) that is equally error-prone.
5. **Density underperformance.** Models spend so many tokens parsing the schema that they produce thin worlds -- rooms with one-sentence descriptions, NPCs without dialogue, puzzles without multi-step chains.

**Design goal:** Replace the JSON template with a compact textual DSL (ZorkScript) that teaches the grammar through a single worked example, eliminates field-name ambiguity by using keywords instead of JSON keys, and reclaims context budget for richer content generation.

---

## 2. Design Principles

### 2.1 Grammar by Example, Not by Specification

The current template explains every field abstractly and then shows examples. ZorkScript inverts this: the grammar IS the example. A single complete worked example (a tiny but complete game) demonstrates every construct. The model learns the syntax by pattern-matching, not by reading a specification.

This works because LLMs are strong pattern completers. Showing one correct `.zorkscript` file and asking for another is a much more natural task than saying "here are 18 effect types with these exact parameter names."

### 2.2 Keywords Over Field Names

JSON field names are arbitrary strings. Nothing in `"type": "set_flag"` tells the model that `flag` is the required companion field. ZorkScript uses keyword syntax where the construct name implies the shape:

```
set flag door_opened
```

There is no `type` key to forget, no companion field to misname. The keyword IS the type, and the argument follows positionally.

### 2.3 Implicit Structure Over Explicit Nesting

JSON forces explicit object boundaries (`{`, `}`, commas). ZorkScript uses indentation and section headers. A room declaration is:

```
room dungeon_entrance "Dungeon Entrance"
  region: castle
  dark: false
  start: true
  ---
  Moonlight cuts across crumbled flagstones. A heavy iron door blocks the
  passage north, its surface pitted with rust. A silver key glints on a
  hook beside the doorframe.
  ---
  A compact entry hall with an iron door to the north.
  ---
  The air here carries the faint metallic tang of old iron and damp stone.
```

The three `---`-delimited blocks are `description`, `short_description`, and `first_visit_text` by position. No field names to misremember.

### 2.4 Compile, Don't Interpret

The ZorkScript output from the LLM is compiled by a new parser in the AnyZork codebase into the same internal structures the current JSON importer produces. The runtime engine never sees ZorkScript -- it still reads the SQLite `.zork` file. This means:

- No changes to the engine
- No changes to the command DSL evaluation
- The compiler can produce clear error messages when the LLM generates malformed syntax
- The compiler validates cross-references (items, rooms, NPCs, flags) at compile time

---

## 3. ZorkScript Grammar Overview

### 3.1 Top-Level Blocks

A ZorkScript file is a sequence of top-level declarations in any order. Each declaration starts with a keyword at column 0.

| Keyword | Declares |
|---------|----------|
| `game` | Game metadata, win/lose conditions |
| `room` | A room with exits, descriptions |
| `item` | An item (takeable, scenery, container, toggle, consumable) |
| `npc` | An NPC with placement and optional dialogue |
| `lock` | A lock on an exit |
| `puzzle` | A puzzle with solution steps |
| `flag` | A world-state flag |
| `quest` | A quest with objectives |
| `on` | A command rule (player action -> preconditions -> effects) |
| `when` | A trigger rule (reactive event -> preconditions -> effects) |

### 3.2 Game Block

```
game "The Sealed Tomb"
  author: "A dungeon delve beneath a forgotten mountain."
  realism: medium
  win: [sealed_king_defeated]
  lose: [player_dead]
  max_score: 200
  start: dungeon_entrance
  hp: 100
  ---
  You awaken on cold stone. The last thing you remember is the
  wizard's voice: "Find the three seals. Break them. End this."
  ---
  The Sealed King crumbles to dust. Light pours in from above.
  You are free.
```

The two `---` blocks are `intro_text` and `win_text` by position. An optional third block is `lose_text`.

### 3.3 Room Block

```
room dungeon_entrance "Dungeon Entrance"
  region: castle
  dark: false
  start: true
  exit north -> great_hall
  exit south -> courtyard (locked, hidden)
  ---
  Moonlight cuts across crumbled flagstones. A heavy iron door blocks the
  passage north, its surface pitted with rust. A silver key glints on a
  hook beside the doorframe. The air is still and cold.
  ---
  A stone entry hall with an iron door to the north.
  ---
  Something about this place feels expectant, as if the walls themselves
  have been waiting.
```

**Exits are inline.** Each `exit` line declares direction, target room, and optional parenthetical modifiers. This eliminates the separate `exits` array and its cross-referencing errors.

Exit modifiers:
- `locked` -- the exit starts locked (requires a corresponding `lock` declaration)
- `hidden` -- the exit is not visible until revealed
- `"description text"` -- optional prose shown when traversing

### 3.4 Item Block

```
item rusty_key "Rusty Key"
  in: dungeon_entrance
  takeable: true
  ---
  A heavy iron key, its teeth worn almost smooth. A faint
  inscription reads "D.H." in cramped lettering.
  ---
  An old key lies on the floor, half-hidden by debris.
```

The two `---` blocks are `examine_description` and `room_description` (the prose shown when the item is visible in a room).

**Item variants use modifier keywords:**

```
item oak_chest "Oak Chest"
  in: treasure_room
  container: true
  has_lid: true
  locked: true
  key: brass_key
  ---
  A sturdy oak chest bound in tarnished brass. The lock plate
  bears a scratched maker's mark you cannot read.
  ---
  A heavy oak chest sits against the far wall.

item torch "Wooden Torch"
  in: supply_room
  takeable: true
  toggle: [unlit, lit]
  toggle_default: unlit
  ---
  A rough pine torch wrapped in oil-soaked cloth.
  ---
  A torch leans in the corner, unlit.

item healing_herb "Healing Herb"
  in: garden
  takeable: true
  consumable: true
  quantity: 3
  quantity_unit: sprigs
  ---
  A fragrant green herb with broad, serrated leaves. It smells
  faintly of mint and something sharper beneath.
  ---
  Several sprigs of a green herb grow in a sheltered patch.
```

### 3.5 NPC Block

```
npc old_wizard "The Old Wizard"
  in: tower_study
  ---
  A gaunt figure in threadbare robes, his eyes sharp despite
  his age. His fingers are stained with ink and something darker.
  ---
  The wizard glances up from a massive tome, one eyebrow raised.

  dialogue root
    "You have the look of someone who doesn't know what they've
    walked into." He studies you for a long moment.
    sets: spoke_to_wizard
    option "Tell me about the Sealed King." -> node_king_lore
    option "What is this place?" -> node_tower_history
    option "I should go." -> end

  dialogue node_king_lore
    "A ruler entombed beneath the mountain. Three locks bind him.
    No single key opens them all." He presses a cold amulet into
    your hand.
    sets: knows_about_seals
    gives: enchanted_amulet
    requires_flag: spoke_to_wizard
    option "How do I find the locks?" -> node_lock_hints
    option "Thank you." -> end

  dialogue node_lock_hints
    "The first seal lies in the crypt beneath the great hall.
    The second, behind the falls. The third..." He trails off.
    "You'll know it when the ground shakes."
    option "I'll find them." -> end
```

**Dialogue is nested inside the NPC block.** Each `dialogue` sub-block declares a node. The first `dialogue root` is the entry point. Options use `->` to point to the next node or `-> end` to close the conversation.

Dialogue modifier lines:
- `sets: flag_id` -- sets a flag when this node is reached
- `gives: item_id` -- spawns an item into the player's inventory
- `requires_flag: flag_id` -- this node is only reachable when the flag is set
- `excludes_flag: flag_id` -- this node is hidden when the flag is set
- `requires_item: item_id` -- player must have this item for the option to appear

### 3.6 Lock Block

```
lock dungeon_door_lock
  exit: dungeon_entrance -> great_hall north
  type: key
  key: rusty_key
  consume_key: true
  ---
  The iron door is locked. Its hinges are rusted shut.
  ---
  The key turns with a grinding screech. The door shudders open.
```

The two `---` blocks are `locked_message` and `unlock_message`.

**Lock exit reference syntax:** `from_room -> to_room direction` uniquely identifies an exit without requiring the author to invent exit IDs. The compiler resolves this to the correct exit row.

Lock types and their required fields:
- `type: key` requires `key: item_id` and optional `consume_key: true/false`
- `type: flag` requires `flags: [flag_a, flag_b]` (all must be set)
- `type: puzzle` requires `puzzle: puzzle_id`

### 3.7 Puzzle Block

```
puzzle lever_and_statue "The Mechanism Puzzle"
  in: great_hall
  difficulty: medium
  score: 25
  optional: false
  steps: ["Pull the lever in the mechanism room", "Push the statue in the great hall"]
  hint: "Something beneath the statue seems to be holding it in place."
  ---
  A heavy stone statue stands on a raised platform. Its base
  seems designed to slide, but it won't move.
```

### 3.8 Flag Block

```
flag dungeon_door_opened "The dungeon door has been opened."
flag spoke_to_wizard "The player has spoken to the wizard."
flag lever_pulled "The mechanism lever has been pulled."
```

Flags are single-line declarations: `flag id "description"`. All flags start as `false`.

### 3.9 Quest Block

```
quest main:seal_the_mountain "Seal the Mountain Gate"
  completion: sealed_king_defeated
  discovery: spoke_to_wizard
  score: 0
  ---
  The wizard spoke of a Sealed King beneath the mountain,
  bound by three locks. Find and break all three seals.

  objective "Find the Crypt Seal" -> crypt_seal_broken (order: 0)
  objective "Find the Waterfall Seal" -> waterfall_seal_broken (order: 1)
  objective "Confront the Sealed King" -> sealed_king_defeated (order: 2)

quest side:hermits_bargain "The Hermit's Bargain"
  completion: hermit_helped
  discovery: found_hermits_journal
  score: 15
  ---
  A hermit trapped beyond the briar grove offers a shortcut
  in exchange for a silver mirror.

  objective "Find the silver mirror" -> has_silver_mirror (order: 0, optional: true, bonus: 5)
  objective "Bring the mirror to the hermit" -> hermit_helped (order: 1)
```

The `main:` or `side:` prefix on the quest ID declares `quest_type`. Objectives are inline. The arrow `->` points to the `completion_flag` for that objective.

### 3.10 Command Block (`on`)

Commands are the core interactivity. The `on` keyword declares what happens when the player types something.

```
on "use {item} on {target}" in dungeon_entrance [one_shot]
  require has_item rusty_key
  require not_flag dungeon_door_opened
  ---
  remove_item rusty_key
  unlock dungeon_door_lock
  reveal_exit dungeon_entrance -> great_hall north
  set_flag dungeon_door_opened
  score 10
  ---
  The rusty key turns with a grinding screech. The iron door
  shudders, then swings inward. A cold draft rushes out from
  the darkness beyond.
  ---
  You need the right key for this door.
```

**Structure of an `on` block:**

1. **Header line:** `on "pattern" in room_id [modifiers]`
   - Pattern uses `{slot}` placeholders
   - `in room_id` scopes to a room (optional; omit for anywhere)
   - `[one_shot]` marks the command as single-use
2. **Preconditions:** `require` lines, one per condition
3. **First `---` separator**
4. **Effects:** one effect per line, keyword + arguments
5. **Second `---` separator**
6. **Success message:** prose shown when the command fires
7. **Third `---` separator** (optional)
8. **Failure message:** prose shown when preconditions fail

**Precondition syntax:**

| Syntax | Maps to |
|--------|---------|
| `require has_item item_id` | `{ "type": "has_item", "item": "item_id" }` |
| `require has_flag flag_id` | `{ "type": "has_flag", "flag": "flag_id" }` |
| `require not_flag flag_id` | `{ "type": "not_flag", "flag": "flag_id" }` |
| `require in_room room_id` | `{ "type": "in_room", "room": "room_id" }` |
| `require item_in_room item_id room_id` | `{ "type": "item_in_room", "item": "...", "room": "..." }` |
| `require item_in_room item_id _current` | item in player's current room |
| `require npc_in_room npc_id _current` | `{ "type": "npc_in_room", "npc": "...", "room": "_current" }` |
| `require lock_unlocked lock_id` | `{ "type": "lock_unlocked", "lock": "..." }` |
| `require puzzle_solved puzzle_id` | `{ "type": "puzzle_solved", "puzzle": "..." }` |
| `require health_above N` | `{ "type": "health_above", "threshold": N }` |
| `require container_open item_id` | `{ "type": "container_open", "item": "..." }` |
| `require toggle_state item_id state` | `{ "type": "toggle_state", "item": "...", "state": "..." }` |

**Effect syntax:**

| Syntax | Maps to |
|--------|---------|
| `move_item item_id from to` | `{ "type": "move_item", ... }` |
| `remove_item item_id` | `{ "type": "remove_item", ... }` |
| `set_flag flag_id` | `{ "type": "set_flag", "flag": "...", "value": true }` |
| `unset_flag flag_id` | `{ "type": "set_flag", "flag": "...", "value": false }` |
| `unlock lock_id` | `{ "type": "unlock", ... }` |
| `move_player room_id` | `{ "type": "move_player", ... }` |
| `spawn_item item_id location` | `{ "type": "spawn_item", ... }` |
| `heal N` | `{ "type": "change_health", "amount": N }` |
| `damage N` | `{ "type": "change_health", "amount": -N }` |
| `score N` | `{ "type": "add_score", "points": N }` |
| `reveal_exit from -> to direction` | `{ "type": "reveal_exit", ... }` |
| `solve_puzzle puzzle_id` | `{ "type": "solve_puzzle", ... }` |
| `discover_quest quest_id` | `{ "type": "discover_quest", ... }` |
| `open_container item_id` | `{ "type": "open_container", ... }` |
| `set_toggle item_id state` | `{ "type": "set_toggle_state", ... }` |

### 3.11 Trigger Block (`when`)

Triggers fire reactively when engine events occur. They use the same precondition and effect syntax as commands.

```
when room_enter dungeon_entrance [one_shot]
  require not_flag first_dungeon_visit
  ---
  set_flag first_dungeon_visit
  score 5
  ---
  A deep rumble echoes through the stone walls. Something
  ancient knows you are here.
```

**Trigger event types:**

| Syntax | Event |
|--------|-------|
| `when room_enter room_id` | Player enters a room |
| `when flag_set flag_id` | A flag is set to true |
| `when item_taken item_id` | Player takes an item |
| `when item_dropped item_id` | Player drops an item |
| `when dialogue_node node_id` | A dialogue node is reached |

The structure after the header is identical to `on` blocks: `require` lines, `---`, effect lines, `---`, message text.

---

## 4. Game Mechanic Coverage Analysis

### 4.1 First-Class Constructs (Must Be Easy to Express)

These are the mechanics that appear in every well-authored text adventure. ZorkScript must make each of these trivial to declare.

**Rooms and spatial navigation.** Rooms are the atomic unit. Exits must be declarable inline (no separate array, no cross-referencing IDs). Hidden and locked exits must be one-word modifiers. Regions must be a single property line, not a separate entity.

**Items with behavioral variants.** The current schema supports: takeable objects, scenery, containers (with lids, locks, nested contents), toggleable items (torch lit/unlit), consumables with quantities, and keys. ZorkScript must support all of these through modifier keywords on the `item` block rather than requiring the author to know which of 30+ boolean fields to set.

**NPCs with embedded dialogue.** The current system separates `npcs`, `dialogue_nodes`, and `dialogue_options` into three arrays with cross-referencing IDs. This is the single highest source of authoring errors. ZorkScript nests dialogue inside the NPC block and uses indentation to show the tree structure. The compiler generates IDs automatically.

**Locks with human-readable exit references.** The current system requires the author to know the exit ID (e.g., `dungeon_entrance_to_great_hall`). ZorkScript uses the `from_room -> to_room direction` triple, which is what the author already knows. The compiler resolves it.

**Puzzles with solution steps and hints.** Currently just a data record. ZorkScript keeps this as a simple block but ensures `steps` and `hint` are first-class properties, not JSON-encoded strings.

**Commands as the core gameplay verb.** The `on` block is the heart of ZorkScript. Every player interaction beyond built-in verbs (look, take, drop, go) is an `on` block. The syntax must be compact enough that a 6-effect command fits in 12 lines, not 30 lines of JSON.

**Triggers as reactive rules.** The `when` block mirrors `on` but fires on engine events instead of player input. Same precondition/effect vocabulary, same syntax, different trigger.

**Quests with inline objectives.** The current system requires quest objectives as a separate nested array with their own IDs. ZorkScript embeds objectives as `objective` lines inside the `quest` block.

**Flags as the connective tissue.** Flags are single-line declarations. They connect commands, triggers, dialogue, locks, and quests. ZorkScript must make flag references consistent and grep-able across the entire file.

### 4.2 Pain Points in the Current System (Must Be Easier)

**Multi-outcome interactions require duplicate commands.** In JSON, if a player can "talk to wizard" and get 3 different responses based on state, that is 3 separate command objects with 3 sets of preconditions. In ZorkScript, these are still separate `on` blocks, but each is 8-12 lines instead of 20-30 lines of JSON. The compactness makes authoring 3 variants feel natural rather than tedious.

**The "examine" override pattern.** Overriding what happens when a player examines an item (e.g., examining a bookshelf reveals a secret passage) requires a command that intercepts `look at {target}` with `in_room` and `item_in_room` preconditions. In JSON this is a 25-line object. In ZorkScript:

```
on "look at {target}" in library [one_shot]
  require item_in_room old_bookshelf _current
  require not_flag bookshelf_moved
  ---
  set_flag bookshelf_moved
  reveal_exit library -> secret_study east
  score 20
  ---
  You run your fingers along the bookshelf's edge. One volume
  doesn't budge. The entire shelf swings outward, revealing a
  narrow passage cut into the stone behind it.
```

That is 12 lines. The JSON equivalent is 25. The improvement is arithmetic, not magical, but it compounds across dozens of interactions.

**Trigger cascades are hard to author.** A common pattern: trigger A sets a flag when the player enters a room, trigger B fires when that flag is set and does something else. In JSON, the author must track `event_type`, `event_data` shapes, precondition objects, and effect objects across two separate trigger declarations. In ZorkScript, the two `when` blocks use identical syntax with readable keywords:

```
when room_enter crypt [one_shot]
  ---
  set_flag crypt_seal_visible
  ---
  The wall shimmers. An ancient seal materializes in the stone.

when flag_set crypt_seal_visible [one_shot]
  ---
  spawn_item crypt_seal crypt
  ---
  A glowing sigil burns itself into the wall. You can feel its heat.
```

**Cross-referencing is error-prone.** In JSON, the author must manually ensure that every `room_id`, `item_id`, `npc_id`, `lock_id`, `puzzle_id`, `quest_id`, and `flag` reference points to a real entity. In ZorkScript, the compiler validates all cross-references at compile time and produces clear error messages like "Command references item 'silver_key' but no item with that ID exists."

**Dialogue node ID management.** In JSON, every dialogue node and option needs a unique ID, and options must reference node IDs by string. ZorkScript auto-generates IDs from the NPC ID and node label (`npc_id + "_" + node_label`). The author writes `dialogue root` and `-> node_king_lore`; the compiler handles the rest.

### 4.3 Missing Affordances (Currently Hard or Impossible)

**Conditional NPC behavior based on state.** The current system supports this through flag-gated dialogue options and separate commands for each NPC interaction variant. ZorkScript does not add new mechanics here but makes the pattern cheaper to author. A dialogue node with `requires_flag` and `excludes_flag` lines naturally expresses "say this before quest X, say that after."

**Multi-step crafting.** The engine supports this through `combine` commands that remove inputs and spawn outputs. ZorkScript does not add a first-class `recipe` construct because the `on "combine {item} with {item2}"` pattern is already compact. However, if crafting becomes common, a future `recipe` shorthand could compile to the same command structure.

**Timed events (do X within N moves).** The current engine does not track move counts per-trigger. This is a runtime engine feature, not a prompt/DSL feature. ZorkScript cannot express what the engine cannot evaluate. If move-based timing is added to the engine later, a `within N moves` modifier on `when` blocks would be the natural syntax.

**NPC movement between rooms.** The current schema stores NPCs in a single room. NPC relocation requires a `move_item`-style effect for NPCs, which does not exist. This is an engine limitation, not a prompt limitation.

**Ambient descriptions that change with state.** The engine always shows the same room description (full on first visit, short on revisit). State-dependent room prose would require a new engine feature (description variants keyed on flags). ZorkScript could express this as:

```
room courtyard "Courtyard"
  description when has_flag garden_bloomed:
    The courtyard bursts with color. Flowers climb every wall.
  description default:
    The courtyard is barren. Dead vines cling to grey stone.
```

But this requires engine support that does not exist. Flagged for future consideration.

---

## 5. The Prompt Template

### 5.1 Design Constraints

- **Target: 80-100 lines** (the prompt itself, excluding the concept brief injected at runtime)
- **Cross-provider compatibility:** Must produce correct output from Claude, GPT-4o, Gemini Pro, and their smaller variants
- **Single worked example:** The grammar section is one complete mini-game, not abstract BNF
- **Quality requirements as bullets:** Concise, scannable, enforceable
- **Concept brief injected at runtime:** The prompt template has a `{concept}` placeholder

### 5.2 Prompt Structure

```
[1] Role instruction (3-4 lines)
[2] ZorkScript grammar reference via worked example (45-55 lines)
[3] Quality requirements (10-12 lines)
[4] Constraints (5-8 lines)
[5] Concept brief (injected at runtime, variable length)
```

### 5.3 Draft Prompt

```
You are authoring a complete, playable text adventure in ZorkScript format.
Output ONLY valid ZorkScript. No markdown, no commentary, no prose outside
the ZorkScript blocks. Follow the grammar shown in the example below exactly.

--- EXAMPLE: A complete mini-game in ZorkScript ---

game "The Silver Key"
  author: "A short dungeon escape built around a locked door and a hidden lever."
  realism: medium
  win: [escaped_dungeon]
  max_score: 55
  start: cell
  hp: 100
  ---
  You wake on cold stone. Iron bars. Darkness. Somewhere above,
  a key turns in a lock that is not yours.
  ---
  Daylight. You stumble into the courtyard, free. The dungeon
  is behind you. The sky has never looked so wide.

room cell "Prison Cell"
  region: dungeon
  start: true
  exit north -> corridor
  ---
  A narrow stone cell. The iron door hangs open -- whoever left
  forgot to lock it. A straw pallet lies in the corner. Scratches
  on the wall mark hundreds of days.
  ---
  Your former cell. The door hangs open.
  ---
  The silence here is heavier than the stone walls.

room corridor "Dungeon Corridor"
  region: dungeon
  exit south -> cell
  exit north -> gate_room
  exit east -> supply_closet
  ---
  A long corridor lit by guttering torches. The air smells of
  damp stone and old smoke. Doors line the east wall. To the north,
  a heavy portcullis blocks the passage.
  ---
  A torch-lit corridor running north-south.

room supply_closet "Supply Closet"
  region: dungeon
  exit west -> corridor
  ---
  A cramped closet stuffed with crates and mouldering rope. A rusty
  lever protrudes from the wall, connected to chains that vanish into
  the ceiling.
  ---
  A cluttered supply closet with a lever on the wall.

room gate_room "Portcullis Chamber"
  region: dungeon
  exit south -> corridor
  exit north -> courtyard (locked)
  ---
  The corridor ends at a massive iron portcullis. Beyond it, you
  can see a stone staircase climbing toward daylight. A guard slouches
  on a stool beside the gate, half-asleep.
  ---
  The portcullis chamber. A guard watches the gate.

room courtyard "Sunlit Courtyard"
  region: exterior
  exit south -> gate_room
  ---
  Warm sunlight floods a flagstone courtyard. An overgrown garden
  borders the eastern wall. The main road leads west to freedom.
  ---
  A bright courtyard outside the dungeon.
  ---
  The light stings your eyes after so long underground.

item straw_pallet "Straw Pallet"
  in: cell
  ---
  A thin, filthy pallet. Something hard is hidden inside the straw.
  ---
  A straw pallet lies crumpled in the corner.

item silver_key "Silver Key"
  in: cell
  takeable: true
  ---
  A small silver key, cool to the touch. Its head is stamped with
  a portcullis sigil.
  ---
  A glint of silver peeks out from the straw.

item rusty_lever "Rusty Lever"
  in: supply_closet
  ---
  A heavy iron lever mounted to the wall. Chains run from it up
  through a slot in the ceiling. It looks connected to something
  mechanical above.
  ---
  A rusty lever juts from the wall.

item guard_stool "Guard's Stool"
  in: gate_room
  ---
  A worn wooden stool. Initials are carved into the seat: "J.R."
  ---
  A rickety stool sits beside the gate.

item healing_moss "Healing Moss"
  in: supply_closet
  takeable: true
  consumable: true
  quantity: 2
  quantity_unit: clumps
  ---
  Soft green moss with a sharp, clean smell. It clings to a
  damp stone in the corner.
  ---
  Green moss grows on the damp stones.

npc guard "The Guard"
  in: gate_room
  blocking: gate_room -> courtyard north
  unblock_flag: guard_bribed
  ---
  A heavyset man in dented armor. His eyes are bloodshot and his
  breath smells of cheap ale. He grips a short sword loosely.
  ---
  The guard eyes you with lazy suspicion.

  dialogue root
    "Another rat from the cells." He barely looks up. "Gate's
    locked. Go back to your hole."
    option "I have something for you." -> node_bribe
      requires_item: silver_key
    option "I'll find another way." -> end

  dialogue node_bribe
    His eyes fix on the silver key. "Where'd you get that?"
    He snatches it from your hand and pockets it. "Fine.
    Go. I never saw you."
    sets: guard_bribed

flag dungeon_door_opened "The portcullis has been raised."
flag lever_pulled "The lever in the supply closet has been pulled."
flag guard_bribed "The guard accepted a bribe."
flag escaped_dungeon "The player escaped the dungeon."

lock portcullis_lock
  exit: gate_room -> courtyard north
  type: flag
  flags: [dungeon_door_opened]
  ---
  The portcullis is lowered. Its iron bars are too heavy to lift by hand.
  ---
  With a grinding shriek, the portcullis rises into the ceiling.

puzzle lever_puzzle "Raise the Portcullis"
  in: gate_room
  difficulty: easy
  score: 15
  steps: ["Pull the lever in the supply closet"]
  hint: "There must be a mechanism somewhere that controls the gate."
  ---
  The portcullis blocks the northern passage. It seems mechanical.

quest main:escape_dungeon "Escape the Dungeon"
  completion: escaped_dungeon
  score: 0
  ---
  Find a way past the locked portcullis and the guard to reach
  the courtyard.

  objective "Raise the portcullis" -> dungeon_door_opened (order: 0)
  objective "Get past the guard" -> guard_bribed (order: 1)
  objective "Reach the courtyard" -> escaped_dungeon (order: 2)

on "pull {target}" in supply_closet [one_shot]
  require item_in_room rusty_lever _current
  require not_flag lever_pulled
  ---
  set_flag lever_pulled
  set_flag dungeon_door_opened
  unlock portcullis_lock
  solve_puzzle lever_puzzle
  score 15
  ---
  You heave the lever down. Chains rattle through the ceiling.
  Somewhere beyond the corridor, metal grinds against stone.
  The portcullis is rising.
  ---
  The lever won't budge further. It's already pulled.

on "pull {target}" in supply_closet
  require item_in_room rusty_lever _current
  require has_flag lever_pulled
  ---
  ---
  The lever is already in the down position. The chains are taut.

on "give {item} to {npc}" in gate_room [one_shot]
  require has_item silver_key
  require npc_in_room guard _current
  require not_flag guard_bribed
  ---
  remove_item silver_key
  set_flag guard_bribed
  score 15
  ---
  You hold out the silver key. The guard's eyes widen. He snatches
  it and tucks it into his belt. "Get out of here. Quick."
  ---
  The guard doesn't want what you're offering.

on "use {item}" [one_shot]
  require has_item healing_moss
  ---
  remove_item healing_moss
  heal 20
  score 5
  ---
  You press the moss against your skin. A cool tingling spreads
  through you as the ache recedes.

on "examine {target}" in cell [one_shot]
  require item_in_room straw_pallet _current
  require not_flag found_silver_key
  ---
  set_flag found_silver_key
  move_item silver_key straw_pallet cell
  score 5
  ---
  You pull apart the straw. Something falls out -- a small
  silver key, stamped with a portcullis sigil.

when room_enter courtyard [one_shot]
  require has_flag guard_bribed
  require has_flag dungeon_door_opened
  ---
  set_flag escaped_dungeon
  score 15
  ---
  You climb the stairs into blinding sunlight. Free.

--- END EXAMPLE ---

Quality requirements:
- At least 8 rooms across 2+ regions. Prefer 12-20 for medium concepts.
- At least 10 items. Every major room has 2+ examinable objects.
- At least 3 NPCs with dialogue trees for story-driven concepts.
- At least 2 puzzles with multi-step solutions.
- At least 1 main quest with 3+ objectives.
- Every room description: 2-4 vivid, concrete sentences. Sensory detail.
  Embed clues and interactable objects naturally in prose.
- Short descriptions: 1 compact orienting sentence.
- First-visit text: a fresh detail or reaction, never a repeat of the description.
- Every item mentioned in room prose must exist as a real item declaration.
- Every NPC mentioned in room prose must exist as a real NPC declaration.
- The starting room must offer an obvious first action within 1-2 commands.
- The win condition must be reachable through the authored commands and triggers.
- No dead ends or softlocks. Every lock has a reachable key or solution.

Constraints:
- Use ONLY the keywords shown in the example. Do not invent new block types.
- Exit directions must be: north, south, east, west, up, down.
- Do not explain the game outside the ZorkScript. No commentary or markdown.
- Every flag referenced in require/set/when must have a flag declaration.
- Every ID must be snake_case and unique within its entity type.
- Preserve the concept's scope. Do not reduce it to a skeleton.
- Do not expand beyond what the concept requests.

Concept:
{concept}
```

### 5.4 Line Count Analysis

| Section | Lines |
|---------|-------|
| Role instruction | 3 |
| Example header | 1 |
| Worked example (game + rooms + items + NPCs + locks + puzzles + quests + commands + triggers) | ~67 |
| Example footer | 1 |
| Quality requirements | 14 |
| Constraints | 7 |
| Concept injection | 2 |
| **Total (excluding concept)** | **~95** |

This meets the 80-100 line target. The worked example is the largest section but it doubles as the complete grammar reference -- no separate BNF or field-name tables are needed.

---

## 6. Quality Gates and Density Requirements

### 6.1 Minimum Density Targets

These are preserved from the current template and compiled into scannable bullets in the prompt.

| Entity | Minimum | Notes |
|--------|---------|-------|
| Rooms | 8 | Across 2+ regions. Prefer 12-20 for medium concepts. |
| Items | 10 | Every major room should have 2+ examinable objects. |
| NPCs | 3-4 | For story-driven concepts with named characters. |
| Dialogue nodes | 3+ | Per NPC with a speaking role. |
| Puzzles | 2 | With multi-step solutions. |
| Quests | 1 main | With 3+ objectives. Side quests encouraged. |
| Commands (`on` blocks) | 1 per puzzle + 1 per key interaction | Every puzzle must have at least the solution command. |
| Triggers (`when` blocks) | 1+ | Room-entry triggers for atmosphere; flag triggers for cascades. |
| Flags | 1 per gate + 1 per quest objective | Enough to track all progression. |

### 6.2 Content Quality Standards

| Standard | How ZorkScript Enforces It |
|----------|---------------------------|
| Room descriptions are rich | The `---` block format makes thin descriptions visually obvious. The example demonstrates 2-4 sentence descriptions. |
| Items mentioned in prose exist | The compiler cross-references item IDs against room prose (future enhancement). At minimum, the prompt explicitly states this rule. |
| First loop is playable | The prompt requires "the starting room must offer an obvious first action within 1-2 commands." The example demonstrates this (examine pallet -> find key). |
| No softlocks | The prompt states this. The compiler validates that every lock has a reachable key/solution (existing validation logic). |
| Win condition is reachable | The prompt states this. The compiler traces the flag dependency graph from win condition flags back through commands and triggers. |

### 6.3 Compiler-Enforced Validation

The ZorkScript compiler should perform these checks at compile time (not in the prompt, but as a safety net):

1. **Referential integrity:** Every room, item, NPC, lock, puzzle, quest, and flag referenced in any block must be declared somewhere in the file.
2. **Exit consistency:** Every exit target room must exist. Locked exits must have a corresponding lock declaration.
3. **Win condition reachability:** At least one command or trigger must set each win-condition flag.
4. **Orphan detection:** Items in rooms that don't exist. NPCs in rooms that don't exist.
5. **Duplicate ID detection:** No two entities of the same type share an ID.
6. **Start room existence:** The declared start room must be a real room.
7. **Dialogue tree connectivity:** Every `-> node_label` in a dialogue option must point to a declared dialogue node within the same NPC.

---

## 7. Comparison: JSON Template vs. ZorkScript Prompt

### 7.1 Token Comparison (Estimated)

| Component | JSON Template (tokens) | ZorkScript Prompt (tokens) |
|-----------|----------------------|---------------------------|
| Schema documentation | ~2,800 | 0 (taught by example) |
| Enum/value constraints | ~400 | ~80 (in constraints section) |
| Forbidden aliases | ~350 | 0 (keywords eliminate ambiguity) |
| Worked examples | ~800 | ~600 (the example IS the grammar) |
| Quality requirements | ~500 | ~200 (concise bullets) |
| Self-check instructions | ~200 | 0 (compiler does this) |
| **Total** | **~5,050** | **~880** |

Estimated reduction: **~83%** of prompt tokens freed for content generation.

### 7.2 Error Surface Comparison

| Error Type | JSON Frequency | ZorkScript Expected |
|------------|---------------|-------------------|
| Wrong field name (`text` vs `content`) | High | Eliminated (keywords) |
| Missing `type` key in precondition/effect | High | Eliminated (keyword IS type) |
| Wrong nesting structure | Medium | Eliminated (indentation + `---`) |
| Invalid enum value (exit direction, event type) | Medium | Same (must still match keywords) |
| Missing cross-reference | Medium | Same in prompt, caught by compiler |
| Thin content / low density | High | Reduced (more context budget for generation) |
| Shorthand/alias inventions | High | Eliminated (no JSON keys to alias) |

### 7.3 Authoring Effort: Locked Door Puzzle

**JSON (30 lines):**
```json
{
  "id": "use_rusty_key_on_dungeon_door",
  "type": "read_item",
  "command": "use rusty_key on dungeon_door",
  "item_id": "rusty_key",
  "context_room_ids": ["dungeon_entrance"],
  "required_flags": [],
  "excluded_flags": ["dungeon_door_opened"],
  "required_items": ["rusty_key"],
  "set_flags": ["dungeon_door_opened"],
  "give_items": [],
  "unlock_lock_ids": ["dungeon_door_lock"],
  "reveal_exit_ids": ["dungeon_entrance_to_great_hall"],
  "discover_quest_ids": [],
  "solve_puzzle_ids": [],
  "move_player_room_id": null,
  "success_message": "The rusty key turns with a grinding screech.",
  "failure_message": "You need the right key for this door.",
  "priority": 0,
  "one_shot": true
}
```

**ZorkScript (12 lines):**
```
on "use {item} on {target}" in dungeon_entrance [one_shot]
  require has_item rusty_key
  require not_flag dungeon_door_opened
  ---
  remove_item rusty_key
  unlock dungeon_door_lock
  reveal_exit dungeon_entrance -> great_hall north
  set_flag dungeon_door_opened
  score 10
  ---
  The rusty key turns with a grinding screech. The iron door
  shudders, then swings inward. Cold air rushes out.
  ---
  You need the right key for this door.
```

60% reduction in lines. But the real win is that the ZorkScript version has zero fields that can be misnamed.

---

## 8. Compiler Implementation Notes

### 8.1 Parser Strategy

The ZorkScript parser should be a hand-written recursive descent parser, not a grammar generator. The language is simple enough that a ~300 line Python parser suffices. Key parsing rules:

1. **Top-level dispatch:** Read the first word of each non-blank, non-indented line. Dispatch to the appropriate block parser.
2. **Block boundaries:** A block ends when a new top-level keyword appears at column 0, or at end-of-file.
3. **`---` separators:** Within a block, `---` on its own line separates positional text sections.
4. **Indented lines:** Lines starting with whitespace belong to the current block. Lines starting with specific keywords (`exit`, `dialogue`, `objective`, `require`, `option`) are sub-declarations.
5. **Quoted strings:** Double-quoted strings on header lines capture display names and patterns.
6. **Bracketed lists:** `[flag_a, flag_b]` is parsed as a list of identifiers.
7. **Parenthetical modifiers:** `(locked, hidden)` on exit lines are parsed as modifier sets.

### 8.2 Compilation Targets

The parser produces the same Python dictionary structure that `parse_import_spec_text` returns today. This means:

- `compile_import_spec` works unchanged
- All existing validation in `_validate_imported_game` applies
- The `.zork` file output is identical regardless of whether the source was JSON or ZorkScript

### 8.3 Error Recovery

The parser should be lenient on whitespace and trailing commas but strict on keywords. When an unknown keyword appears, the error message should include "did you mean X?" suggestions based on edit distance from valid keywords.

### 8.4 ID Generation

For entities where the author does not need to control the ID:

- **Exit IDs:** auto-generated as `{from_room}_{direction}` (e.g., `cell_north`)
- **Dialogue node IDs:** auto-generated as `{npc_id}_{node_label}` (e.g., `guard_root`, `guard_node_bribe`)
- **Dialogue option IDs:** auto-generated as `{node_id}_opt_{index}`
- **Quest objective IDs:** auto-generated as `{quest_id}_obj_{index}`

This eliminates an entire class of ID-management errors.

---

## 9. Migration Path

### 9.1 Phase 1: Parser + Prompt (This Work)

- Write the ZorkScript parser (`anyzork/zorkscript/parser.py`)
- Write the new prompt template (replacing `IMPORT_SPEC_AUTHORING_TEMPLATE`)
- Add `build_zorkscript_prompt` alongside the existing `build_import_prompt`
- Compile ZorkScript to the same internal dict that JSON compilation uses
- Existing `compile_import_spec` works on either input

### 9.2 Phase 2: CLI Integration

- `anyzork import` auto-detects JSON vs. ZorkScript input
- `anyzork author --format zorkscript` sends the new prompt to external models
- `anyzork author --format json` (deprecated, still works)

### 9.3 Phase 3: Deprecate JSON Template

- JSON import remains supported (existing authored specs still compile)
- New authoring defaults to ZorkScript
- JSON template moved to a compatibility module

---

## 10. Open Questions

1. **Should the example in the prompt be a fixed, hand-authored mini-game, or should it be dynamically selected to match the concept's genre?** A dungeon example may confuse a model asked to generate a mystery set in a Victorian manor. However, genre-matched examples would require maintaining multiple example games, increasing maintenance burden. Recommendation: start with one fixed example and measure error rates before investing in genre-matched examples.

2. **Should the compiler round-trip?** That is, should it be possible to decompile a `.zork` file back to ZorkScript? This would enable editing existing games in the textual format. Not required for the prompt use case but valuable for a ZorkScript-first authoring workflow.

3. **Should `on` blocks support a shorthand for the common "examine item reveals information" pattern?** This is the most frequently authored command type. A dedicated `examine_override` block would reduce boilerplate. Counter-argument: adding special syntax for one pattern adds cognitive load for a small saving. The generic `on "examine {target}"` pattern is already compact.

4. **Should the prompt include negative examples?** ("Do NOT write it like this.") The current JSON template has extensive negative examples. The ZorkScript prompt relies on the worked example being unambiguous enough that negative examples are unnecessary. This assumption should be tested.

5. **How does realism injection work?** The current system injects realism guidance as a text block. The ZorkScript prompt should inject it the same way -- as additional natural-language guidance before the concept brief. The `realism` field in the `game` block is the output; the guidance is the input.
