# AnyZork Game Design Document

> This GDD describes the **engine's design space** — the mechanics, systems, and structures that AnyZork supports so that an LLM can generate complete, playable text adventure games within these constraints.

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
- **Tension**: Limited information — the player must explore, gather clues, collect items, and reason about how pieces fit together. Wrong approaches fail gracefully with hints, not dead ends.
- **Resolution**: The gate opens, a new region becomes accessible, and the player's score reflects their progress.

### Long-Term Loop (30 minutes - hours)

- **Progression**: The player unlocks progressively deeper regions of the world, each gated behind more complex puzzles that build on mechanics introduced earlier.
- **Retention Hook**: Lore discovery across three tiers rewards thorough exploration. Scoring incentivizes completionism. Optional challenges provide replayability.
- **Completion**: The game has a clear win condition. Reaching it provides closure; the score breakdown shows what was missed, inviting replay.

---

## Player Interactions

### Movement

Players navigate between rooms using directional commands and custom named exits.

**Standard compass directions:**
- `north`, `south`, `east`, `west`
- `northeast`, `northwest`, `southeast`, `southwest`
- `up`, `down`

**Custom/contextual exits:**
- Named exits defined per-room: `enter cave`, `climb ladder`, `cross bridge`, `jump chasm`
- These appear in room descriptions so the player knows they exist

**Movement behavior:**
- Moving to an unlocked exit transitions the player to the target room and displays that room's description.
- Moving to a locked exit displays the lock's failure message (e.g., "The iron door is locked. You'll need a key.").
- Moving to a nonexistent direction displays a standard rejection (e.g., "You can't go that way.").
- Revisiting a room shows its `short_description` instead of the full `description`, unless the player explicitly types `look`.

### Inventory Management

- `take <item>` / `get <item>` — pick up an item from the current room and add it to inventory. The item must be flagged as `takeable`. Prints the item's `take_message`.
- `drop <item>` — remove an item from inventory and place it in the current room. Prints the item's `drop_message`.
- `examine <item>` / `inspect <item>` / `look at <item>` — display an item's detailed `examine_description`. Works on items in inventory or in the current room. This is the primary way players discover clues.
- `inventory` / `i` — list all carried items with their short names.

**Inventory constraints:**
- Items have a `takeable` flag. Scenery items (furniture, wall decorations, structural elements) cannot be taken but can be examined.
- There is no carry limit by default. Generated games may optionally define one via a flag.

### Item Use

- `use <item>` — use an item by itself (e.g., `use lantern` to light it). Resolved via a command rule with preconditions.
- `use <item> on <target>` — use an item on another item, an NPC, or a room feature (e.g., `use rusty_key on iron_door`). This is the core puzzle interaction verb.
- `combine <item> with <item>` — merge two inventory items into a new item (e.g., `combine rope with hook` produces `grappling_hook`). The source items are consumed; the result item is spawned into inventory.

**Resolution**: Every `use` and `combine` interaction is a command rule in the database. If no rule matches the player's input, the engine returns a generic failure message. There are no freeform item interactions — every valid use is pre-authored by the generator.

### NPC Interaction

- `talk to <npc>` / `speak to <npc>` — initiate dialogue. NPCs have a dialogue tree or a set of dialogue lines gated by game state (flags).
- `ask <npc> about <topic>` — query an NPC about a specific topic. Topics are keywords the NPC recognizes. Unknown topics get a default deflection response.
- `give <item> to <npc>` / `trade <item> with <npc>` — transfer an item to an NPC. May trigger a trade (NPC gives something back) or a quest progression (NPC reacts to receiving the item).
- `show <item> to <npc>` — present an item without giving it away. May trigger dialogue or information.

**NPC behavior:**
- NPCs occupy a specific room. They may move between rooms if the generator defines movement patterns (via flags), but this is optional.
- NPC dialogue can change based on flags. For example, an NPC might say different things before and after a quest is completed.
- NPCs can block exits (acting as gates) until a condition is met.

### Combat (Optional)

Combat is not a core mechanic for every generated game, but the engine supports it when the generator includes it.

