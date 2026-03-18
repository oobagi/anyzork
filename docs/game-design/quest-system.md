# Quest System Design

> Replaces the lore system (Pass 8). Quests give the player clear objectives, a sense of progression, and a reason to explore. This document is the authoritative spec for the quest system -- schema, engine behavior, generation, and integration with existing systems.

## Why Replace Lore

The lore system has four problems:

1. **Content is mundane.** The LLM generates "lore" about things like worn rug fibres. It is flavor text, not meaningful narrative. Players do not feel rewarded for discovering it.

2. **No sense of progression.** Lore entries are isolated fragments. There is no objective, no completion arc, no feeling of building toward something. The player never thinks "I have three of five pieces" or "I need to do X next."

3. **The tiered system is confusing.** "Surface", "engaged", "deep" are designer-facing categories that do not map to how players think about games. Players think in quests and objectives, not content tiers.

4. **Yellow italic text appears randomly.** When the player examines an item with lore attached, extra text pops up in yellow italic. It feels like a bug, not a feature. There is no context for why this text appeared or what it means for the player.

The quest system solves all four problems by replacing passive lore discovery with active objectives the player pursues, tracks, and completes.

---

## Design Pillars

These are the non-negotiable properties of the quest system:

1. **Quests are player-legible.** The player always knows what they are trying to do. Quest names, descriptions, and objectives are written in plain language from the player's perspective.

2. **Quests create direction without linearity.** A player with three active quests has three reasons to explore. They choose which to pursue. The system provides structure without dictating sequence.

3. **Quests integrate with existing systems.** Puzzles, NPCs, items, flags, and the command DSL already exist. Quests sit on top of these systems -- they observe and organize what is already there, not replace it.

4. **One main quest defines the game.** Every generated game has a main quest whose completion is the win condition. The player always knows the big-picture goal. Side quests are optional content that reward exploration.

5. **Everything is deterministic.** Quest state lives in SQLite. Quest advancement is triggered by flags and DSL effects. No LLM at runtime.

---

## Quest Structure

### What Is a Quest

A quest is a named objective with one or more trackable steps. It has a lifecycle: the player discovers it, works toward it, and completes it (or, in rare cases, fails it).

Every quest has:

| Property | Description |
|---|---|
| **Name** | A short, evocative title the player sees: "The Missing Lantern", "The Hermit's Bargain" |
| **Description** | 1-3 sentences explaining what the player needs to do, written as if an NPC or journal entry were describing the task |
| **Objectives** | An ordered list of concrete steps, each independently trackable |
| **Type** | `main` or `side` -- exactly one quest is `main`, all others are `side` |
| **Status** | `undiscovered`, `active`, `completed`, or `failed` |
| **Score value** | Points awarded on completion |
| **Discovery method** | How the player first learns about this quest |

### What Is an Objective

An objective is a single trackable step within a quest. Objectives are the atoms of quest progress.

Every objective has:

| Property | Description |
|---|---|
| **Description** | A short phrase describing the step: "Find the rusty key", "Bring the ore to the blacksmith", "Solve the fountain puzzle" |
| **Completion flag** | The flag ID that, when set to `"true"`, marks this objective as complete |
| **Order index** | Position in the quest's objective list (for display, not for gating -- see Sequential vs Parallel below) |
| **Is optional** | Whether this objective must be completed for the quest to complete. Optional objectives provide bonus score. |
| **Status** | `incomplete` or `complete` (derived from flag state at runtime) |

### Sequential vs Parallel Objectives

Objectives within a quest are **not sequentially gated by default**. If a quest has three objectives, the player can complete them in any order. This matches how text adventures work -- the player explores freely and may stumble onto step 3 before step 1.

If the generator needs sequential ordering (step 2 is impossible before step 1), it enforces that through the existing precondition/flag system on the relevant commands, not through the quest system itself. The quest system only observes flag state; it never gates actions.

This is a deliberate design choice. The quest system is a **tracking and display layer**, not a gating layer. Gating is handled by commands, locks, and flags.

---

## Quest Types

These are the patterns the LLM should use when designing quests. They are not rigid categories -- a single quest may combine multiple patterns.

### Fetch Quest
"Bring X to Y."

The player must find an item and deliver it to a location or NPC. The item may need to be found through exploration, puzzle-solving, or NPC interaction.

**Example:** "The blacksmith needs star iron to forge the blade. Find the star iron in the collapsed mine and bring it to him."

