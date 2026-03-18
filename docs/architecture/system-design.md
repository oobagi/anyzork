# AnyZork System Architecture

## 1. Architectural Overview

AnyZork is a CLI tool that turns a natural language prompt into a playable Zork-style text adventure. The system is split into two distinct phases with fundamentally different runtime characteristics:

**Phase 1 -- Generation (LLM-powered).** The user provides a prompt like "a haunted lighthouse on a foggy coast." An orchestrator feeds this through a sequence of focused LLM passes, each one building a specific layer of the game world (rooms, items, NPCs, puzzles, commands, lore). Each pass writes structured data into a SQLite database -- the `.zork` file.

**Phase 2 -- Runtime (deterministic).** The game engine reads from the `.zork` file and executes player commands by evaluating DSL rules stored in the database. No LLM is involved. State transitions are explicit, preconditions are checked, effects are applied, and the result is always consistent.

This separation exists for one reason: LLMs are excellent at creative generation and terrible at state management. A real-time LLM game forgets rooms, hallucinates inventory, and drifts on puzzle solutions. By confining the LLM to a one-time generation step and running the actual game deterministically, we get creative worlds without runtime inconsistency.

```
                        GENERATION PHASE                          RUNTIME PHASE
                        ================                          =============

User Prompt ──> CLI ──> Orchestrator ──> Provider ──> LLM        .zork file ──> Game Engine ──> Player
                             │                         │              │              │
                             │         ┌───────────────┘              │              ├── Command Parser
                             │         │                              │              ├── DSL Interpreter
                             ▼         ▼                              │              ├── State Manager
                        Pass 1: World Concept                         │              └── Output Formatter
                        Pass 2: Room Graph                            │                       │
                        Pass 3: Locks & Gates                         │                       ▼
                        Pass 4: Items                                 │              [Optional Narrator]
                        Pass 5: NPCs                                  │                  (LLM layer,
                        Pass 6: Puzzles                               │                   read-only)
                        Pass 7: Commands (DSL)                        │
                        Pass 8: Lore                                  │
                        Pass 9: Validation                            │
                             │                                        │
                             └────── writes to ──────────────────────>│
```

## 2. Component Responsibilities

### 2.1 CLI (`click` + `rich`)

The user-facing entry point. Subcommands include:

- `anyzork generate <prompt>` -- run the generation pipeline, produce a `.zork` file
- `anyzork play <file.zork>` -- launch the game engine against an existing file
- `anyzork info <file.zork>` -- inspect metadata (rooms, items, seed, provider used)

The CLI handles argument parsing, provider selection (via flags or config), progress display during generation (rich progress bars per pass), and the REPL loop during play. It owns no game logic.

### 2.2 Config (`pydantic-settings`)

Configuration is layered: defaults < config file < environment variables < CLI flags. All env vars use the `ANYZORK_` prefix.

Key settings:
- `ANYZORK_PROVIDER` -- which LLM provider to use (`claude`, `openai`, `gemini`)
- `ANYZORK_API_KEY` -- API key for the selected provider
- `ANYZORK_MODEL` -- model override (e.g., `claude-sonnet-4-20250514`, `gpt-4o`)
- `ANYZORK_SEED` -- seed for reproducible generation
- `ANYZORK_NARRATOR` -- enable/disable narrator mode during play (`true`/`false`)
- `ANYZORK_OUTPUT` -- output path for generated `.zork` files

Pydantic validates all config at startup and fails fast with clear error messages (e.g., "ANYZORK_API_KEY is required when using the 'claude' provider").

### 2.3 Database Layer

A thin abstraction over SQLite that provides:

- **Schema management** -- creates tables on new `.zork` files, verifies schema version on existing ones
- **Typed accessors** -- `get_room(id)`, `get_items_in_room(room_id)`, `get_commands_for_verb(verb)`, etc.
- **Write methods for generation** -- `insert_room()`, `insert_item()`, `insert_command()`, each with validation
- **Player state operations** -- `get_player_state()`, `update_player_position()`, `add_to_inventory()`, `set_flag()`
- **Transaction boundaries** -- each generation pass runs inside a single transaction; if it fails, the pass can be retried without corrupting earlier work