- `attack <target>` / `fight <target>` — initiate combat with an NPC or creature.
- Combat is **turn-based and command-driven**: the player chooses actions (attack, defend, use item, flee) and the engine resolves them against rules.
- Combat stats (player HP, enemy HP, damage values) are stored as flags and modified by command effects.
- Death is a lose condition unless the generator provides revival mechanics.

**Combat is deliberately simple.** AnyZork is a puzzle-adventure engine first. Combat, when present, should serve as a puzzle gate (figure out the weakness) rather than a mechanical skill challenge.

### Information Commands

- `look` / `l` — redisplay the current room's full description, including items and exits.
- `help` — display available verbs and general guidance.
- `score` — display current score and maximum possible score.
- `save` / `load` — managed externally (copy the `.zork` file), but the commands are recognized.
- `quit` / `q` — exit the game.
- `hint` — if the generator provides hints, display a context-sensitive hint based on the player's current state.

---

## Room System

Rooms are the atomic unit of space in AnyZork. Every location the player can visit is a room.

### Room Properties

| Property | Purpose |
|---|---|
| `id` | Unique identifier (e.g., `dungeon_entrance`). Used in all references. |
| `name` | Display name (e.g., "Dungeon Entrance"). Shown in the header when entering. |
| `description` | Full prose description shown on first visit or when the player types `look`. Should establish atmosphere, mention visible items and exits, and embed clues for nearby puzzles. |
| `short_description` | Abbreviated description shown on subsequent visits. Should orient the player without repeating prose. |
| `first_visit_text` | Optional one-time text shown only the very first time the player enters. Used for cutscene-like moments, triggered events, or atmosphere-setting. |
| `region` | Groups rooms into logical areas (e.g., "Forest", "Castle", "Caves"). Used for theming and progression tracking. |
| `is_dark` | Whether the room requires a light source to see. If dark and no light source, the player gets a darkness description and cannot examine items or read descriptions. |
| `visited` | Runtime state flag — tracks whether the player has been here before. |

### Room Description Design

Good room descriptions follow a layered structure:

1. **Atmosphere** (first sentence): sets the sensory tone. What does the player see, hear, smell, feel?
2. **Landmarks** (next 1-2 sentences): notable features of the room that establish it as a distinct place.
3. **Interactive elements** (embedded naturally): items and exits are woven into the prose, not listed mechanically. "A rusty key hangs from a hook by the door" is better than "Items: rusty key."
4. **Clue embedding** (subtle): details that become significant later. A scratched symbol on the wall, a faint smell of sulfur, an out-of-place book. These don't announce themselves as clues.

### Regions

Regions group rooms into thematic and mechanical areas:

- **Thematic cohesion**: rooms in a region share tone, vocabulary, and atmosphere.
- **Progression gating**: regions are often separated by locks/gates. Unlocking access to a new region is a major progression milestone.
- **Pacing**: early regions are simpler (fewer puzzles, more guidance). Later regions increase complexity.
- **The generator should create 2-5 regions** depending on game scale, with 3-8 rooms per region.

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
| `solution_steps` | Ordered list of actions the player must perform. Can be a single step or multi-step. |
| `preconditions` | What must be true before the puzzle is solvable (items in inventory, flags set, rooms visited). |
| `rewards` | What happens when the puzzle is solved: unlock an exit, spawn an item, set a flag, add score, print a message. |
| `hint_text` | Optional progressive hints the player can request. |
| `difficulty` | Relative difficulty rating guiding generation pacing. |

### Puzzle Types

**Fetch puzzles**: bring item X to location Y or NPC Z.
- Example: Find the ancient coin in the well, give it to the ferryman to cross the river.

**Use-on puzzles**: use item X on target Y to produce an effect.
- Example: Use the fire crystal on the frozen door to melt the ice.

**Combination puzzles**: combine items A and B to create item C, then use C.
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
- The key may or may not be consumed on use (configurable).

**Puzzle lock**: solving a puzzle unlocks the exit.
- The puzzle's reward effect includes `unlock_exit`.
- Example: Solving the lever sequence opens the portcullis.