**Objectives:**
1. Find the star iron (flag: `has_star_iron` or `player_has_item` resolved via flag)
2. Give the star iron to the blacksmith (flag: `gave_star_iron_to_blacksmith`)

### Exploration Quest
"Find the hidden place."

The player must discover a specific room or hidden area. Completion triggers when the player enters the target room or reveals a hidden exit.

**Example:** "Legends speak of a sealed chamber beneath the fountain. Find a way in."

**Objectives:**
1. Discover the entrance to the undercroft (flag: `fountain_activated`)

### Puzzle Quest
"Solve the challenge."

The player must solve one or more puzzles. This is the most common quest type for the main quest, since puzzles are the primary progression mechanic.

**Example:** "The three crystals must be returned to the altar to lift the curse."

**Objectives:**
1. Place the red crystal (flag: `crystal_red_placed`)
2. Place the blue crystal (flag: `crystal_blue_placed`)
3. Place the green crystal (flag: `crystal_green_placed`)

### Collection Quest
"Find all N of something."

The player must collect a set of related items scattered across the world. Each item found advances the quest.

**Example:** "Five torn pages of the captain's journal are scattered throughout the castle. Collect them all to learn the truth."

**Objectives:**
1. Find page 1 (flag: `has_journal_page_1`)
2. Find page 2 (flag: `has_journal_page_2`)
3. Find page 3 (flag: `has_journal_page_3`)
4. Find page 4 (flag: `has_journal_page_4`)
5. Find page 5 (flag: `has_journal_page_5`)

### NPC Task Quest
"Do what the NPC asks."

An NPC gives the player a task. Completion may require talking to other NPCs, finding items, or solving puzzles. The NPC's dialogue changes after completion.

**Example:** "The gate guard needs to see the Captain's seal before he'll let you through. Find Captain Maren and obtain her seal."

**Objectives:**
1. Learn about Captain Maren (flag: `learned_captain_name`)
2. Find Captain Maren (flag: `spoke_to_captain`)
3. Obtain the Captain's seal (flag: `has_captain_seal`)
4. Show the seal to the guard (flag: `guard_convinced`)

---

## Quest Discovery

Quests must be discovered before they appear in the player's journal. Discovery methods:

### Automatic (Main Quest)
The main quest is always discovered at game start. It appears in the journal from the first moment. The intro text should establish what the main quest is.

### NPC-Given
Talking to an NPC triggers quest discovery. The NPC's dialogue includes information that implies a task, and a `discover_quest` effect adds the quest to the journal.

**Example:** The guard says "No one enters without the Captain's seal." This dialogue's `set_flags` sets a flag that triggers the quest's discovery.

### Exploration-Triggered
Entering a room or examining an item triggers quest discovery. Useful for side quests the player finds by exploring off the critical path.

**Example:** The player enters an optional room and finds a half-finished letter. Examining it reveals a plea for help and discovers a side quest.

### Event-Triggered
A command effect discovers a quest as part of a larger action. Solving one puzzle might reveal that a bigger challenge exists.

**Example:** Solving the first puzzle reveals an inscription that implies three more puzzles must be solved. A side quest is discovered.

---

## Quest Tracking (Player-Facing)

### The `quests` Command

The player types `quests` (or `journal`, `quest log`, `j`) to see their quest status.

**Display when quests exist:**

```
============ Quest Log ============

  MAIN QUEST
  The Curse of Thornwall
  Lift the curse by performing the three rituals.
  [x] Complete the Ritual of Fire
  [x] Complete the Ritual of Water
  [ ] Complete the Ritual of Earth
  Progress: 2/3

  SIDE QUESTS
  The Captain's Journal            [COMPLETED]
  Collected all 5 journal pages.

  The Hermit's Bargain             [ACTIVE]
  Bring the hermit a silver mirror.
  [ ] Find the silver mirror
  [ ] Deliver the mirror to the hermit
  Progress: 0/2

=======================================
```

**Display rules:**

- Main quest always appears first, separated from side quests
- Active quests show their objectives with checkboxes
- Completed quests show as a single collapsed line with `[COMPLETED]`
- Failed quests show as a single collapsed line with `[FAILED]` (rare)
- Undiscovered quests do not appear at all
- Objective progress is shown as "X/Y" where Y is the count of required (non-optional) objectives
- Optional objectives are displayed with a `(bonus)` tag

### Quest State Change Notifications

When quest state changes during gameplay, the engine prints a notification:

**Quest discovered:**
```
  -- New Quest: The Hermit's Bargain --
  Bring the hermit a silver mirror in exchange for passage through the grove.
```

**Objective completed:**
```
  -- Quest Updated: The Curse of Thornwall --
  Completed: Complete the Ritual of Fire (2/3)
```

**Quest completed:**
```
  ====================================
  Quest Complete: The Captain's Journal
  You've collected all five pages of the captain's journal.
  +15 points
  ====================================
```

**Notification styling (Rich markup):**
- Quest discovery: `[bold bright_cyan]` for the header, normal text for description
- Objective completion: `[bold bright_cyan]` for header, `[green]` for the completed objective
- Quest completion: `[bold bright_green]` panel with score

### Integration with Score Command

The `score` command's breakdown should show quest-related score entries. Score entries from quest completion use the reason format `quest:<quest_id>` for deduplication.

---

## Schema Design

### New Table: `quests`

Replaces the `lore` table.

```sql
CREATE TABLE IF NOT EXISTS quests (
    id              TEXT PRIMARY KEY,
    name            TEXT    NOT NULL,
    description     TEXT    NOT NULL,
    quest_type      TEXT    NOT NULL,  -- main | side
    status          TEXT    NOT NULL DEFAULT 'undiscovered',
                    -- undiscovered | active | completed | failed
    discovery_flag  TEXT,              -- flag that triggers discovery (NULL = auto-discover at start)
    completion_flag TEXT    NOT NULL,  -- flag set when quest completes (engine checks objectives)
    score_value     INTEGER NOT NULL DEFAULT 0,
    sort_order      INTEGER NOT NULL DEFAULT 0   -- display ordering among side quests
);

CREATE INDEX IF NOT EXISTS idx_quests_status ON quests(status);
CREATE INDEX IF NOT EXISTS idx_quests_type   ON quests(quest_type);
```

### New Table: `quest_objectives`

```sql
CREATE TABLE IF NOT EXISTS quest_objectives (
    id              TEXT PRIMARY KEY,
    quest_id        TEXT    NOT NULL REFERENCES quests(id),
    description     TEXT    NOT NULL,
    completion_flag TEXT    NOT NULL,  -- the flag that marks this objective done
    order_index     INTEGER NOT NULL DEFAULT 0,
    is_optional     INTEGER NOT NULL DEFAULT 0,
    bonus_score     INTEGER NOT NULL DEFAULT 0   -- extra points for optional objectives
);

CREATE INDEX IF NOT EXISTS idx_objectives_quest ON quest_objectives(quest_id);
```

### Field Details

**`quests.id`** -- Unique snake_case identifier. Examples: `main_quest`, `hermits_bargain`, `captains_journal`.

**`quests.name`** -- Player-facing title. Examples: "The Curse of Thornwall", "The Hermit's Bargain".

**`quests.description`** -- 1-3 sentences describing the quest from the player's perspective. Written as if a journal entry or NPC were explaining the task.

**`quests.quest_type`** -- Either `main` or `side`. Exactly one quest must be `main`. The main quest's completion triggers the win condition.

**`quests.status`** -- Runtime state. Initialized to `undiscovered` for most quests. The main quest starts as `active` (engine handles this automatically during `init_player`). The engine updates this field based on flag state.

**`quests.discovery_flag`** -- The flag ID that, when set to `"true"`, transitions the quest from `undiscovered` to `active`. If `NULL`, the quest is discovered automatically at game start (used for the main quest).

**`quests.completion_flag`** -- A flag the engine sets when all required objectives are complete. This flag can be referenced by win conditions, other quest objectives, NPC dialogue gates, or lock conditions. The engine manages this flag automatically -- the generator creates the flag but the engine sets it.

**`quests.score_value`** -- Points awarded when the quest is completed. Added to score via `add_score_entry` with reason `quest:<quest_id>`.

**`quests.sort_order`** -- Controls display order in the quest log. Lower numbers appear first. The main quest always appears first regardless of sort_order.

**`quest_objectives.id`** -- Unique snake_case identifier. Examples: `main_ritual_fire`, `journal_page_1`.

**`quest_objectives.quest_id`** -- FK to `quests.id`.

**`quest_objectives.description`** -- Short phrase shown in the quest log. Examples: "Complete the Ritual of Fire", "Find journal page 1".

