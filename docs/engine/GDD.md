# AnyZork Game Design Document

> This GDD describes the **engine's design space** — the mechanics, systems, and structures that AnyZork supports so that an LLM can generate complete, playable text adventure games within these constraints.

## Motivation

Using an LLM to run a text adventure in real time fails in the same ways over and over: context loss (the model forgets rooms, items, flags), state inconsistency (it lets the player do impossible things), and world drift (descriptions and puzzle logic change mid-session). The core issue is role overload — a single model trying to be the world database, the game engine, and the narrator at once.

AnyZork splits the system into three steps:

1. `anyzork generate` builds a ZorkScript authoring prompt for an external LLM.
2. `anyzork import` compiles the returned ZorkScript into a portable `.zork` archive.
3. `anyzork play` runs the deterministic engine against that file.

The LLM is used once for creativity. The engine handles all runtime state.

Commands are stored as structured precondition/effect rules instead of generated code. This keeps runtime deterministic, auditable, and safe — the model can compose valid mechanics, but it cannot invent arbitrary executable behavior.

---

## Design Pillars

1. **Deterministic integrity** — every game state transition is rule-driven and reproducible. The player can trust that the world behaves consistently.
2. **Discoverable depth** — the world rewards curiosity. Surface gameplay is accessible; engaged play reveals hidden layers; deep exploration uncovers secrets that recontextualize the world.
3. **Fair challenge** — every puzzle is solvable with information available in the game world. No pixel hunts, no read-the-designer's-mind solutions. Clues exist; the player must find and connect them.
4. **Emergent narrative** — the player's sequence of actions creates a story. The game provides the pieces; the player assembles the experience.
5. **Portable completeness** — a `.zork` file is a self-contained world. No external dependencies, no network calls, no missing assets.

---

## Core Gameplay Loop

### Moment-to-Moment (0-30 seconds)

- **Action**: Player types a command (move, examine, take, use, talk).
- **Feedback**: The engine evaluates preconditions and returns immediate textual feedback — either the effect of the action or a meaningful failure message explaining why it didn't work.
- **Reward**: New information (room descriptions, item details, NPC dialogue), inventory changes, score increments, or world state changes (doors opening, items appearing).

### Session Loop (5-30 minutes)

- **Goal**: Solve a puzzle or overcome a gate to reach a new area of the world.
- **Tension**: Limited information — the player must explore, gather clues, collect items, and reason about how pieces fit together. Wrong approaches fail gracefully with informative messages, not dead ends.
- **Resolution**: The gate opens, a new region becomes accessible, and the player's score reflects their progress.

### Long-Term Loop (30 minutes - hours)

- **Progression**: The player unlocks progressively deeper regions of the world, each gated behind more complex puzzles that build on mechanics introduced earlier.
- **Retention Hook**: Hidden details in examine descriptions, optional puzzles, and side quests reward thorough exploration. Scoring incentivizes completionism.
- **Completion**: The game has a clear win condition. Reaching it provides closure; the score breakdown shows what was missed, inviting replay.

---

## Player Interactions

### Movement

Players navigate between rooms using directional commands.

**Supported directions:**
- `north`, `south`, `east`, `west`
- `up`, `down`
- Shortcuts: `n`, `s`, `e`, `w`, `u`, `d`
- Prefix form: `go north`, `go n`, etc.

**Movement behavior:**
- Moving to an unlocked exit transitions the player to the target room and displays that room's description.
- Moving to a locked exit displays the lock's failure message (e.g., "The iron door is locked. You'll need a key.").
- Moving to a nonexistent direction displays a standard rejection: "You can't go that way."
- Revisiting a room shows its `short_description` instead of the full `description`, unless the player explicitly types `look`.

Custom traversal actions like `enter`, `climb`, or `cross` are implemented as DSL commands rather than exit directions. The game author defines these as command rules with `move_player` effects.

### Inventory Management

