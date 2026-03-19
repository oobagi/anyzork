# DSL Simplification: Built-in Engine Verbs vs. Generated Commands

**Status**: Proposal
**Author**: GameDesigner Agent
**Date**: 2025-03-18
**Scope**: Reduce LLM-generated DSL command boilerplate without losing custom messages

---

## 1. Problem Statement

The LLM currently generates ~20+ DSL commands per game. Many follow predictable, repetitive patterns that the engine already has enough schema data to handle natively. This creates three costs:

1. **Generation tokens** -- each DSL command is a JSON blob the LLM must author. Boilerplate commands waste context window and increase generation time.
2. **Generation errors** -- the more commands the LLM writes, the more chances for malformed JSON, wrong item IDs, missing preconditions, or inconsistent flag names.
3. **Maintenance surface** -- every DSL command is a moving part. Fewer commands = fewer things to break.

The goal is to identify which patterns should become built-in engine behaviors (using data already in the schema) and which should remain DSL commands because they encode genuinely unique interactions.

---

## 2. Full Command Audit: Legacy Test Game

This section audits an older hand-authored test game that predates the current
single human-testing world. It remains useful as historical analysis of DSL
shape, but it should not be treated as the current fixture source of truth.

### 2.1 Command Inventory

| # | Command ID | Verb | Pattern | Category | Rationale |
|---|-----------|------|---------|----------|-----------|
| 1 | `use_apartment_key` | use | `use apartment key on door` | BOILERPLATE | Key-on-lock. Locks table has `key_item_id`, `unlock_message`, `consume_key`. |
| 2 | `unlock_apartment_door` | unlock | `unlock door` | BOILERPLATE | Synonym of #1. The built-in `unlock` verb already tries locks; it just needs to be smarter. |
| 3 | `examine_window_reveal` | look | `look at {target}` | UNIQUE | Examining an item triggers reveal_exit + solve_puzzle. This is a discovery interaction -- the "examine" itself has side effects beyond showing text. |
| 4 | `examine_window_after` | look | `look at {target}` | BOILERPLATE | "Already done" variant. After the window flag is set, this just shows text. Could be handled by a state-aware `examine_description` field. |
| 5 | `pull_trunk_release` | pull | `pull {target}` | UNIQUE | Pulling a lever opens a container in the same room. This is a multi-object interaction (lever affects trunk). Genuinely custom. |
| 6 | `pull_trunk_already` | pull | `pull {target}` | BOILERPLATE | "Already done" variant. Just prints "the trunk is already open." |
| 7 | `pry_glovebox` | use | `use {item} on {target}` | SEMI-BOILERPLATE | Tool-on-locked-container. Similar to key-on-lock but the tool (crowbar) is not consumed and the lock is on a container, not an exit. Custom message matters. |
| 8 | `pry_glovebox_alt` | pry | `pry {target}` | BOILERPLATE | Verb synonym of #7. Identical preconditions and effects with a different verb. |
| 9 | `read_registration` | read | `read {target}` | SEMI-BOILERPLATE | Reading an item to discover lore and set a flag. The core action is "show text + discover lore," which is almost identical to examine with lore discovery (which the engine already handles). |
| 10 | `cut_chain` | use | `use bolt cutters on chain` | SEMI-BOILERPLATE | Tool-on-lock. The chain is a lock entity. Bolt cutters are the key. This follows the key-on-lock pattern with a tool twist. |
| 11 | `cut_chain_alt` | cut | `cut chain` | BOILERPLATE | Verb synonym of #10. |
| 12 | `search_counter` | search | `search {target}` | UNIQUE | Searching spawns a hidden item. The counter is not a container -- this is a custom "search reveals hidden thing" interaction. |
| 13 | `look_under_counter` | look | `look under {target}` | BOILERPLATE | Verb synonym of #12. Same effects, different phrasing. |
| 14 | `fuel_truck` | use | `use gas can on truck` | UNIQUE | Custom multi-step puzzle. Consuming an item on a non-lock target, setting a progression flag. No schema data could predict this. |
| 15 | `fuel_truck_alt` | pour | `pour {item}` | BOILERPLATE | Verb synonym of #14. |
| 16 | `start_truck` | use | `use truck keys on truck` | UNIQUE | Win condition trigger. Using an item when specific flags are set triggers victory. Completely game-specific. |
| 17 | `start_truck_no_fuel` | use | `use truck keys on truck` | UNIQUE | Attempted win without prerequisite. Custom feedback for a specific game state. |
| 18 | `start_truck_verb` | start | `start truck` | BOILERPLATE | Verb synonym of #16. |
| 19 | `attack_zombie_bat` | hit | `hit {target}` | UNIQUE | Weapon-specific combat with custom message. Needs DSL until combat system exists. |
| 20 | `attack_zombie_crowbar` | hit | `hit {target}` | UNIQUE | Different weapon, different message, different priority. |
| 21 | `attack_zombie_knife` | hit | `hit {target}` | UNIQUE | Different weapon, takes damage. Mechanically distinct. |
| 22 | `attack_zombie_verb` | attack | `attack {target}` | BOILERPLATE | Verb synonym of #19-21 (generic fallback). |
| 23 | `use_bandages` | use | `use bandages` | SEMI-BOILERPLATE | Consumable use: remove item, heal, print message. Pattern is "use consumable for effect." |
| 24 | `use_painkillers` | use | `use painkillers` | SEMI-BOILERPLATE | Identical pattern to #23 with different item and values. |
| 25 | `read_bloody_note` | read | `read {target}` | SEMI-BOILERPLATE | Read an item, discover lore, print text. Same pattern as #9. |
| 26 | `read_torn_map` | read | `read {target}` | SEMI-BOILERPLATE | Same pattern again. |
| 27 | `ask_maria_zombies` | ask | `ask {npc} about zombies` | BOILERPLATE | NPC topic question. The dialogue system already handles `ask {npc} about {topic}` as a built-in verb with flag-gated dialogue. This DSL command duplicates that. |
| 28 | `ask_maria_station` | ask | `ask {npc} about gas station` | BOILERPLATE | Same as #27. Dialogue table + lore trigger already exists. |