**`quest_objectives.completion_flag`** -- The flag that marks this objective done. The objective is complete when `flags.value = 'true'` for this flag ID. These flags are typically set by command effects, dialogue effects, or puzzle completion -- the quest system reads them, never writes them (except for the quest-level completion flag).

**`quest_objectives.order_index`** -- Display order within the quest. Lower numbers appear first.

**`quest_objectives.is_optional`** -- `0` = required for quest completion, `1` = optional bonus.

**`quest_objectives.bonus_score`** -- Extra points for completing an optional objective (on top of the quest's base score_value). Only relevant when `is_optional = 1`.

### Removed Table: `lore`

The `lore` table, its indices, and all related GameDB methods are removed. The `insert_lore`, `discover_lore`, `get_discovered_lore`, `get_lore_in_room`, `get_lore_for_item`, and `get_lore` methods are replaced with quest-specific methods.

### Relationship Map (Updated)

```
rooms ──< exits ──< locks
  |                   |
  |                   |── references items (key_item_id)
  |                   └── references puzzles (puzzle_id)
  |
  |──< items (room_id = current location)
  |──< npcs (room_id = current location)
  └──< commands (context_room_id, optional)

items ──< commands (references in preconditions/effects)

npcs ──< dialogue (npc_id)

puzzles ──< commands (puzzle_id)

flags ──< referenced by commands, locks, puzzles, dialogue, quests
      ──< quest_objectives.completion_flag
      ──< quests.discovery_flag
      ──< quests.completion_flag

quests ──< quest_objectives (quest_id)
```

The key insight: quests observe flag state but do not create new gating mechanisms. Flags are still the universal state glue. Quests simply provide a player-facing view of flag progress.

---

## Engine Changes

### New GameDB Methods

```python
# ---- Quest queries ----

def get_all_quests(self) -> list[dict]:
    """Return all quests ordered by type (main first) then sort_order."""

def get_quest(self, quest_id: str) -> dict | None:
    """Return a single quest by id."""

def get_active_quests(self) -> list[dict]:
    """Return quests with status = 'active', main quest first."""

def get_completed_quests(self) -> list[dict]:
    """Return quests with status = 'completed'."""

def get_quest_objectives(self, quest_id: str) -> list[dict]:
    """Return all objectives for a quest, ordered by order_index."""

def update_quest_status(self, quest_id: str, status: str) -> None:
    """Set quest status to 'active', 'completed', or 'failed'."""

# ---- Bulk insert (generator) ----

def insert_quest(self, **fields) -> None:
    """Insert a single quest row."""

def insert_quest_objective(self, **fields) -> None:
    """Insert a single quest_objective row."""
```

### Quest State Machine (Engine Logic)

After every command (in the `_tick()` method), the engine runs a quest state check:

```
For each quest in the database:

  IF quest.status == 'undiscovered':
    IF quest.discovery_flag is NULL:
      -> Set status to 'active' (auto-discover)
    ELIF flag(quest.discovery_flag) == 'true':
      -> Set status to 'active'
      -> Print discovery notification

  IF quest.status == 'active':
    Check all required objectives:
      FOR each objective WHERE is_optional = 0:
        IF flag(objective.completion_flag) == 'true':
          -> Objective is complete
          -> If this is newly complete, print objective notification

      IF all required objectives are complete:
        -> Set quest.status to 'completed'
        -> Set flag(quest.completion_flag) to 'true'
        -> Award quest.score_value via add_score_entry
        -> Award bonus_score for any completed optional objectives
        -> Print quest completion notification
```

This check runs every tick. It is efficient because:
- It queries the quests table once (small -- typically 3-8 quests)
- It checks flags via `has_flag()` which is a single indexed lookup per flag
- Early exit: skip quests that are already `completed` or `failed`

The engine tracks "last known state" for objectives to detect newly-completed objectives (to print notifications). This can be done by comparing the objective's flag state against a cached snapshot, or by adding a `was_complete` column. The simpler approach: check if the quest status just changed to 'completed' this tick by comparing before/after.

Implementation detail: the engine should cache the previous tick's objective states in memory (a `dict[str, bool]`) and compare against current flag states. When a difference is detected, it prints the appropriate notification. This avoids adding runtime columns to the schema.

### New Built-in Command: `quests`

Add to the `main_loop` in `game.py`:

```python
if verb in ("quests", "journal", "quest", "j") and len(tokens) == 1:
    self._show_quests()
    continue  # does not cost a move
```

The `_show_quests()` method renders the quest log as described in the Quest Tracking section above.

### Removed Built-in Command: `lore`

The `lore` command and `_show_lore()` method are removed.

### Updated Help Text

The help text replaces `lore` with `quests`:

```
  quests (j)           -- view your quest log
```

### Updated Examine Handler

The `_handle_examine` method currently checks for lore attached to items. This behavior is removed entirely. No more yellow italic lore text popping up on examine. Items' `examine_description` field is sufficient for embedded narrative and clues.

### New Effect Type: `discover_quest`

Add to the command DSL effect types:

```python
elif effect_type == "discover_quest":
    quest_ref = _substitute_slots(effect["quest"], slots)
    # Set the quest's discovery flag, which the tick handler will pick up
    quest = db.get_quest(quest_ref)
    if quest and quest.get("discovery_flag"):
        db.set_flag(quest["discovery_flag"], "true")
```

This effect lets commands explicitly discover quests. It works by setting the quest's `discovery_flag`, which the tick handler then detects.

Alternatively, since the tick handler already checks `discovery_flag` against flag state, any command that sets the discovery flag (via `set_flag`) will implicitly discover the quest. The `discover_quest` effect is syntactic sugar that makes command intent clearer in the generated data.

### Updated Effect Type: `discover_lore` (Removed)

The `discover_lore` effect type is removed from `commands.py`. Any generated commands that used it should use `print` (for flavor text) or `discover_quest` (for quest discovery) instead.

---

## Generation Pipeline Changes

### Pass 8: Quests (Replaces Lore)

**Produces:** Quest records in the `quests` and `quest_objectives` tables, plus related flags in the `flags` table.

**Reads from previous passes:** World concept (theme, setting, goal), rooms (locations for quest objectives), items (quest-relevant items), NPCs (quest givers), puzzles (objectives that correspond to puzzle solutions), locks (gated areas that quests may reference), commands (existing flag-setting effects the quest objectives can observe), and all flags from prior passes.

**What the LLM prompt should focus on:**

The LLM receives the complete world state from Passes 1-7 and must design quests that:

1. **Create a main quest** that maps to the game's win condition. The main quest's objectives should correspond to the major milestones of the critical path. Its `completion_flag` should be one of (or the last of) the win condition flags.

2. **Create 2-4 side quests** that reward exploration off the critical path. Side quests should use existing items, NPCs, and puzzles that are not part of the critical path (marked `is_optional = 1` on puzzles).

3. **Reference existing flags.** The most important constraint: quest objectives' `completion_flag` values should reference flags that are already set by existing commands, dialogue, or puzzle effects from prior passes. The quest system observes existing state; it does not require new commands to be generated.

4. **Add new flags only for quest-level tracking.** The quest's `completion_flag` and `discovery_flag` are new flags the quest pass creates. Objective completion flags should reuse existing flags wherever possible. If a new flag is needed (rare), the quest pass creates it and documents which existing command or dialogue should set it (this may require a minor update to a prior pass's output, handled by validation).