- `take <item>` / `get <item>` / `pick up <item>` — pick up an item from the current room and add it to inventory. The item must be flagged as `takeable`. Prints the item's `take_message`.
- `take <item> from <container>` — take an item out of an accessible, open container.
- `drop <item>` — remove an item from inventory and place it in the current room. Prints the item's `drop_message`.
- `examine <item>` / `x <item>` / `look at <item>` — display an item's detailed `examine_description`. Works on items in inventory or in the current room. This is the primary way players discover clues.
- `read <item>` — display an item's `read_description` if it has one, or fall back to `examine_description`.
- `inventory` / `i` — list all carried items with their names, descriptions, toggle states, and quantities.

**Inventory constraints:**
- Items have a `takeable` flag. Scenery items (furniture, wall decorations, structural elements) cannot be taken but can be examined.
- There is no carry limit.

### Containers

Items can be containers — furniture, chests, bags, or any object that holds other items.

- `open <container>` — open a closed container, revealing its contents. Containers with `has_lid` must be opened before their contents are accessible.
- `search <container>` / `look in <container>` — inspect the contents of a container. Displays the container's `search_message` and lists visible items inside.
- `put <item> in <container>` / `use <item> on <container>` — place an inventory item into a container. Containers may have an `accepts_items` whitelist; items not on the list are rejected with a `reject_message`.
- `unlock <container>` — if the player holds the container's `key_item_id`, unlock and open it.

**Container properties:**
- `is_container` — marks the item as a container.
- `is_open` — runtime state for whether it's currently open.
- `has_lid` — whether the container can be opened/closed (a shelf has no lid; a chest does).
- `is_locked` — whether the container requires a key to open.
- `key_item_id` — the item that unlocks a locked container.
- `accepts_items` — optional JSON whitelist of accepted item IDs.

### Toggleable Items

Items can have on/off or multi-state toggles. Light sources, switches, and machines use this system.

- `turn on <item>` / `turn off <item>` — toggle an item's state. Displays the item's `toggle_on_message` or `toggle_off_message`.
- Items with a `requires_item_id` (e.g., a flashlight that requires batteries) only function when the required item is present and has remaining quantity.

**Light sources**: items tagged `light_source` with `toggle_state = "on"` illuminate dark rooms when carried. Dark rooms without an active light source show "It's pitch black. You can't see a thing." and block most interactions.

### Consumable Items

Items can have stackable quantities — ammunition, healing items, fuel charges.

- `quantity` / `max_quantity` — current and maximum stack count.
- `quantity_unit` — display unit ("rounds", "charges", "clumps").
- `depleted_message` — shown when quantity reaches zero.
- Quantities are consumed and restored via DSL command effects (`consume_quantity`, `restore_quantity`).

### Item Use

- `use <item>` — use an item by itself (e.g., toggle it, or trigger a DSL command rule).
- `use <item> on <target>` — use an item on another item, an NPC, or a room feature. This is the core puzzle interaction verb. Resolution follows a cascade:
  1. DSL command rules are checked first (specific authored interactions).
  2. The interaction matrix is checked (tag-based category responses).
  3. Container placement is attempted as a fallback.

**Resolution**: Every `use` interaction resolves through command rules or the interaction matrix. If no rule matches, the engine returns a failure message. There are no freeform item interactions — every valid use is pre-authored.

### Interaction Matrix

The interaction matrix provides category-level fallback responses for `use <item> on <target>`. Instead of authoring individual command rules for every possible item/target combination, the game author defines responses by item tag and target category.

For example, an interaction response with `item_tag = "firearm"` and `target_category = "character"` handles any firearm used on any character NPC, with `{item}` and `{target}` placeholders in the response text.

Interaction responses can consume item quantities, adjust score, set flags, and execute the same effects available to DSL commands (including `kill_target`, `damage_target`, `destroy_target`, and `open_target`).

### NPC Interaction

- `talk to <npc>` / `talk <npc>` — initiate a dialogue tree conversation. The engine presents the NPC's dialogue text and numbered response options. The player selects by number.
- `give <item> to <npc>` — transfer an inventory item to an NPC. Resolved via DSL command rules that define what happens when a specific item is given.
- `show <item> to <npc>` — present an item without giving it away. Resolved via DSL command rules.