The database layer never interprets game logic. It is a persistence boundary: data in, data out.

The `.zork` file schema includes (at minimum):

| Table | Purpose |
|-------|---------|
| `meta` | Game title, description, seed, provider, model, schema version, generation timestamp |
| `rooms` | id, name, description, initial_description, visited flag |
| `exits` | source_room, direction, target_room, locked flag, lock_id |
| `items` | id, name, description, room_id (or null if in inventory), portable flag, hidden flag |
| `npcs` | id, name, description, room_id, dialogue JSON |
| `commands` | id, verb, pattern, preconditions JSON, effects JSON, description |
| `lore` | id, tier (surface/hidden/deep), content, trigger, room_id or item_id |
| `player_state` | current_room, inventory (as item refs), health, score, moves, flags JSON |
| `locks` | id, type (key/puzzle/npc), item_id or puzzle_id, unlocked flag |

Foreign keys enforce referential integrity: every exit references two rooms, every item references a room (or null), every lock references an item or puzzle.

### 2.4 Game Engine

The deterministic runtime. It runs a REPL loop:

1. **Read** -- accept player input (e.g., `go north`, `take lantern`, `use key on door`)
2. **Parse** -- tokenize and match against known command patterns
3. **Evaluate** -- find matching commands in the database, check preconditions against current state
4. **Apply** -- execute effects (move player, add/remove items, set flags, unlock exits, print text, add score)
5. **Output** -- compose the response (room description, action result, status changes)

The engine does not contain game content. It is a generic interpreter for the data and DSL rules stored in the `.zork` file. Swap the file, and you have a completely different game.

Built-in commands that exist regardless of the `.zork` content:
- `look` -- redisplay current room
- `inventory` / `i` -- list carried items
- `go <direction>` / cardinal shortcuts (`n`, `s`, `e`, `w`, `u`, `d`)
- `examine <target>` -- detailed description of item/NPC/feature
- `help` -- list available verbs
- `save` / `load` -- copy/restore the `.zork` file
- `quit`

### 2.5 Command DSL Interpreter

The heart of the game logic system. Each command row in the database is a structured rule:

```json
{
  "verb": "use",
  "pattern": "use {item} on {target}",
  "preconditions": [
    {"type": "player_has", "item": "rusty_key"},
    {"type": "player_in", "room": "dungeon_entrance"},
    {"type": "flag_not_set", "flag": "dungeon_door_unlocked"}
  ],
  "effects": [
    {"type": "remove_item", "item": "rusty_key"},
    {"type": "set_flag", "flag": "dungeon_door_unlocked"},
    {"type": "unlock_exit", "room": "dungeon_entrance", "direction": "north"},
    {"type": "print", "text": "The rusty key crumbles as the lock gives way. The door groans open."},
    {"type": "add_score", "points": 10}
  ]
}
```

**Precondition types** the interpreter understands:
- `player_has` -- player carries the named item
- `player_in` -- player is in the named room
- `flag_set` / `flag_not_set` -- a game flag is or isn't set
- `item_in_room` -- a specific item exists in a specific room
- `npc_in_room` -- a specific NPC is in a specific room
- `exit_locked` / `exit_unlocked` -- an exit's lock state

**Effect types** the interpreter can apply:
- `print` -- display text to the player
- `add_item` / `remove_item` -- modify inventory
- `move_item` -- move an item to a room
- `set_flag` / `clear_flag` -- toggle game flags
- `unlock_exit` / `lock_exit` -- change exit lock state
- `move_player` -- teleport the player to a room
- `add_score` -- increase score
- `reveal_item` -- unhide a hidden item
- `update_description` -- change a room or item description (for state changes like "the door is now open")