5. **Write player-facing descriptions.** Quest names and descriptions should be evocative and clear. Objectives should be concrete enough that the player knows what to do but not so specific that they spoil the puzzle. "Solve the fountain's riddle" is good. "Use the moonstone on the fountain" is too specific.

**Prompt structure:**

```
You are designing quests for a Zork-style text adventure.
You have the complete world from prior passes. Your job is to
organize the player's experience into clear objectives.

## World Concept
{concept}

## Rooms
{rooms_summary}

## Items
{items_summary}

## NPCs
{npcs_summary}

## Puzzles
{puzzles_summary}

## Existing Flags (from prior passes)
{flags_summary}

## Existing Commands (flag-setting effects)
{commands_flag_effects_summary}

## Win Conditions
{win_conditions}

## Your Task

### 1. Main Quest
Design exactly ONE main quest. Its objectives should map to the
major milestones on the critical path to winning. The quest's
completion_flag should be the final flag checked by the win
condition (or a new flag that aggregates the win conditions).

Requirements:
- 2-5 objectives that span the critical path
- Each objective's completion_flag MUST reference an existing
  flag from the flags list above
- The quest description should match the game's intro text /
  overall goal
- discovery_flag: null (auto-discovered at game start)
- score_value: 0 (the main quest IS the game; puzzles along
  the way already award score)

### 2. Side Quests
Design 2-4 side quests. Each should:
- Use existing items, NPCs, rooms, and puzzles that are NOT
  on the critical path
- Have 1-3 objectives per quest
- Reference existing flags as objective completion_flags
- Have a clear discovery trigger (an NPC conversation, entering
  a room, examining an item)
- Award 5-20 score points on completion
- Be completable independently of other side quests

### 3. Flags
For each quest, create:
- A completion_flag (e.g., quest_hermits_bargain_complete)
- A discovery_flag for side quests (e.g., quest_hermits_bargain_discovered)
  The discovery_flag should correspond to a flag that is already
  set by an existing command or dialogue. If no existing flag
  fits, create a new one and note which command/dialogue should
  set it.

### Output Format
{json_schema}
```