**Dialogue trees**: NPCs have branching dialogue implemented through `dialogue_nodes` and `dialogue_options` tables:
- Each node contains NPC dialogue text and may set flags when visited.
- Options are the player's choices within a node. Each option can require flags or items to appear, set flags when chosen, and point to a next node (or end the conversation).
- Dialogue options can be gated by `required_flags`, hidden by `excluded_flags`, or require `required_items` in inventory.

**NPC behavior:**
- NPCs occupy a specific room. They can be moved between rooms via the `move_npc` effect.
- NPC dialogue changes based on flags — different dialogue paths become available as the game progresses.
- NPCs can block exits (`is_blocking`, `blocked_exit_id`) until an `unblock_flag` is set.
- NPCs have optional `hp` and `damage` stats for combat-capable games. The `kill_npc` effect marks an NPC as dead. Dead NPCs generate a searchable body container.

### Combat (Optional)

Combat is not a core mechanic, but the engine supports it through the interaction matrix and DSL commands.

- Combat verbs like `attack`, `hit`, `shoot` are implemented as DSL command rules or resolved through the interaction matrix (e.g., a `weapon`-tagged item used on a `hostile`-category NPC).
- Combat stats (player HP, NPC HP, damage values) are stored in the `player` and `npcs` tables and modified by `change_health`, `damage_target`, and `kill_npc` effects.
- Player death (HP reaching zero) is a lose condition.

**Combat is deliberately simple.** AnyZork is a puzzle-adventure engine first. Combat, when present, should serve as a puzzle gate (figure out the weakness) rather than a mechanical skill challenge.

### Information Commands

- `look` / `l` — redisplay the current room's full description, including items, NPCs, and exits.
- `help` / `h` / `?` — display built-in verbs, interaction verbs, movement shortcuts, and any game-specific DSL commands available in the current context.
- `score` — display current score, maximum possible score, moves, and HP, plus a per-event score breakdown.
- `quests` / `journal` / `quest` / `j` — display the quest log with main quest, side quests, and objective progress.
- `narrator on` / `narrator off` — toggle the optional LLM narrator layer during play.
- `save` — display the active save file path. Progress saves automatically to the managed save slot.
- `quit` / `exit` / `q` — exit the game.

---

## Narrator System

The narrator is an optional, read-only LLM layer that sits between the engine's deterministic output and the player's display. When enabled, it rewrites room descriptions and action results into atmospheric prose tailored to the game's tone, era, and setting.

**Key properties:**
- The narrator never changes game state — it only transforms display text.
- If the LLM call fails, the engine's deterministic output is shown instead. The game always works without the narrator.
- Room narrations are cached per room state (items + NPCs present), so revisiting an unchanged room reuses the previous narration.
- Narration can be toggled at any time during play with `narrator on` / `narrator off`, or enabled at launch with `--narrator`.
- Supports multiple LLM providers: Claude, OpenAI, and Gemini.

---

## Trigger System

Triggers are reactive rules that fire automatically when game events occur. They enable dynamic world responses without player-initiated commands.

**Supported event types:**
- `room_enter` — fires when the player enters a specific room.
- `flag_set` — fires when a specific flag becomes true.
- `item_taken` — fires when the player picks up a specific item.
- `item_dropped` — fires when the player drops a specific item.
- `dialogue_node` — fires when a specific dialogue node is visited.

**Trigger properties:**
- `event_data` — JSON partial match against the emitted event (e.g., `{"room_id": "vault"}`).
- `preconditions` — same format as DSL command preconditions. All must pass for the trigger to fire.
- `effects` — same format as DSL command effects. Applied when the trigger fires.
- `message` — optional text displayed when the trigger fires.
- `one_shot` — if true, the trigger fires only once.
- `priority` — higher-priority triggers evaluate first.

Events are queued and processed iteratively with a cascade limit of 20 to prevent infinite loops from circular flag dependencies.

---

## Room System

Rooms are the atomic unit of space in AnyZork. Every location the player can visit is a room.

### Room Properties