**Combination lock**: the player must enter a code.
- The code is discoverable somewhere in the game world.
- Implemented as a command with a pattern like `enter <code>` and a precondition checking the code value.

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
| `required_flags` | For state locks: the flag conditions that must all be true. |
| `locked_message` | What the player sees when they try to pass while locked. Should hint at the solution type. |
| `unlock_message` | What the player sees when the lock opens. |
| `is_locked` | Runtime state — whether the lock is currently active. |
| `consume_key` | Whether using the key destroys it. |

### Progression Graph

The generator should create a progression structure that follows these principles:

- **Hub-and-spoke early game**: the starting area has multiple paths, some gated, some open. The player has agency in choosing what to explore first.
- **Gated bottlenecks mid-game**: major region transitions require solving a significant puzzle or collecting multiple items. This ensures the player has explored thoroughly before advancing.
- **Convergent endgame**: late-game gates may require items or knowledge from multiple earlier regions, testing the player's accumulated understanding.
- **No required backtracking without purpose**: if the player must return to an earlier area, it should be because new information recontextualizes that area, not because of tedious fetch quests.

---

## Lore System

Lore adds depth and replayability. It is layered into three tiers so that different player types all find something rewarding.

### Tier 1: Surface Lore

**Audience**: Every player, including those who just want to solve puzzles and move on.

**Delivery**: Embedded in room descriptions, NPC dialogue, and item names. The player absorbs this passively by playing the game normally.

**Examples**:
- Room descriptions mention a war that scarred the land.
- An NPC refers to "the old king" in passing.
- Item names imply history: "a sword with a notched blade" rather than just "a sword."

**Purpose**: Establishes the world's tone and makes it feel like a place with history, not a series of puzzle rooms.

### Tier 2: Engaged Lore

**Audience**: Players who examine things, talk to NPCs beyond what's required, and explore optional rooms.

**Delivery**: Found by examining items closely, asking NPCs about optional topics, reading books/scrolls/inscriptions, and visiting optional rooms.

**Examples**:
- Examining the sword reveals an inscription: "Forged for Captain Aldric, who held the bridge at Thornwall."
- Asking the innkeeper about "the old king" triggers a story about the kingdom's fall.
- A hidden journal in an optional room describes the dungeon's original purpose.

**Purpose**: Rewards curiosity with context. The player who engages with the world understands *why* things are the way they are.

### Tier 3: Deep Lore

**Audience**: Lore hunters, completionists, and second-playthrough players.

**Delivery**: Requires connecting information across multiple sources, solving optional puzzles, or finding well-hidden secrets.

**Examples**:
- Combining clues from three different inscriptions reveals that the "hero" of the surface lore was actually the villain.
- An optional puzzle in a hidden room unlocks a sealed chamber containing a chronicle that reframes the entire story.
- Examining a seemingly decorative item after learning a specific fact (setting a flag) reveals new text.

**Purpose**: Rewards mastery and thoroughness with the richest narrative payoff. These are the moments players share and discuss.

### Lore Properties

| Property | Description |
|---|---|
| `id` | Unique identifier. |
| `tier` | `surface`, `engaged`, or `deep`. |
| `content` | The lore text itself. |
| `delivery_method` | How the player encounters it: `room_description`, `examine`, `dialogue`, `inscription`, `book`, `puzzle_reward`. |
| `location_id` | Room where this lore is found (if applicable). |
| `item_id` | Item this lore is attached to (if applicable). |
| `npc_id` | NPC who delivers this lore (if applicable). |
| `required_flags` | Flags that must be set before this lore is visible/accessible. |
| `score_value` | Points awarded for discovering this lore. |

---

## Scoring System

Scoring provides extrinsic motivation and a measure of completeness.

### Score Sources

| Source | Typical Value | Notes |
|---|---|---|
| Required puzzle solved | 10-25 pts | Scales with difficulty. |
| Optional puzzle solved | 15-30 pts | Higher than required — rewards going off the critical path. |
| Region unlocked | 5-10 pts | Milestone marker. |
| Lore discovered (surface) | 0 pts | Surface lore is free — no score incentive needed. |
| Lore discovered (engaged) | 2-5 pts | Small reward for curiosity. |
| Lore discovered (deep) | 10-20 pts | Substantial reward for thoroughness. |
| Optional challenge completed | 10-25 pts | Time-based, inventory-limited, or otherwise constrained challenges. |
| NPC quest completed | 5-15 pts | Helping NPCs beyond the critical path. |