**JSON output schema:**

```json
{
  "quests": [
    {
      "id": "main_quest",
      "name": "The Curse of Thornwall",
      "description": "Lift the ancient curse by performing the three sacred rituals.",
      "quest_type": "main",
      "discovery_flag": null,
      "completion_flag": "quest_main_complete",
      "score_value": 0,
      "sort_order": 0,
      "objectives": [
        {
          "id": "main_ritual_fire",
          "description": "Complete the Ritual of Fire",
          "completion_flag": "ritual_fire_done",
          "order_index": 0,
          "is_optional": 0,
          "bonus_score": 0
        }
      ]
    }
  ],
  "flags": [
    {
      "id": "quest_main_complete",
      "value": "false",
      "description": "Set by engine when all main quest objectives are complete"
    }
  ]
}
```

**Validation checks:**

- Exactly one quest has `quest_type = "main"`
- Every `completion_flag` in objectives references a flag that exists (either from prior passes or newly created in this pass)
- Every `discovery_flag` (when not null) references a flag that exists
- Every quest has at least one non-optional objective
- No duplicate quest or objective IDs
- Objective completion flags are not duplicated across objectives (one flag = one objective)
- Main quest's `completion_flag` is included in (or triggers) the win conditions
- Side quest score values sum to a reasonable portion of total max_score (15-40%)

---

## Integration with Existing Systems

### Quests and Puzzles

Puzzles are the mechanical implementation. Quests are the narrative wrapper. A puzzle exists whether or not a quest references it. But when a quest objective's `completion_flag` matches the flag set by a `solve_puzzle` effect, the two systems connect naturally.

**Example flow:**
1. The puzzle `moonstone_fountain_puzzle` has a command that, when solved, sets flag `fountain_activated` and triggers `solve_puzzle`.
2. The quest "The Curse of Thornwall" has an objective "Activate the moonstone fountain" with `completion_flag = "fountain_activated"`.
3. When the player solves the puzzle, the flag is set. Next tick, the quest system detects the objective is complete and prints a notification.

No new wiring is needed. The quest system reads what the puzzle system writes.

### Quests and NPCs

NPCs can discover quests (via dialogue that sets a discovery flag) and can be objectives themselves (via dialogue flags or give-item flags).

**Example flow:**
1. NPC "The Hermit" has dialogue that sets flag `met_hermit`.
2. Quest "The Hermit's Bargain" has `discovery_flag = "met_hermit"`.
3. When the player talks to the hermit, the flag is set. Next tick, the quest is discovered.
4. An objective "Bring the silver mirror to the hermit" has `completion_flag = "gave_mirror_to_hermit"`.
5. A command `give mirror to hermit` sets flag `gave_mirror_to_hermit` in its effects.

### Quests and the Command DSL

Commands can trigger quest discovery via the `discover_quest` effect or by setting flags that match a quest's `discovery_flag`. Commands can advance quests by setting flags that match objective `completion_flag` values. No new precondition types are needed.

New effect type added:

| Type | Parameters | Description |
|---|---|---|
| `discover_quest` | `quest` | Set the quest's discovery flag, making it appear in the journal |

### Quests and Flags

Flags remain the universal state glue. The quest system introduces a naming convention for quest-specific flags:

- `quest_<quest_id>_complete` -- set by engine when quest completes
- `quest_<quest_id>_discovered` -- set by commands/dialogue to trigger discovery

Objective completion flags reuse existing flags from the game world (e.g., `fountain_activated`, `guard_convinced`). This avoids flag duplication.

### Quests and the Score System

Quest completion awards score via `add_score_entry` with reason `quest:<quest_id>`. Optional objective bonuses use reason `quest_bonus:<objective_id>`. The score system's deduplication prevents double-scoring.

The main quest awards 0 score by default (the journey is the reward; puzzles along the way already give score). Side quests award 5-20 points.