| Property | Purpose |
|---|---|
| `id` | Unique identifier (e.g., `dungeon_entrance`). Used in all references. |
| `name` | Display name (e.g., "Dungeon Entrance"). Shown in the panel title when entering. |
| `description` | Full prose description shown on first visit or when the player types `look`. Should establish atmosphere, mention visible items and exits, and embed clues for nearby puzzles. |
| `short_description` | Abbreviated description shown on subsequent visits. Should orient the player without repeating prose. |
| `first_visit_text` | Optional one-time text shown only the very first time the player enters. Used for cutscene-like moments, triggered events, or atmosphere-setting. |
| `is_dark` | Whether the room requires a light source to see. If dark and no light source, the player gets a darkness message and most interactions are blocked. |

### Room Rendering

The engine renders rooms as styled Rich panels with highlighted interactable names. Item and NPC names are color-coded by category (weapons in red, furniture in blue, NPCs in magenta, etc.).

Items with a `room_description` blend into the room body text as authored prose. Items without prose get a natural-language scene note ("Nearby, the rusty key catches the eye."). NPCs not mentioned in the room description are appended similarly.

Exits are listed below the room panel with destination names. Locked exits show a "(locked)" indicator instead of a destination.

### Room Description Design

Good room descriptions follow a layered structure:

1. **Atmosphere** (first sentence): sets the sensory tone. What does the player see, hear, smell, feel?
2. **Landmarks** (next 1-2 sentences): notable features of the room that establish it as a distinct place.
3. **Interactive elements** (embedded naturally): items and exits are woven into the prose, not listed mechanically. "A rusty key hangs from a hook by the door" is better than "Items: rusty key."
4. **Clue embedding** (subtle): details that become significant later. A scratched symbol on the wall, a faint smell of sulfur, an out-of-place book. These don't announce themselves as clues.

---

## Command DSL

Every player action beyond the built-in verbs is defined as a command rule in the database. Command rules are the core authoring mechanism — they define what happens when the player types something.

### Command Properties

| Property | Description |
|---|---|
| `verb` | The first word of the command (e.g., `pull`, `enter`, `pray`). |
| `pattern` | Full input pattern with `{slot}` placeholders (e.g., `pull {target}`). |
| `preconditions` | JSON array of conditions that must all pass (e.g., `has_item`, `in_room`, `has_flag`). |
| `effects` | JSON array of state changes to apply on success (e.g., `set_flag`, `unlock`, `spawn_item`). |
| `success_message` | Text shown when the command succeeds. |
| `failure_message` | Text shown when preconditions fail. |
| `context_room_ids` | JSON array of rooms where this command is valid. NULL = global. |
| `priority` | Higher-priority commands are tried first. |
| `one_shot` | If true, the command can only succeed once. |
| `done_message` | Text shown on subsequent attempts of a one-shot command. |

### Precondition Types

`in_room`, `has_item`, `has_flag`, `not_flag`, `item_in_room`, `item_accessible`, `npc_in_room`, `lock_unlocked`, `puzzle_solved`, `health_above`, `container_open`, `item_in_container`, `not_item_in_container`, `container_has_contents`, `container_empty`, `has_quantity`, `toggle_state`.

### Effect Types

`move_item`, `remove_item`, `set_flag`, `unlock`, `move_player`, `spawn_item`, `change_health`, `heal_player`, `damage_player`, `add_score`, `reveal_exit`, `solve_puzzle`, `discover_quest`, `print`, `open_container`, `move_item_to_container`, `take_item_from_container`, `consume_quantity`, `restore_quantity`, `set_toggle_state`, `move_npc`, `fail_quest`, `complete_quest`, `kill_npc`, `remove_npc`, `lock_exit`, `hide_exit`, `change_description`, `make_visible`, `make_hidden`, `make_takeable`.

---

## Puzzle System

Puzzles are the primary progression mechanic. They are what makes the game a game rather than a walking simulator.

### Puzzle Structure

Every puzzle has:

| Component | Description |
|---|---|
| `id` | Unique identifier. |
| `name` | Human-readable name for internal reference. |
| `description` | What the puzzle looks like to the player (this is not shown directly — it guides how the puzzle manifests in room descriptions and item examinations). |
| `room_id` | The room where this puzzle is located. |
| `solution_steps` | JSON array describing the ordered steps the player must perform. |
| `hint_text` | Optional JSON array of progressive hints. |
| `difficulty` | Relative difficulty rating (integer) guiding generation pacing. |
| `score_value` | Points awarded when the puzzle is solved. |
| `is_optional` | Whether the puzzle is off the critical path. |