All values above are `[PLACEHOLDER]` ranges. The generator should assign specific values per game, scaling to a target maximum score.

### Score Display

- `score` command shows: current score, maximum possible score, and a breakdown by category.
- On game completion (win condition), the final score is displayed with a summary of what was found and what was missed, without spoiling specific solutions.

### Score as Design Feedback

During generation validation, the scoring system serves as a self-check:
- If max score is achievable only through the critical path, the game lacks optional content.
- If 80%+ of the score comes from lore, the game lacks mechanical depth.
- A well-balanced game should have roughly 50% critical-path score and 50% optional-content score.

---

## Win and Lose Conditions

### Win Conditions

Every generated game defines at least one win condition — a flag or set of flags that, when all true, trigger the victory sequence.

**Common win condition patterns:**
- **Reach a location**: arrive at the final room after all gates are unlocked (e.g., "Escape the dungeon by reaching the exit").
- **Collect a set**: gather all N macguffins and bring them to a location (e.g., "Restore the three crystals to the altar").
- **Defeat a boss**: reduce an NPC's HP to zero using the correct strategy (e.g., "Defeat the dragon using its weakness to silver").
- **Achieve a state**: set all required flags through various puzzle solutions (e.g., "Lift the curse by performing the three rituals").

The generator defines the `win_condition` as a set of flags. The engine checks after every command whether all win-condition flags are true.

### Lose Conditions

Lose conditions are optional. Not every generated game needs them.

**Common lose condition patterns:**
- **Player death**: HP reaches zero (only in games with combat or hazards).
- **Time/move limit**: exceeded maximum moves (only if the generator imposes this as a design choice — it should be thematic, not arbitrary).
- **Catastrophic action**: the player does something irreversible that makes winning impossible. (This should be rare and well-telegraphed. The design philosophy strongly discourages unwinnable states.)

**On losing**: the engine displays the lose message and offers to restore to the last safe state (or restart).

### No-Lose Design Preference

The generator should strongly prefer designs where **the player cannot lose through normal exploration**. Death should only come from clearly dangerous, opt-in actions (attacking a dragon without preparation, drinking an obviously poisoned potion). A player who is cautious and observant should never die by surprise.

---

## What Makes a Good Generated Game

The generation pipeline should evaluate its output against these quality criteria. A game that meets all of these is well-designed; a game that fails any of them needs another pass.

### Interconnectedness

- Every room connects to at least one other room (no orphans).
- Every item is either useful for a puzzle, a key for a lock, a lore carrier, or meaningful scenery. No item exists without purpose.
- Every NPC contributes something: information, a trade, a gate, or lore. No NPCs exist as empty decoration.
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
- Lore across all three tiers tells a consistent, layered story — not contradictory fragments.

### Mechanical Clarity

- The player always knows what verbs are available.
- Failure messages are specific: "The door is locked" is better than "You can't do that." "The key doesn't fit this lock" is better than "Nothing happens."
- When the player is stuck, examining items and talking to NPCs should provide enough information to make progress. The game should never require the player to guess blindly.

---

## Generation Quality Checklist

The validation pass should confirm:

- [ ] All exits are bidirectional (or explicitly one-way with narrative justification).
- [ ] All locks have corresponding keys/solutions reachable before the lock is encountered.
- [ ] All puzzles have all required items placed in the world.
- [ ] No items are referenced in commands but missing from the items table.
- [ ] No rooms are unreachable from the start room.
- [ ] The win condition is achievable by following the critical path.
- [ ] The critical path has been simulated — every step works mechanically.
- [ ] At least one puzzle exists per region.
- [ ] Lore exists at all three tiers.
- [ ] Score totals are sensible (critical path = ~50% of max score).
- [ ] No NPC references items or locations that don't exist.
- [ ] Dark rooms have a light source accessible before or at the room.
