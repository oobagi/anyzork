# Implementation Phases

## Phase 1: Foundation

**Goal:** Project skeleton and database layer — the base everything builds on.

**Tasks:**
- [x] `pyproject.toml` — dependencies, scripts entry point, dev tools
- [x] `.gitignore` — Python, SQLite, env files, .zork games
- [x] Package structure — `anyzork/` with `__init__.py` and subpackage inits
- [x] `anyzork/config.py` — pydantic-settings config (providers, keys, paths)
- [x] `anyzork/db/schema.py` — SQLite schema (all tables from world-schema.md) + GameDB class

**Agents:**
- Software Architect agent → project skeleton, config
- Game Designer agent → database schema (they wrote the world schema doc, they know it best)

**Key docs to reference:**
- `docs/architecture/system-design.md` — component responsibilities
- `docs/game-design/world-schema.md` — all tables and fields
- `docs/architecture/adrs/adr-001-sqlite-game-storage.md` — SQLite rationale
- `docs/providers/integration.md` — config structure

**Done when:** `pip install -e .` works, `GameDB` can create and read a `.zork` file.

---

## Phase 2: Runtime Engine

**Goal:** Deterministic game engine that can play a hand-built game. No LLM needed.

**Tasks:**
- [x] `anyzork/engine/commands.py` — command DSL interpreter (preconditions + effects)
- [x] `anyzork/engine/game.py` — game loop (room display, input parsing, command resolution, state updates)
- [x] `tests/build_test_game.py` + `tests/test_game.zork` — hand-crafted 6-room test game ("The Hollow Lantern")

**Agents:**
- Narrative Designer agent → command DSL interpreter (they wrote the DSL spec)
- Game Designer agent → game loop + state management
- Level Designer agent → hand-crafted test game (room layout, puzzles, items, lore)

**Key docs to reference:**
- `docs/dsl/command-spec.md` — all precondition/effect types, pattern matching
- `docs/game-design/gdd.md` — gameplay loop, player interactions
- `docs/game-design/world-schema.md` — what data the engine reads

**Done when:** We can run the test game from Python, move between rooms, pick up items, solve a puzzle, and win.

---

## Phase 2b: Dynamic Room Descriptions

**Goal:** Room descriptions stay accurate as world state changes. No stale item mentions.

**Problem:** Static room descriptions mention items that may no longer be present (e.g., "A rusty iron key hangs from a hook" persists after the player takes the key).

**Solution:** Each item gets a `room_description` field — a prose sentence describing how it looks *in the room*. The engine appends these dynamically at render time. Base room descriptions never mention takeable items.

**Tasks:**
- [x] `anyzork/db/schema.py` — add `room_description TEXT` column to items table
- [x] `anyzork/engine/game.py` — update `display_room()` to append present items' `room_description` to body text (instead of just listing names)
- [x] `tests/build_test_game.py` — remove item mentions from room descriptions, add `room_description` to each item
- [x] `docs/game-design/world-schema.md` — document the new field and the dynamic description pattern
- [x] Rebuild test game and verify descriptions update when items are taken/dropped

**Agents:**
- Game Designer agent → schema change + engine display logic + test game updates + doc update

**Key principle:** Scenery items (is_takeable=0) can still be mentioned in base room descriptions since they never move. Only takeable/removable items need `room_description`.

---

## Phase 3: CLI

**Goal:** `anyzork play game.zork` works from the terminal with nice output.

**Tasks:**
- [x] `anyzork/cli.py` — wire `play` command to GameEngine
- [x] Built-in engine verbs — `take`/`get`, `drop`, `examine`/`look at`, `open`, `talk to`/`ask`
- [x] Rich output formatting — room descriptions, inventory, score, styled text
- [x] Help system — shows built-in verbs + DSL verbs
- [x] End-to-end test — `anyzork play tests/test_game.zork` plays the full game

**Agents:**
- Software Architect agent → CLI wiring (`cli.py` play command)
- Game Designer agent → built-in engine verbs (take, drop, examine, open, talk)

**Key docs to reference:**
- `docs/architecture/system-design.md` — CLI component responsibilities
- `docs/game-design/gdd.md` — player interactions, information commands