Puzzle completion is tracked by the `is_solved` flag. The `solve_puzzle` effect marks a puzzle as solved. Preconditions, rewards, and the actual mechanical steps are implemented through DSL command rules that reference the puzzle.

### Puzzle Types

**Fetch puzzles**: bring item X to location Y or NPC Z.
- Example: Find the ancient coin in the well, give it to the ferryman to cross the river.

**Use-on puzzles**: use item X on target Y to produce an effect.
- Example: Use the fire crystal on the frozen door to melt the ice.

**Combination puzzles**: combine items A and B to create item C, then use C. Implemented as DSL commands with custom verbs like `combine`.
- Example: Combine the lens and the brass tube to make a telescope. Use the telescope on the tower window to read the distant inscription.

**Sequence puzzles**: perform actions in a specific order.
- Example: Pull the levers in the order described by the mural — left, right, center.

**Knowledge puzzles**: the solution requires information found elsewhere in the world.
- Example: The combination lock code is scattered across three books in three different rooms.

**State-based puzzles**: the world must be in a certain state before the solution works.
- Example: The shadow only appears when the lantern is lit and placed on the pedestal. The shadow points to the hidden passage.

**NPC-gated puzzles**: an NPC must be persuaded, traded with, or given information before they'll help.
- Example: The blacksmith will forge the key only after you bring him the ore AND tell him the shape (learned from the engraving in the tomb).

### Multi-Step Puzzles

The best puzzles chain multiple steps, each of which feels like its own discovery:

1. Player finds a torn page in the library describing a "moonstone's resting place."
2. Player examines the fountain in the garden — the description mentions the basin is shaped like a crescent moon.
3. Player uses the moonstone on the fountain — the water drains, revealing a passage.

Each step gives the player a moment of realization. The generator should create puzzles where the "aha!" moment comes from connecting information across rooms, not from brute-force trying every combination.

### Puzzle Fairness Contract

Every generated puzzle MUST obey these rules:

1. **All clues exist in the world.** The player never needs out-of-game knowledge.
2. **Clues precede the puzzle.** The player encounters the clue before (or simultaneously with) the puzzle, never after.
3. **Red herrings are minimal and fair.** A few misleading items add flavor; a world full of useless noise is hostile.
4. **Failure is informative.** When a wrong solution is tried, the feedback should hint at what's wrong, not just say "nothing happens."
5. **No softlocks.** The player can never reach a state where the game is unwinnable. If a key item is consumed, it must not be needed again. If a one-way path exists, everything needed beyond it is accessible.

---

## Lock and Key System

Locks gate player progression. Every lock has a corresponding key (broadly defined). The lock/key system is the backbone of pacing.

### Lock Types

**Physical key lock**: a specific item unlocks a specific exit.
- Key: `rusty_key` unlocks Exit: `iron_door`.
- The key may or may not be consumed on use (configurable via `consume_key`).

**Puzzle lock**: solving a puzzle unlocks the exit.
- The puzzle's reward effect includes `unlock`.
- Example: Solving the lever sequence opens the portcullis.

**Combination lock**: the player must enter a code.
- The code is discoverable somewhere in the game world.
- Implemented as a DSL command with a pattern like `enter {code}` and a precondition checking the code value.

**State-based lock**: a set of flags must be true.
- Example: The magical barrier drops only when all three crystals are placed on their pedestals (three separate flags).

**NPC lock**: an NPC blocks the path until a condition is met.
- Example: The guard won't let you pass until you show the royal signet.

### Lock Properties

| Property | Description |
|---|---|
| `id` | Unique identifier. |
| `lock_type` | One of: `key`, `puzzle`, `combination`, `state`, `npc`. |
| `target_exit_id` | The exit this lock gates. |
| `key_item_id` | For key locks: the item that unlocks it. |
| `puzzle_id` | For puzzle locks: the puzzle whose completion unlocks it. |
| `combination` | For combination locks: the correct code. |
| `required_flags` | For state locks: JSON array of flag conditions that must all be true. |
| `locked_message` | What the player sees when they try to pass while locked. Should hint at the solution type. |
| `unlock_message` | What the player sees when the lock opens. |
| `is_locked` | Runtime state — whether the lock is currently active. |
| `consume_key` | Whether using the key destroys it (default: true). |