### Quests and Win Conditions

The main quest's `completion_flag` should be included in the `metadata.win_conditions` array. When the engine's quest tick sets this flag (because all required objectives are complete), the existing win condition check in `check_end_conditions()` detects it and triggers the victory sequence.

This creates a clean chain:
1. Player completes the last puzzle on the critical path
2. Puzzle command sets the final objective's flag
3. Quest tick detects all objectives complete, sets `quest_main_complete`
4. Win condition check detects `quest_main_complete`, triggers victory

---

## Example Quests

For a game set in a castle with a curse theme ("The Silver Stag"):

### Main Quest: The Curse of Thornwall

```json
{
  "id": "main_quest",
  "name": "The Curse of Thornwall",
  "description": "The castle is cursed. Discover the truth about what happened at Thornwall and find a way to lift the curse before it consumes the valley.",
  "quest_type": "main",
  "discovery_flag": null,
  "completion_flag": "quest_main_complete",
  "score_value": 0,
  "sort_order": 0,
  "objectives": [
    {
      "id": "main_enter_keep",
      "description": "Gain entry to the castle keep",
      "completion_flag": "guard_convinced",
      "order_index": 0,
      "is_optional": 0,
      "bonus_score": 0
    },
    {
      "id": "main_find_captain",
      "description": "Find Captain Maren",
      "completion_flag": "spoke_to_captain",
      "order_index": 1,
      "is_optional": 0,
      "bonus_score": 0
    },
    {
      "id": "main_open_sealed_chamber",
      "description": "Open the sealed chamber beneath the castle",
      "completion_flag": "fountain_activated",
      "order_index": 2,
      "is_optional": 0,
      "bonus_score": 0
    },
    {
      "id": "main_reveal_truth",
      "description": "Discover the truth about the Battle of Thornwall",
      "completion_flag": "truth_revealed",
      "order_index": 3,
      "is_optional": 0,
      "bonus_score": 0
    }
  ]
}
```

### Side Quest: The Captain's Journal

```json
{
  "id": "captains_journal",
  "name": "The Captain's Journal",
  "description": "Torn pages from Captain Aldric's personal journal are scattered throughout the castle. Collecting them all may reveal what really happened during the siege.",
  "quest_type": "side",
  "discovery_flag": "found_first_journal_page",
  "completion_flag": "quest_captains_journal_complete",
  "score_value": 15,
  "sort_order": 1,
  "objectives": [
    {
      "id": "journal_page_1",
      "description": "Find the first journal page",
      "completion_flag": "found_first_journal_page",
      "order_index": 0,
      "is_optional": 0,
      "bonus_score": 0
    },
    {
      "id": "journal_page_2",
      "description": "Find the second journal page",
      "completion_flag": "has_journal_page_2",
      "order_index": 1,
      "is_optional": 0,
      "bonus_score": 0
    },
    {
      "id": "journal_page_3",
      "description": "Find the third journal page",
      "completion_flag": "has_journal_page_3",
      "order_index": 2,
      "is_optional": 0,
      "bonus_score": 0
    }
  ]
}
```

Note: The first journal page's flag doubles as the discovery flag. Finding the first page both completes objective 1 and discovers the quest. The quest log immediately shows 1/3 progress.

### Side Quest: The Hermit's Bargain

```json
{
  "id": "hermits_bargain",
  "name": "The Hermit's Bargain",
  "description": "The old hermit in the grove knows a shortcut through the castle walls, but he wants something in return -- a silver mirror from the watchtower.",
  "quest_type": "side",
  "discovery_flag": "met_hermit",
  "completion_flag": "quest_hermits_bargain_complete",
  "score_value": 10,
  "sort_order": 2,
  "objectives": [
    {
      "id": "hermit_find_mirror",
      "description": "Find the silver mirror in the watchtower",
      "completion_flag": "has_silver_mirror",
      "order_index": 0,
      "is_optional": 0,
      "bonus_score": 0
    },
    {
      "id": "hermit_deliver_mirror",
      "description": "Bring the silver mirror to the hermit",
      "completion_flag": "gave_mirror_to_hermit",
      "order_index": 1,
      "is_optional": 0,
      "bonus_score": 0
    },
    {
      "id": "hermit_explore_shortcut",
      "description": "Use the shortcut the hermit revealed",
      "completion_flag": "used_hermit_shortcut",
      "order_index": 2,
      "is_optional": 1,
      "bonus_score": 5
    }
  ]
}
```