**Done when:** `anyzork play tests/test_game.zork` launches a playable game in the terminal with styled output.

---

## Phase 4: Generation

**Goal:** `anyzork generate "prompt"` creates a playable `.zork` file using an LLM.

**Tasks:**
- [x] `anyzork/generator/providers/base.py` — abstract provider interface
- [x] `anyzork/generator/providers/claude.py` — Anthropic API provider (streaming)
- [x] `anyzork/generator/providers/openai_provider.py` — OpenAI API provider
- [x] `anyzork/generator/providers/gemini.py` — Google GenAI provider
- [x] `anyzork/generator/orchestrator.py` — multi-pass generation coordinator
- [x] `anyzork/generator/passes/` — all 8 passes (concept, rooms, locks, items, npcs, puzzles, commands, lore)
- [x] `anyzork/generator/validator.py` — post-generation consistency checks
- [x] Wire `generate` command into CLI
- [x] End-to-end test — generated "haunted lighthouse" game with 12 rooms, all validation passed

**Agents:**
- Software Architect agent → provider abstraction, orchestrator skeleton
- Game Designer agent → generation pass prompts, validation rules
- Narrative Designer agent → lore pass, command pass (ensuring DSL compliance)
- Level Designer agent → room graph pass, lock/gate pass, spatial flow

**Key docs to reference:**
- `docs/architecture/generation-pipeline.md` — all 9 passes, dependencies, validation
- `docs/providers/integration.md` — provider interface, adding new providers
- `docs/dsl/command-spec.md` — what valid commands look like
- `docs/game-design/world-schema.md` — what the LLM must produce

**Done when:** `anyzork generate "A haunted mansion with a mystery"` produces a playable `.zork` file.

---

## Phase 5: Polish

**Goal:** Narrator mode, seed system, and quality-of-life features.