### 2.2 Summary Counts

| Category | Count | Commands |
|----------|-------|----------|
| **UNIQUE** | 9 | #3, #5, #12, #14, #16, #17, #19, #20, #21 |
| **SEMI-BOILERPLATE** | 6 | #7, #9, #10, #23, #24, #25, #26 |
| **BOILERPLATE** | 13 | #1, #2, #4, #6, #8, #11, #13, #15, #18, #22, #27, #28 |

That is **13 pure boilerplate** and **6 semi-boilerplate** out of 28 commands. If the engine handled these natively, the LLM would only need to generate **9 commands** -- a **68% reduction**.

---

## 3. Pattern Analysis and Recommendations

### 3.1 Pattern: Key-on-Lock (use {key} on {door/container})

**Affected commands**: #1, #2, #10, #11

**Current behavior**: The LLM generates a DSL command for every key+lock pair. Each command hardcodes the item ID, lock ID, room, flag, unlock message, score, and key consumption.

**What the schema already knows**:
- `locks.key_item_id` -- which item is the key
- `locks.consume_key` -- whether the key is consumed
- `locks.unlock_message` -- what to print on success
- `locks.locked_message` -- what to print on failure
- `locks.target_exit_id` -- which exit to unlock
- The exit's room can be inferred from `exits.from_room_id`

**What the engine already does**: The built-in `open` and `unlock` verbs in `game.py` (lines 746-855) already check if the player has the key item and unlocks the lock. The `_try_unlock` method handles key checking, key consumption, and message display.

**The gap**: The built-in `open`/`unlock` verbs only respond to `open {direction}` or `unlock {direction}`. They do not respond to `use {key} on {door}`. The player must know to type `open south` or `unlock door` -- they cannot say `use apartment key on door`.

**Recommendation**: Extend the engine to recognize `use {item} on {target}` as a lock-interaction attempt when:
1. The `{target}` resolves to a direction, exit, or lock description.
2. The `{item}` resolves to a `key_item_id` in the locks table.

The engine performs the unlock using existing schema data and prints the `unlock_message`. No DSL command needed.

**Custom message preservation**: The `unlock_message` field in the locks table already stores the custom message. The current built-in `_try_unlock` already reads and displays it (line 838-842). No change needed.