### Progression Graph

The generator should create a progression structure that follows these principles:

- **Hub-and-spoke early game**: the starting area has multiple paths, some gated, some open. The player has agency in choosing what to explore first.
- **Gated bottlenecks mid-game**: major region transitions require solving a significant puzzle or collecting multiple items. This ensures the player has explored thoroughly before advancing.
- **Convergent endgame**: late-game gates may require items or knowledge from multiple earlier regions, testing the player's accumulated understanding.
- **No required backtracking without purpose**: if the player must return to an earlier area, it should be because new information recontextualizes that area, not because of tedious fetch quests.

---

## Quest System

Quests give the player explicit direction without turning the game into a rigid checklist.

### Main Quest

Every generated game has exactly one main quest. It represents the big-picture goal of the adventure and should align with the actual win condition.

Main-quest rules:

- Auto-discovered at game start (no `discovery_flag` needed)
- Built from 2-5 clear objectives tracked by `completion_flag` on each objective
- Tracks critical-path progress
- Usually awards `0` score directly because the gated puzzles and milestones already carry their own rewards

### Side Quests

Side quests reward exploration, optional dialogue, and off-critical-path discoveries.

Good side quests:

- reuse existing rooms, items, NPCs, and flags
- clarify why optional content matters
- provide score, shortcuts, rewards, or narrative payoff
- can often be progressed in parallel with the main quest
- require a `discovery_flag` — they appear in the journal only after the player triggers their discovery

### Objectives

Quest objectives are tracked by deterministic flags. The quest system observes those flags and presents progress to the player; it does not gate mechanics on its own.

When an objective's `completion_flag` becomes true, the engine displays a notification showing the completed objective and overall quest progress. When all required objectives for a quest are complete, the quest is marked completed and the player sees a completion panel with any associated score award.

Typical objective patterns:

- Find an item
- Reach a room
- Solve a puzzle
- Convince or help an NPC
- Complete a multi-step collection or restoration task

### Player-Facing Journal

The player uses `quests`, `journal`, `quest`, or `j` to open the quest log.

Display layout:

- Main quest first, with status and objectives
- Side quests grouped separately, visible only once discovered
- Each objective shows a checkbox (complete/incomplete)
- Completed and failed quests are displayed with their final status

---

## Scoring System

Scoring provides extrinsic motivation and a measure of completeness.

### Score Sources

| Source | Typical Value | Notes |
|---|---|---|
| Required puzzle solved | 10-25 pts | Scales with difficulty. |
| Optional puzzle solved | 15-30 pts | Higher than required — rewards going off the critical path. |
| Region unlocked | 5-10 pts | Milestone marker. |
| Side quest completed | 5-20 pts | Rewards optional exploration and follow-through. |
| Bonus objective completed | 2-10 pts | Optional steps inside a quest. |
| Optional discovery or hidden shortcut | 2-10 pts | For worthwhile but non-quest optional content. |
| NPC task completed | 5-15 pts | Often represented as a side quest or quest objective. |

All values above are `[PLACEHOLDER]` ranges. The generator should assign specific values per game, scaling to a target maximum score.

### Score Display

- `score` command shows: current score, maximum possible score, move count, HP, and a per-event breakdown listing the reason, points earned, and move number for each scoring event.
- On game completion (win condition), the final score is displayed with the full breakdown.

### Score as Design Feedback

During generation validation, the scoring system serves as a self-check:
- If max score is achievable only through the critical path, the game lacks optional content.
- If 80%+ of the score comes from quest completion with no puzzle or exploration rewards, the game lacks mechanical texture.
- A well-balanced game should have roughly 50% critical-path score and 50% optional-content score.

---

## Win and Lose Conditions

### Win Conditions