---

## Max Score Calculation Update

The `metadata.max_score` calculation must be updated to include quest score sources:

```
max_score = sum(puzzle.score_value for all puzzles)
          + sum(quest.score_value for all quests)
          + sum(objective.bonus_score for all optional objectives)
          + sum(command add_score effects)
```

The GDD's guideline that ~50% of score should come from the critical path and ~50% from optional content still applies. Side quest scores are part of the optional 50%.

---

## Migration from Lore

### What Changes

| Before (Lore) | After (Quests) |
|---|---|
| `lore` table | Dropped, replaced by `quests` + `quest_objectives` |
| `lore` command | Replaced by `quests` command |
| `_show_lore()` | Replaced by `_show_quests()` |
| `discover_lore` effect | Replaced by `discover_quest` effect |
| `get_lore_for_item()` in examine handler | Removed entirely |
| Yellow italic lore text on examine | Gone |
| `insert_lore()` | Replaced by `insert_quest()` + `insert_quest_objective()` |
| Lore pass (Pass 8) | Quest pass (Pass 8) |
| Lore tier system (surface/engaged/deep) | Gone |
| Lore score values | Quest score values |

### What Stays the Same

- The flag system is unchanged
- The command DSL is unchanged (one new effect type added)
- Puzzle system is unchanged
- NPC dialogue system is unchanged
- Room descriptions are unchanged
- Item examine descriptions are unchanged (and no longer trigger lore popups)
- The score system is unchanged (quests use `add_score_entry` like everything else)
- Win/lose conditions are unchanged (quests use flags, win conditions check flags)

### What Happens to Flavor Text

The lore system's best content -- evocative historical details, world-building fragments, narrative color -- does not disappear. It moves to where it always should have been:

- **Room descriptions** -- atmospheric details baked into the room prose
- **Item examine descriptions** -- historical context embedded in item inspections
- **NPC dialogue** -- world-building delivered through conversation
- **First-visit text** -- dramatic reveals on room entry

These fields already exist and already work. The lore system was a separate layer trying to add narrative that should have been part of the base content. With the quest system, the LLM's narrative energy goes into quest descriptions and objective text instead of standalone lore fragments.

---

## Generation Quality Checklist (Updated)

Replace the lore-related checks with:

- [ ] Exactly one quest has `quest_type = "main"`
- [ ] Main quest has `discovery_flag = NULL` (auto-discovered)
- [ ] Main quest's `completion_flag` is in `metadata.win_conditions`
- [ ] Every quest has at least one non-optional objective
- [ ] Every objective's `completion_flag` references an existing flag
- [ ] Every quest's `discovery_flag` (when not null) references an existing flag
- [ ] Side quest discovery flags are set by existing commands or dialogue
- [ ] No orphan objectives (every objective belongs to a quest that exists)
- [ ] Score totals are sensible (side quests = 15-40% of optional score budget)
- [ ] Quest descriptions do not spoil puzzle solutions
- [ ] Main quest objectives span the critical path (not clustered in one region)
- [ ] At least 2 side quests exist for medium/large games

---

## GDD Updates Required

The GDD (`docs/game-design/gdd.md`) needs these updates when this design is implemented:

1. **Lore System section** -- Replace entirely with a Quest System section that summarizes this document
2. **Scoring System section** -- Replace "Lore discovered" rows with quest-related score sources
3. **Long-Term Loop** -- Replace "Lore discovery across three tiers" with "Quest progression across main and side objectives"
4. **Core Gameplay Loop** -- Add quest notifications as a feedback mechanism
5. **Information Commands** -- Replace `lore` with `quests` / `journal`
6. **Generation Quality Checklist** -- Replace lore checks with quest checks
7. **What Makes a Good Generated Game > Interconnectedness** -- Replace "every item is useful for a puzzle, a key, a lore carrier, or scenery" with "every item is useful for a puzzle, a key, a quest objective, or scenery"

---

## World Schema Updates Required

The world-schema doc (`docs/game-design/world-schema.md`) needs:

1. **Schema Overview table** -- Replace `lore` row with `quests` and `quest_objectives`
2. **Relationship Map** -- Update to show quest relationships
3. **Table: `lore` section** -- Replace with `Table: quests` and `Table: quest_objectives` sections
4. **Generation Checklist** -- Replace lore checks with quest checks
5. **Content Quality checks** -- Replace "Lore exists at all three tiers" with quest-related checks