**Score**: Lock unlocks that should award points could use a new `score_value` field on the locks table, or the engine could just not award score for lock-based unlocks (score comes from puzzle completion instead).

### 3.2 Pattern: Verb Synonyms

**Affected commands**: #2, #8, #11, #13, #15, #18, #22

**Current behavior**: For every custom interaction, the LLM generates 2-3 additional commands with different verb/pattern combos that do the exact same thing. Examples:
- `use bolt cutters on chain` / `cut chain` -- same effects
- `use gas can on truck` / `pour gas` -- same effects
- `use crowbar on glovebox` / `pry glovebox` -- same effects
- `use truck keys on truck` / `start truck` -- same effects
- `search counter` / `look under counter` -- same effects

This is pure duplication. 7 commands exist only as verb synonyms.

**Recommendation**: Implement a **verb alias table** in the schema. Each command can register alternative patterns that map to the same command.

```sql
CREATE TABLE IF NOT EXISTS command_aliases (
    id          TEXT PRIMARY KEY,
    command_id  TEXT NOT NULL REFERENCES commands(id),
    pattern     TEXT NOT NULL,
    verb        TEXT NOT NULL
);
```

The LLM generates one canonical command plus zero or more aliases (just a pattern string, no duplicated preconditions/effects). The engine checks aliases during pattern matching and redirects to the canonical command.

Alternatively, the engine could support a `synonyms` JSON array field directly on the commands table:

```json
{
  "id": "cut_chain",
  "verb": "use",
  "pattern": "use bolt cutters on chain",
  "synonyms": ["cut chain", "cut chain with bolt cutters"],
  ...
}
```

The engine would try the canonical pattern first, then fall through to synonym patterns. This keeps everything in one row and avoids a join.

**Estimated savings**: 7 commands eliminated entirely.

### 3.3 Pattern: "Already Done" Variants

**Affected commands**: #4, #6

**Current behavior**: The LLM generates a second command for every one-shot action to handle "what if the player tries again." These commands check `has_flag` for the completion flag and print a message like "the trunk is already open" or "the window is already open."

**What the engine could do instead**: When a one-shot command has been executed, the engine currently skips it silently and falls through to "I don't understand." Instead, the engine should:

1. Check if a matching command exists but has `executed = 1` (already done).
2. If so, display the command's **`done_message`** (new field) instead of "I don't understand."

**Schema change**: Add an optional `done_message` column to the commands table.

```sql
ALTER TABLE commands ADD COLUMN done_message TEXT DEFAULT '';
```

When set, the engine prints this message when a one-shot command's pattern matches but it has already been executed. When empty, the engine falls through to other commands or the default failure.

**Estimated savings**: 2 commands eliminated. More importantly, this prevents the LLM from having to generate "already done" pairs for every one-shot command in every game. In a larger game with 30 one-shot actions, that is 30 fewer commands.

### 3.4 Pattern: Read {item} (examine with optional read text)

**Affected commands**: #9, #25, #26

**Current behavior**: The LLM generates `read {target}` commands that print text, sometimes set flags, and sometimes award score. Each is a one-shot DSL command.

**What the engine already does**: The built-in `examine` verb already resolves room and inventory items cleanly. Items also have a `read_description` field for cases where "read" should surface different text than ordinary examination.

**The gap**: `read` is not mapped to `examine`. The engine treats `read {item}` as an unknown verb and falls through to DSL resolution.

**Recommendation**: Map `read` as a synonym for `examine` in the engine's built-in verb handling. When the player types `read bloody note`, the engine runs `_handle_examine("bloody note", room_id)`.