Every generated game defines at least one win condition — a flag or set of flags that, when all true, trigger the victory sequence.

**Common win condition patterns:**
- **Reach a location**: arrive at the final room after all gates are unlocked (e.g., "Escape the dungeon by reaching the exit").
- **Collect a set**: gather all N macguffins and bring them to a location (e.g., "Restore the three crystals to the altar").
- **Defeat a foe**: reduce an NPC's HP to zero using the correct strategy.
- **Achieve a state**: set all required flags through various puzzle solutions (e.g., "Lift the curse by performing the three rituals").

The authored game defines `win_conditions` as a JSON array of flag IDs in the metadata table. The engine checks after every command whether all win-condition flags are true. When triggered, it displays the `win_text`, shows the final score breakdown, and ends the game.

### Lose Conditions

Lose conditions are optional. Not every generated game needs them.

**Common lose condition patterns:**
- **Player death**: HP reaches zero (only in games with combat or hazards).
- **Flag-based failure**: a specific lose-condition flag becomes true through player actions.

Lose conditions are defined as a JSON array of flag IDs in `lose_conditions`. When triggered, the engine displays the `lose_text` and ends the game.

### No-Lose Design Preference

Generated games should strongly prefer designs where **the player cannot lose through normal exploration**. Death should only come from clearly dangerous, opt-in actions (attacking a dragon without preparation, drinking an obviously poisoned potion). A player who is cautious and observant should never die by surprise.

---

## What Makes a Good Generated Game

The import and validation flow evaluates authored games against these quality criteria. A game that meets all of these is well-designed; a game that fails any of them needs revision.

### Interconnectedness

- Every room connects to at least one other room (no orphans).
- Every item is either useful for a puzzle, a key for a lock, part of a quest/objective, or meaningful scenery. No item exists without purpose.
- Every NPC contributes something: information, a trade, a gate, a trigger, or a quest. No NPC exists as empty decoration.
- Puzzles reference items, rooms, and NPCs from across the world, not just their immediate vicinity.

### Pacing

- The first 5 minutes introduce the core verbs: move, look, take, examine, use. The player succeeds at each.
- The first puzzle is solvable within the starting area with no gating. It teaches the player that exploration and examination lead to solutions.
- Difficulty increases gradually. Mid-game puzzles should have 2-3 steps. Late-game puzzles should have 3-5 steps or require synthesis of information from multiple regions.
- There should be a rhythm of tension (stuck on a puzzle) and release (breakthrough). Two hard puzzles in a row is acceptable; four is not.

### Fairness

- Every puzzle is solvable with in-game information.
- Every locked exit has a discoverable key/solution.
- The game is completable — there are no dead ends, softlocks, or unwinnable states.
- Examine descriptions contain real clues, not just atmospheric fluff.

### World Coherence

- Room descriptions are internally consistent (a room described as small doesn't have six exits).
- Items make sense in their locations (a ship's wheel in a harbor, not a library).
- NPC dialogue reflects the world's tone and the NPC's role.
- Quests, clues, room text, and dialogue all reinforce the same underlying story instead of pulling in different directions.

### Mechanical Clarity

- The player always knows what verbs are available.
- Failure messages are specific: "The door is locked" is better than "You can't do that." "The key doesn't fit this lock" is better than "Nothing happens."
- When the player is stuck, examining items and talking to NPCs should provide enough information to make progress. The game should never require the player to guess blindly.

---

## Generation Quality Checklist

The import-time validator confirms:

- [ ] All exits are bidirectional (or explicitly one-way with narrative justification).
- [ ] All key-type locks have their key item reachable before the lock in a valid unlock order.
- [ ] All puzzles have all required items placed in the world.
- [ ] No items are referenced in commands but missing from the items table.
- [ ] No rooms are unreachable from the start room.
- [ ] The win condition flags are achievable by following the critical path.
- [ ] Exit foreign keys reference valid rooms.
- [ ] Item room references and container references are valid.
- [ ] NPC room references are valid.
- [ ] Lock target exits exist.
- [ ] DSL commands use only valid precondition and effect types.
- [ ] Triggers use only valid event types.
- [ ] Dark rooms have a light source accessible before or at the room.