**Tasks:**
- [x] `anyzork/engine/narrator.py` — optional LLM layer that flavors engine output with prose (read-only, can't mutate state)
- [x] Seed system — pass seeds through to providers, store in game meta, auto-generate if not provided
- [x] `anyzork list` CLI command — list saved games with version/title/date/score
- [x] Game info display — show engine vs save version (outdated warning), seed, date, max score
- [x] Polish pass — Reality Checker audit: 12 fixes (3 critical, 3 high, 6 medium)

**Agents:**
- Narrative Designer agent → narrator mode (prose generation from deterministic output)
- Software Architect agent → seed system, CLI commands
- Reality Checker agent → final review of the whole system

**Key docs to reference:**
- `docs/guides/design-brief.md` — narrator mode concept, seed system
- `docs/architecture/system-design.md` — narrator architecture

- [ ] CLI providers — Claude Code / Codex subprocess provider (deferred from Phase 4)

**Done when:** Full feature set works end-to-end. Reality checker signs off.

---

## Phase 4b: Nested Containers (in progress)

**Goal:** Containers can hold other containers. Whitelists control what fits where.

**Tasks:**
- [x] Design doc — `docs/game-design/nested-containers.md`
- [x] `anyzork/db/schema.py` — `accepts_items` and `reject_message` columns, whitelist + cycle detection in `move_item_to_container`, recursive `remove_item`
- [x] `anyzork/engine/commands.py` — new DSL preconditions (`item_in_container`, `not_item_in_container`, `container_has_contents`, `container_empty`) + `take_item_from_container` effect
- [x] `anyzork/engine/game.py` — `_find_accessible_item` helper, updated `_handle_search`, `_handle_take_from`, `_handle_examine` for nested resolution
- [x] `anyzork/generator/passes/items.py` — update prompt to allow nesting, whitelist guidance
- [x] `anyzork/generator/passes/commands.py` — nesting-aware command generation guidance
- [x] `anyzork/generator/validator.py` — replace "no nesting" rule with cycle/whitelist validation
- [x] New test world — P226 + AR-15 nested weapon systems, replaces old test game

**Agents:**
- Software Architect agent → schema, DSL, engine changes
- Level Designer agent → new test world
- Code Reviewer agent → review all changes

**Key docs to reference:**
- `docs/game-design/nested-containers.md` — full design spec

**Done when:** `put magazine in gun`, `search gun` shows magazine, `put ammo in magazine` works with whitelist enforcement. Test world is playable.

---

## Phase 4c: Contextual Item Descriptions (complete)

**Goal:** Items describe themselves differently based on where they are (home vs dropped).

**Tasks:**
- [x] Design doc at `docs/game-design/contextual-items.md`
- [x] `home_room_id` and `drop_description` columns on items table
- [x] Three-tier engine display logic in `display_room()`
- [x] DSL-first handler chain for `drop`/`put`/`place` (placement triggers)
- [x] Generation pass updates (items.py + commands.py)
- [x] Test game updated with all contextual fields

---

## Phase 5c: Onboarding (complete)

**Goal:** Interactive setup command for first-time users.

**Tasks:**
- [x] `anyzork init` command — provider selection, API key entry, connection test, model selection
- [x] Save config to `~/.anyzork/config.toml` (preserves existing keys)
- [x] `anyzork config` — view current settings with source provenance
- [x] Config file loaded by `Config` class alongside env vars (load order: defaults → toml → .env → env vars → CLI)
- [x] Rich prompts with provider-specific key URLs and connection validation

---

## Phase 5d: UX Polish

**Goal:** Small quality-of-life touches for the play experience.

**Tasks:**
- [x] Intro shortcut bar on game start — `[I]nventory  [J]ournal  [L]ook  [H]elp`
- [x] Contextual hint — first "I don't understand that" includes "Type 'help' for available commands."
- [x] Clean input prompt — `> ` chevron without colon

---

## Phase 5e: Trigger/Event System

**Goal:** Reactive side effects that fire automatically on game state changes, not player input.

**Problem:** The DSL only fires on player-typed commands. There's no way to say "when X happens, do Y" — e.g., dialogue node spawns an item, entering a room triggers NPC dialogue, setting a flag unlocks a door.

**Examples:**
- Dialogue node reached → spawn item to inventory
- Player enters a room → NPC says something
- Flag gets set → unlock door, spawn item, NPC reacts
- Player attacks something → nearby NPC responds

**Tasks:**
- [ ] Design doc
- [ ] Schema: triggers table (event_type, conditions, effects)
- [ ] Engine: trigger evaluation in `_tick()` and event hooks
- [ ] Generation: LLM generates triggers alongside commands
- [ ] Test world: fix crate key spawn via trigger, add room-enter events

---

## Phase 6: Combat

**Goal:** Deterministic turn-based combat with equip slots and weakness system.

**Tasks:**
- [ ] Design doc at `docs/game-design/combat-system.md`
- [ ] Two equip slots (weapon, armor)
- [ ] Turn-based combat loop
- [ ] Weakness/resistance system (no RNG)

---

## Phase 5b: Item Dynamics (unified)

**Goal:** Unifies interaction matrix, item states, consumables, and realism into one system.

**Design doc:** `docs/game-design/item-dynamics.md`

**Sub-systems:**
- **Item States** — toggleable on/off (flashlights, radios, lanterns), `use {item}` / `turn on/off`
- **Interaction Matrix** — tag-based category responses (shoot any NPC/object, illuminate dark rooms)
- **Consumables & Quantities** — ammo counts, battery charges, depletion on use
- **Realism Dial** — `--realism low/medium/high` generation setting
- **Dark Rooms** — `is_dark` + light source check in engine

**Tasks:**
- [x] Design doc — `docs/game-design/item-dynamics.md`
- [x] Schema changes (item states, tags, quantities, interaction responses table)
- [x] DSL extensions (has_quantity, consume_quantity, restore_quantity, set_toggle_state)
- [x] Engine: toggle handler, turn on/off, interaction matrix resolver, dark room check, quantity/state display
- [x] Generation: interactions pass, realism-aware prompts, item tags, NPC categories
- [x] Test world: flashlight + batteries, dark bunker room, interaction responses, weapon tags
- [x] CLI: --realism flag on generate, --provider/--model on play