For items that should show different text when read vs. examined (e.g., a book's `examine_description` says "A leather-bound journal" but reading it reveals the contents), use the existing `read_description` field on the items table.

```sql
ALTER TABLE items ADD COLUMN read_description TEXT;
```

Engine logic: when the verb is `read`, check `read_description` first. If present, display it. If absent, fall through to `examine_description`.

**Score on read**: If a readable item should award score or progress a quest, that should happen through an explicit command effect, quest flag, or trigger rather than a hidden lore system.

**Flag on read**: The `note_read` flag in the test game is used by other commands to gate content. That should stay in the DSL or move to a trigger, because read-driven flag setting is world-specific game logic.

**Estimated savings**: 3 commands eliminated (the three `read` commands). In larger games with many readable items, this could eliminate 5-10 commands.

### 3.5 Pattern: Consumable Item Use (use {item} for healing/buff)

**Affected commands**: #23, #24

**Current behavior**: Each consumable item gets a DSL command: check `has_item`, remove item, apply effect (change_health), set flag, print message.

**Recommendation**: Add optional `use_effect` and `use_message` fields to the items table.

```sql
ALTER TABLE items ADD COLUMN use_effect TEXT;    -- JSON: {"type": "change_health", "amount": 25}
ALTER TABLE items ADD COLUMN use_message TEXT;   -- "You bandage your wounds..."
```

When the player types `use {item}` and the item is in inventory:
1. If `use_effect` is set, apply it.
2. If `is_consumed_on_use` is set, remove the item.
3. Print `use_message` or a generic "Used."

The engine already has `is_consumed_on_use` on the items table -- it just is not wired up to anything yet.

**Limitation**: This only works for simple single-effect consumables. Items with complex effects (multiple effects, conditional logic) still need DSL commands. The items in the test game (#23, #24) are simple consumables and fit this pattern.

**Score on use**: Add an optional `use_score` integer field, or let the LLM attach a score via lore discovery.

**Estimated savings**: 2 commands eliminated per game. In games with many consumables (potions, food, ammo), this could save 5-10 commands.

### 3.6 Pattern: Ask NPC About {topic} (with flags/score)

**Affected commands**: #27, #28

**Current behavior**: The LLM generates DSL commands for `ask {npc} about {topic}` that check NPC presence, check flags, set flags, and print dialogue.

**What the engine already does**: The built-in `ask` verb (game.py lines 304-313) already handles `ask {npc} about {topic}`. It calls `_handle_ask`, which:
1. Finds the NPC in the room.
2. Queries dialogue entries filtered by topic.
3. Picks the highest-priority undelivered dialogue whose required flags are met.
4. Prints it and sets any `set_flags` from the dialogue entry.

**The gap**: The dialogue system does not directly award score. The DSL commands for `ask_maria_zombies` and `ask_maria_station` mainly add `add_score`, while `set_flag` is already covered by dialogue fields.

**Recommendation**: Extend dialogue delivery with optional score support if this pattern remains common.

```sql
ALTER TABLE dialogue ADD COLUMN score_value INTEGER DEFAULT 0;
```

When a dialogue line is delivered:
1. If `score_value > 0`, award that many points.
2. Set any flags from `set_flags` (already implemented).

This makes the dialogue system more self-contained for the common "ask NPC, learn something important, get points" pattern.

**Estimated savings**: 2 commands eliminated. In games with 5+ NPC topic interactions, this could save 5-15 commands.

### 3.7 Pattern: Tool-on-Locked-Container (use {tool} on {container})

**Affected commands**: #7, #8

**Current behavior**: The glovebox is a locked container. The crowbar is the "key." The DSL command checks the player has the crowbar, opens the container, sets a flag, and prints a message.

**What the schema lacks**: Containers have `is_locked` but no `key_item_id`. Only exit locks have key references. There is no way for the engine to know that the crowbar opens the glovebox without a DSL command (or schema change).

**Recommendation**: Add `key_item_id`, `unlock_message`, and `consume_key` fields to the items table (for containers).

```sql
ALTER TABLE items ADD COLUMN key_item_id TEXT REFERENCES items(id);
ALTER TABLE items ADD COLUMN unlock_message TEXT;
ALTER TABLE items ADD COLUMN consume_key INTEGER NOT NULL DEFAULT 0;
```

When the player types `use {item} on {container}`:
1. If `{container}` is a locked container with a `key_item_id` matching `{item}`, unlock it.
2. Print the container's `unlock_message` or a default.
3. If `consume_key`, remove the key item.

The built-in `open` verb should also be extended: when the player types `open glovebox` and the glovebox is locked but they have the key item, auto-unlock it (same logic as the exit lock `_try_unlock`).

**Estimated savings**: 2 commands eliminated (the tool-on-container pair). This pattern appears in every game with locked containers.

---

## 4. Proposed Engine Changes

### 4.1 Built-in `use {item} on {target}` Handler

Add a new built-in handler in the `main_loop` method that intercepts `use {item} on {target}` before falling through to DSL resolution.

**Logic**:
1. Parse the input into `item_name` and `target_name`.
2. Find `item` in inventory.
3. Try to resolve `target` as:
   - a. A locked exit (by direction, description, or lock description) whose `key_item_id` matches the item -> unlock the exit.
   - b. A locked container in the room whose `key_item_id` matches the item -> unlock and open the container.
4. If neither matches, fall through to DSL resolution.

This preserves DSL override capability: if a DSL command matches `use {item} on {target}` with higher specificity (hardcoded item/target names), it will be checked first by the DSL resolver. The built-in only fires when no DSL command matches.

**Wait -- order matters.** Currently, built-in verbs are checked BEFORE DSL commands (game.py lines 159-341). If we add a built-in `use` handler, it will intercept ALL `use X on Y` inputs before DSL gets a chance. This would prevent DSL commands like `fuel_truck` (#14) and `start_truck` (#16) from ever firing.

**Resolution**: Reverse the priority for `use`. The engine should check DSL commands FIRST for `use`, then fall back to the built-in. Alternatively, restructure the dispatch so that:
1. Built-in system verbs (quit, look, inventory, score, help, save, lore) run first.
2. DSL commands run second.
3. Built-in interaction verbs (take, drop, examine, open, unlock, search, talk, ask, **use**) run as **fallbacks** if no DSL command matched.

This is the cleanest approach and it applies to all interaction verbs, not just `use`. It means:
- DSL always gets first crack at the input (custom behavior wins).
- Built-ins handle the boring default cases that no DSL command covers.
- The LLM only generates DSL for interactions that deviate from default behavior.

### 4.2 Built-in `read` as Examine Synonym

Map `read` to `_handle_examine` with a `read_description` field fallback. Minimal change -- just add a verb check in the main loop and a field lookup in `_handle_examine`.

### 4.3 Built-in Consumable Use

When `use {item}` matches an inventory item with `use_effect` set, apply the effect without needing a DSL command.

### 4.4 Verb Alias System

Add a `synonyms` JSON field to the commands table. The engine checks synonyms during pattern matching. The LLM generates one command with optional synonyms instead of N duplicate commands.

### 4.5 Done-Message for One-Shot Commands

Add `done_message` to the commands table. When a one-shot command has been executed, print the done message instead of "I don't understand."

---

## 5. Dispatch Order Redesign

This is the highest-impact change and the prerequisite for everything else. The current order is:

```
1. System verbs (quit, look, inventory, score, help, save, lore)
2. Interaction verbs (take, drop, examine, open, unlock, search, put, talk, ask)
3. Movement (directions)
4. DSL commands (resolve_command)
5. "I don't understand"
```

The proposed order is:

```
1. System verbs (quit, look-bare, inventory, score, help, save, lore)
2. Movement (directions)
3. DSL commands (resolve_command) -- custom behavior checked first
4. Built-in interaction verbs (take, drop, examine/read, open, unlock, search,
   put, talk, ask, use) -- default behavior as fallback
5. "I don't understand"
```

**Why DSL before built-ins**: The LLM's generated commands represent the game designer's intent. If the designer wrote a specific `use crowbar on glovebox` command with a custom message and effects, that should take priority over the engine's generic "use key on lock" handler. The built-in only fires when no DSL command claims the input.

**Risk**: Built-in verbs like `take` and `drop` currently handle edge cases well (checking takeability, container contents, "you're already carrying that"). If DSL runs first, a malformed DSL command could intercept `take sword` and do something wrong. Mitigation: built-in verbs for `take`, `drop`, `examine`, `open`, `search`, `talk`, and `ask` are robust and well-tested. They should remain as fallbacks. Only add `use` and `read` as new built-in fallbacks.

**Refinement**: Instead of moving ALL interaction verbs after DSL, we could be selective:

```
1. System verbs
2. Movement
3. Built-in take/drop/examine/open/unlock/search/put/talk/ask (these are well-tested)
4. DSL commands
5. Built-in use/read (new fallback verbs)
6. "I don't understand"
```

But this creates a confusing two-tier system. A cleaner approach:

**Recommended approach**: Keep the current dispatch order but add a **second DSL pass** for verbs that have built-in handlers. Specifically:

```
1. System verbs
2. DSL commands (checked first for ALL verbs)
3. Built-in interaction verbs (fallback)
4. Movement
5. "I don't understand"
```

This means DSL always gets priority. If no DSL command matches, the engine tries built-in handlers. If no built-in matches, it tries movement. This is the simplest mental model: "DSL overrides everything."

---

## 6. Schema Changes Summary

### 6.1 Items Table

| New Column | Type | Default | Purpose |
|-----------|------|---------|---------|
| `read_description` | TEXT | NULL | Text displayed on `read` (falls back to `examine_description`) |
| `use_effect` | TEXT (JSON) | NULL | Effect applied on `use {item}` (e.g., `{"type":"change_health","amount":25}`) |
| `use_message` | TEXT | NULL | Message printed on `use {item}` |
| `use_score` | INTEGER | 0 | Score awarded on `use {item}` |
| `key_item_id` | TEXT FK | NULL | For locked containers: which item unlocks them |
| `unlock_message` | TEXT | NULL | For locked containers: message on unlock |
| `consume_key` | INTEGER | 0 | For locked containers: whether to consume the key item |

### 6.2 Commands Table

| New Column | Type | Default | Purpose |
|-----------|------|---------|---------|
| `done_message` | TEXT | '' | Message shown when a one-shot command's pattern matches after execution |
| `synonyms` | TEXT (JSON) | '[]' | Alternative patterns that resolve to this command |

### 6.3 Dialogue Table

| New Column | Type | Default | Purpose |
|-----------|------|---------|---------|
| `lore_id` | TEXT FK | NULL | Lore entry to discover when this dialogue line is delivered |
| `score_value` | INTEGER | 0 | Score awarded when this dialogue line is delivered |

### 6.4 Lore Table

| New Column | Type | Default | Purpose |
|-----------|------|---------|---------|
| `set_flags` | TEXT (JSON) | NULL | Flags to set when this lore entry is discovered |

---

## 7. Impact Analysis

### 7.1 Command Reduction Estimate (Dead City Test Game)

| Pattern | Commands Eliminated | Remains as DSL |
|---------|-------------------|----------------|
| Key-on-lock (exit) | 2 (#1, #2) | 0 |
| Key-on-lock (container) | 2 (#7, #8) | 0 |
| Tool-on-lock (chain) | 2 (#10, #11) | 0 |
| Verb synonyms (other) | 3 (#13, #15, #18) | 0 |
| Verb synonym (attack) | 1 (#22) | 0 |
| Already-done variants | 2 (#4, #6) | 0 |
| Read items | 3 (#9, #25, #26) | 0 |
| Consumable use | 2 (#23, #24) | 0 |
| Ask NPC about topic | 2 (#27, #28) | 0 |
| **Total eliminated** | **19** | |
| **Remaining DSL** | | **9** |

**Reduction: 19 of 28 commands eliminated (68%).**

The 9 remaining DSL commands are genuinely unique interactions that cannot be derived from schema data:

1. `examine_window_reveal` -- examine triggers exit reveal + puzzle solve
2. `pull_trunk_release` -- lever opens container in same room
3. `search_counter` -- search spawns hidden item
4. `fuel_truck` -- use consumable on non-lock target, set progression flag
5. `start_truck` -- win condition trigger
6. `start_truck_no_fuel` -- custom feedback for specific game state
7. `attack_zombie_bat` -- weapon-specific combat
8. `attack_zombie_crowbar` -- weapon-specific combat
9. `attack_zombie_knife` -- weapon-specific combat with damage

### 7.2 Token Savings Estimate

Each DSL command in the test game averages ~15 lines of Python / ~300 tokens of JSON when generated by the LLM. Eliminating 19 commands saves approximately **5,700 tokens per game generation** in output alone. Prompt tokens saved (fewer examples, shorter instructions) could double that.

### 7.3 Generation Error Reduction

The most common generation errors in DSL commands are:
- Wrong item/lock ID references (typos, mismatched names)
- Missing or incorrect precondition flags
- Duplicated flag names between synonym commands
- Inconsistent messages between a command and its synonym

All 13 pure boilerplate commands and their 6 semi-boilerplate cousins are eliminated from the error surface. The LLM only generates commands for interactions that require creative judgment -- exactly where LLMs are strongest and errors are most acceptable.

---

## 8. Custom Message Preservation

This is the explicit constraint: reducing boilerplate must NOT lose custom messages. Here is how each pattern preserves them:

| Pattern | Where Custom Messages Live |
|---------|---------------------------|
| Key-on-lock (exit) | `locks.unlock_message` and `locks.locked_message` -- already in schema |
| Key-on-lock (container) | New `items.unlock_message` -- generated once per container |
| Verb synonyms | Eliminated entirely; the canonical command retains its message |
| Already-done variants | New `commands.done_message` -- one field per command |
| Read items | New `items.read_description` -- one field per item |
| Consumable use | New `items.use_message` -- one field per item |
| Ask NPC about topic | `dialogue.content` -- already in schema |

In every case, the custom message is a single string field on an entity the LLM is already generating. The LLM writes the message once, on the entity itself, rather than embedding it inside a DSL command JSON blob. This is actually easier for the LLM -- it is filling in a field on a row it is already creating, not authoring a separate command structure.

---

## 9. Migration Path

### Phase 1: Non-Breaking Additions
1. Add `done_message` and `synonyms` to the commands table.
2. Add `read_description`, `use_effect`, `use_message`, `use_score` to the items table.
3. Add `key_item_id`, `unlock_message`, `consume_key` to the items table (for containers).
4. Add `score_value` to the dialogue table.
5. None of these changes break existing games -- all new columns have defaults.

### Phase 2: Engine Behavior
1. Map `read` to examine with `read_description` fallback.
2. Implement consumable `use {item}` with `use_effect`/`use_message`.
3. Implement `use {item} on {container}` for locked containers with `key_item_id`.
4. Extend `_try_unlock` to handle container locks.
5. Implement `done_message` for executed one-shot commands.
6. Implement synonym pattern matching.
7. Add `score_value` handling to dialogue delivery.

### Phase 3: Dispatch Reorder
1. Move DSL resolution before built-in interaction verbs.
2. Keep system verbs and movement where they are.
3. Test that existing games still work (DSL commands that duplicate built-in behavior will still fire first, which is correct -- they are more specific).

### Phase 4: Generator Update
1. Update generation prompts to use new schema fields instead of generating DSL commands.
2. Remove DSL command templates for boilerplate patterns from the generation pipeline.
3. Update the test game to validate the new approach.

---

## 10. Tradeoffs and Risks

### What We Gain
- **68% fewer generated commands** in the test game.
- **Fewer generation errors** -- the LLM fills in schema fields instead of authoring JSON command structures.
- **Consistent behavior** -- every key-on-lock interaction works the same way, guaranteed by the engine.
- **Easier prompt authoring** -- generation prompts can say "fill in `unlock_message` on the lock" instead of "generate a DSL command with these preconditions and these effects."
- **Smaller .zork files** -- fewer rows in the commands table.

### What We Lose
- **Flexibility for edge cases** -- if a game needs `use key on door` to do something other than unlock (e.g., the key breaks and triggers a different puzzle), the built-in would fire and the DSL override would not. Mitigation: the dispatch reorder (DSL before built-ins) handles this. DSL always wins if present.
- **Engine complexity** -- the engine becomes smarter, which means more code to maintain. Mitigation: the new logic is straightforward if/else chains using existing schema queries. No new algorithms.
- **Schema sprawl** -- 11 new columns across 4 tables. Mitigation: all are optional with sensible defaults. Existing games continue to work unchanged.

### Open Question: Built-in with DSL Override vs. DSL with Built-in Fallback

Both approaches work. The recommendation is **DSL first, built-in fallback**, because:
1. It respects the game designer's explicit intent (DSL commands are specific).
2. It lets the engine be generous with defaults (built-ins handle the 80% case).
3. It is the expected behavior in text adventure engines (custom commands override engine defaults).

The only risk is a DSL command accidentally intercepting an input meant for a built-in. This is a generation quality problem, not an engine design problem, and it exists today regardless.

---

## 11. Changelog

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2025-03-18 | Initial analysis and recommendations |