This is deliberately a closed set. The LLM cannot invent new effect types -- it can only compose from the vocabulary above. This makes the system safe (no arbitrary code execution) and predictable (every possible state change is enumerable).

Pattern matching uses `{placeholders}` that bind to player input. `use {item} on {target}` matches "use key on door" with `item=key`, `target=door`. The interpreter resolves these bindings against the database to find the actual item and target entities before checking preconditions.

When multiple commands match the same input, the interpreter picks the one whose preconditions are all satisfied. If none match, the player gets a contextual failure message. If multiple match (ambiguity), the most specific pattern wins (most preconditions).

### 2.6 Narrator

An optional, read-only LLM layer that sits between the engine output and the player display.

**Input to narrator:** The raw engine output (structured data -- room name, description, items present, action results, exits, player status).

**Output from narrator:** Prose that conveys the same information with atmosphere and personality.

**What the narrator cannot do:**
- Mutate game state (it has no write access to the database)
- Add items, rooms, or exits that don't exist
- Change the outcome of a command
- Override precondition failures

The narrator receives context about the game's theme, tone, and the current room's lore tier to stay stylistically consistent. It operates on a per-turn basis (no conversation memory beyond the current turn's context window) to prevent drift.

Implementation: a single LLM call per player turn. The prompt includes the game's theme, the current room context, and the deterministic output to be flavored. This uses the same provider abstraction as generation, so the narrator can use a different (possibly cheaper/faster) model than the generator.

If the narrator call fails (network error, rate limit, timeout), the engine's deterministic output is shown directly. The game never blocks on narrator availability.

### 2.7 Generator Orchestrator

Manages the multi-pass generation pipeline. Responsibilities:

1. **Pass sequencing** -- execute passes in dependency order (rooms before exits before locks before items)
2. **Context assembly** -- for each pass, pull the relevant slice of the database built so far and include it in the LLM prompt
3. **Prompt construction** -- each pass has a specialized system prompt that constrains the LLM to produce the right shape of output
4. **Response parsing** -- extract structured data from LLM output (JSON blocks), validate against expected schema
5. **Database writing** -- insert parsed data into the `.zork` file within a transaction
6. **Error handling** -- if a pass fails (bad output, validation error, API error), retry that pass without losing earlier work
7. **Progress reporting** -- emit events the CLI can display as progress bars

The orchestrator does not talk to LLMs directly. It calls the provider abstraction.

**Pass detail:**

| Pass | Input Context | Output | Validation |
|------|---------------|--------|------------|
| 1. World Concept | User prompt | Theme, tone, scale, title, setting description | Schema conformance |
| 2. Room Graph | World concept | Room list with names, descriptions, spatial relationships | Connected graph (no orphan rooms), reasonable count for scale |
| 3. Locks & Gates | Room graph | Lock definitions on specific exits | Every lock has a solution path, no softlocks |
| 4. Items | Rooms + locks | Item list with locations, properties | Key items exist for all locks, no items in nonexistent rooms |
| 5. NPCs | Rooms + items | NPC list with dialogue trees, locations | NPCs in valid rooms, dialogue references valid items/rooms |
| 6. Puzzles | Full world state | Multi-step puzzle definitions | Puzzles are solvable given available items and connections |
| 7. Commands | Full world state | DSL command rules | All precondition/effect references resolve, verbs are consistent |
| 8. Lore | Full world state | Tiered lore entries | Lore attached to valid rooms/items, three tiers populated |
| 9. Validation | Complete database | Error list (or empty) | Cross-referential integrity check across all tables |

Pass 9 is special: it reads the entire database and checks for inconsistencies. If it finds problems (an exit to a nonexistent room, a command referencing a missing item), it reports them. The orchestrator can then re-run the relevant pass with the error context included in the prompt.

### 2.8 Provider Abstraction

A unified interface that hides the differences between API providers.

```
Provider (abstract)
├── ClaudeProvider      -- Anthropic Messages API
├── OpenAIProvider      -- OpenAI Chat Completions API
└── GeminiProvider      -- Google GenAI API
```

**The interface every provider implements:**

- `generate(system_prompt, user_prompt, schema) -> structured_output` -- send a prompt, get back structured data conforming to the given schema
- `narrate(context, engine_output) -> prose` -- flavor deterministic output with prose (used by narrator mode)
- `supports_seed() -> bool` -- whether the provider/model supports deterministic seeding
- `configure(seed, temperature, max_tokens)` -- set generation parameters

All providers make HTTP calls with structured output / tool-use features where available (Claude's tool use, OpenAI's function calling / structured outputs, Gemini's controlled generation). They require the user to set an API key.

The provider abstraction also handles:
- **Rate limiting** -- backoff and retry on 429 responses
- **Timeout** -- configurable per-call timeout with sensible defaults
- **Cost tracking** -- log token counts and estimated cost per pass (for API providers)
- **Seed forwarding** -- pass the seed to the LLM's seed/temperature parameters when supported

## 3. Data Flow

### 3.1 Generation Flow

```
User runs: anyzork generate "a haunted lighthouse on a foggy coast"

1. CLI parses arguments, loads config
2. CLI creates empty .zork file at output path
3. Database layer initializes schema (CREATE TABLE statements)
4. Orchestrator begins pass sequence:

   Pass 1 (World Concept):
     - Orchestrator builds prompt: system="You are designing a text adventure world..." user="a haunted lighthouse on a foggy coast"
     - Provider sends to LLM, receives: {title: "The Beacon", tone: "gothic horror", scale: "medium (15-25 rooms)", ...}
     - Orchestrator validates response shape, writes to meta table

   Pass 2 (Room Graph):
     - Orchestrator reads meta from DB, builds prompt with world concept as context
     - Provider sends to LLM, receives: [{id: "lighthouse_base", name: "Base of the Lighthouse", ...}, ...]
     - Orchestrator validates (connected graph?), writes to rooms + exits tables

   ...passes 3-8 follow the same pattern...

   Pass 9 (Validation):
     - Orchestrator reads entire DB
     - Provider sends to LLM: "Here is the complete game world. Find inconsistencies."
     - If errors found, orchestrator re-runs affected passes with error context
     - If clean, generation is complete

5. CLI reports success: "Generated 'The Beacon' -- 22 rooms, 47 items, 12 puzzles. Saved to the_beacon.zork"
```

### 3.2 Runtime Flow

```
User runs: anyzork play the_beacon.zork

1. CLI opens .zork file, database layer verifies schema version
2. Engine loads initial state (starting room, empty inventory, score 0)
3. Engine displays opening text + starting room description
4. REPL loop:

   Player types: "take lantern"
   a. Parser tokenizes: verb="take", args=["lantern"]
   b. Engine queries DB: items in current room matching "lantern"
   c. Engine finds built-in "take" handler, checks item is portable
   d. Engine applies: move item from room to inventory
   e. Engine composes output: "Taken."
   f. [Narrator mode]: LLM call with output → "You lift the brass lantern from its hook. It's heavier than it looks, and the glass is fogged with age."
   g. Display to player

   Player types: "use key on door"
   a. Parser tokenizes: verb="use", args=["key", "on", "door"]
   b. Engine queries DB: commands with verb="use" matching pattern "use {item} on {target}"
   c. Engine binds: item="key" → resolves to "rusty_key", target="door" → resolves to "dungeon_door"
   d. Engine checks preconditions: player_has("rusty_key")? yes. player_in("dungeon_entrance")? yes. flag_not_set("dungeon_door_unlocked")? yes.
   e. Engine applies effects in order: remove rusty_key, set flag, unlock exit, print text, add 10 to score
   f. Display result

5. On "quit": engine writes final state to player_state table, closes DB
```

### 3.3 Narrator Flow (detail)

```
Engine output (structured):
{
  "room": "lighthouse_base",
  "room_name": "Base of the Lighthouse",
  "description": "A circular stone room. A spiral staircase leads up. A heavy wooden door is to the south.",
  "items": ["brass_lantern", "waterlogged_journal"],
  "exits": {"up": "lighthouse_stairs", "south": "cliff_path"},
  "action_result": null
}

Narrator prompt:
  System: "You are a gothic horror narrator for a text adventure called 'The Beacon'. Your prose is atmospheric and terse. You describe exactly what the engine tells you -- no more, no less. Do not add items, exits, or information not present in the engine output."
  User: [engine output above] + [room lore context] + [recent action context]

Narrator output:
  "The lighthouse's base is a tomb of cold stone, curved walls weeping with condensation. A spiral staircase corkscrews upward into darkness. To the south, a door of salt-warped oak stands slightly ajar, letting in the moan of wind off the cliffs. A brass lantern sits on a ledge, its glass clouded. Beside it, a journal bloated with seawater."

The engine verifies: does the narrator output reference the same exits and items? If it fabricates an exit ("a passage to the east"), the engine strips that line or falls back to raw output. This is a safety net, not a common case.
```

## 4. The Command DSL In Depth

### 4.1 Design Philosophy

The command DSL is the bridge between LLM creativity and deterministic execution. It answers the question: "How does the LLM specify game logic without writing code?"

The answer is a closed vocabulary of preconditions and effects. The LLM composes rules from this vocabulary. The engine interprets them. The vocabulary is fixed at build time -- the LLM cannot extend it.

This is safer than generated code (no eval, no injection, no arbitrary filesystem access) and more reliable than natural language instructions (no ambiguity, no interpretation drift).

### 4.2 Pattern Matching

Command patterns use `{placeholder}` syntax:

| Pattern | Matches | Bindings |
|---------|---------|----------|
| `take {item}` | "take lantern" | item=lantern |
| `use {item} on {target}` | "use key on door" | item=key, target=door |
| `give {item} to {npc}` | "give coin to merchant" | item=coin, npc=merchant |
| `talk to {npc}` | "talk to ghost" | npc=ghost |
| `push {item}` | "push statue" | item=statue |

Bindings are resolved against the database: `item=lantern` is matched to the item row where `name="lantern"` or any alias. Resolution considers the current room first, then inventory, then fails with "You don't see that here."

### 4.3 Precondition Evaluation

All preconditions must be true for the command to fire. Evaluation is short-circuit: the first failing precondition stops evaluation and produces a contextual failure message.

The failure message can be customized per command. If the LLM provides a `fail_message` field, that text is shown. Otherwise, the engine generates a generic message based on the failing precondition type ("You don't have the rusty key." / "You can't do that here.").

### 4.4 Effect Execution

Effects are applied in order. This matters -- `remove_item` before `print` means the item is gone by the time the message displays. The orchestrator's prompt instructs the LLM to order effects logically.

Effects are atomic within a command: if any effect fails to apply (e.g., trying to remove an item the player doesn't have due to a precondition bug), the entire command rolls back. This uses SQLite's transaction support.

## 5. Save/Load, Export, and Seeds

### 5.1 Save and Load

The `.zork` file is the save file. The `player_state` table captures everything needed to resume:
- Current room
- Inventory (list of item IDs)
- Score
- Move count
- Flags (JSON object of all set flags)
- Health (if the game uses it)

"Saving" is a no-op during play -- state is written to the DB after every command. "Save" as a player action copies the `.zork` file to a user-specified path. "Load" replaces the current file with a saved copy.

Multiple save slots are just multiple copies of the file.

### 5.2 Export and Sharing

A `.zork` file is a self-contained SQLite database. It includes:
- All world data (rooms, items, NPCs, commands, lore)
- Player state (can be reset to initial state via a `reset` command)
- Generation metadata (prompt, seed, provider, model, timestamp)

Share it however you want. The recipient just needs AnyZork installed to play it.

### 5.3 Seed System

When the user provides a seed (`--seed 42`), it is:
1. Stored in the `.zork` meta table
2. Passed to the LLM provider's seed/temperature parameters (where supported)
3. Used to make generation deterministic: same prompt + same seed + same provider/model = same world

Not all providers support seeding equally. The system documents this per-provider.

## 6. Error Boundaries

### 6.1 Generation Failures

Each generation pass can fail in several ways:

| Failure | Response |
|---------|----------|
| **API error** (network, auth, rate limit) | Retry with exponential backoff. After N retries, abort with clear error message. |
| **Malformed output** (LLM returns invalid JSON) | Retry the pass with a tighter prompt ("Your previous response was not valid JSON. Return only a JSON array..."). Up to 3 retries per pass. |
| **Schema violation** (output doesn't match expected structure) | Retry with the schema error included in the prompt ("Missing required field 'name' in room object"). |
| **Validation failure** (pass output is internally inconsistent) | Retry with the validation errors as context. |
| **Cross-pass inconsistency** (pass 9 catches problems) | Re-run the specific pass that produced the bad data, with the error context. |

Because each pass writes within a transaction, a failed pass does not corrupt the database. The orchestrator can roll back a pass and retry it, or skip it and report a partial generation.

If generation fails unrecoverably, the partially-generated `.zork` file is kept (not deleted) so the user can inspect it or attempt to resume generation later.

### 6.2 Runtime Failures

The deterministic engine has very few failure modes:

| Failure | Response |
|---------|----------|
| **Corrupt `.zork` file** | Detected at load time via schema version check and integrity pragma. Clear error, refuse to load. |
| **Missing command match** | "I don't understand that." (not a crash, just a no-op.) |
| **Narrator API failure** | Fall back to raw deterministic output. Game continues. |
| **Impossible state** (precondition passes but effect fails) | Transaction rollback for that command. Log the error. Display generic failure message. |

### 6.3 Validation Pass Detail

Pass 9 checks:

- **Spatial integrity**: every exit's target room exists. Every exit has a reverse (or is explicitly one-way). The room graph is connected (no unreachable rooms).
- **Lock solvability**: every locked exit has a corresponding key item, puzzle solution, or NPC interaction that can unlock it. The solution is reachable before the lock (no chicken-and-egg).
- **Item consistency**: every item referenced in a command exists in the items table. No item is referenced as a key for a lock that doesn't exist.
- **Command completeness**: the game is winnable. There exists a path from the starting room to the end state that satisfies all required puzzles.
- **NPC validity**: NPCs are in rooms that exist. Dialogue doesn't reference nonexistent items or rooms.
- **Lore coverage**: lore entries reference valid rooms or items. All three tiers (surface, hidden, deep) are populated.

## 7. Module Dependency Direction

```
CLI
 └── Config
 └── Generator Orchestrator
      └── Provider Abstraction
      │    ├── ClaudeProvider
      │    ├── OpenAIProvider
      │    └── GeminiProvider
      └── Database Layer
 └── Game Engine
      ├── Command Parser
      ├── DSL Interpreter
      ├── State Manager
      └── Output Formatter
           └── Narrator (optional)
                └── Provider Abstraction
      └── Database Layer
```

Dependencies flow downward. The database layer and provider abstraction are leaf dependencies shared between the generation and runtime paths. The game engine never imports from the orchestrator and vice versa -- they share only the database schema.

## 8. Key Design Invariants

These are properties the system must always maintain:

1. **The engine never calls an LLM** (except narrator, which is read-only and optional).
2. **The `.zork` file is always a valid SQLite database** with referential integrity enforced by foreign keys.
3. **The DSL vocabulary is closed.** The LLM picks from a fixed set of precondition and effect types. The engine does not eval or exec anything.
4. **Each generation pass is independently retryable.** Transaction boundaries ensure partial passes don't corrupt the database.
5. **Narrator output never mutates state.** The narrator has no write path to the database.
6. **Provider choice is invisible to the orchestrator and engine.** They call the same interface regardless of which LLM is behind it.
7. **A `.zork` file is fully self-contained.** No external references, no network calls needed to play.
