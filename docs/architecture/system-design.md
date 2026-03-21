# AnyZork System Architecture

## 1. Overview

AnyZork is a CLI tool that turns a natural-language idea into a playable text adventure. The shipped authoring path is intentionally split into two steps:

1. Authoring: `anyzork generate` produces a ZorkScript authoring prompt.
2. Import/runtime: an external LLM returns ZorkScript, `anyzork import` compiles it into a SQLite `.zork` file, and the deterministic engine plays it with no LLM in the loop unless optional narrator mode is enabled.

The separation is the product. The model creates content once; the engine owns state forever.

```text
Prompt -> `anyzork generate` -> external LLM -> `anyzork import` -> .zork database -> Game Engine -> Player
```

Current authoring flow:

1. `anyzork generate` creates a ZorkScript authoring prompt
2. The user sends that prompt to an external LLM
3. The returned ZorkScript is compiled with `anyzork import`
4. The deterministic runtime reads the resulting `.zork` file

## 2. Major Components

### 2.1 CLI

The entry point is [anyzork/cli.py](../../anyzork/cli.py).

Current commands:

- `anyzork generate [prompt]`
- `anyzork import <file|->`
- `anyzork play <file.zork>`
- `anyzork list`
- `anyzork saves <game>`
- `anyzork delete-save <game>`
- `anyzork delete <game>`

The CLI handles argument parsing, import/export UX, and launching the runtime engine.

### 2.2 Config

Configuration lives in [anyzork/config.py](../../anyzork/config.py) and uses `pydantic-settings`.

Sources, from lowest to highest priority:

1. Defaults
2. `~/.anyzork/config.toml`
3. `.env`
4. Environment variables
5. CLI overrides

Supported providers for narrator mode today are `claude`, `openai`, and `gemini`.

### 2.3 Database Layer

The database wrapper lives in [anyzork/db/schema.py](../../anyzork/db/schema.py). SQLite is both the world format and the save format.

Important tables:

| Table | Purpose |
|---|---|
| `metadata` | Title, prompt, seed, intro/win text, score caps, win/lose conditions |
| `rooms`, `exits`, `locks` | Spatial graph and gating |
| `items` | World objects, containers, item states, quantities |
| `npcs`, `dialogue_nodes`, `dialogue_options` | NPC placement and branching dialogue |
| `puzzles` | Puzzle definitions and completion state |
| `commands` | DSL rules for player-initiated actions |
| `flags` | Shared world-state glue |
| `quests`, `quest_objectives` | Player-facing goals and progress tracking |
| `interaction_responses` | Category/tag-based item-on-target responses |
| `triggers` | Reactive rules fired by emitted events |
| `player`, `score_entries`, `visited_rooms` | Runtime state |

`GameDB` provides the single persistence API used by the engine, importer, and CLI.

### 2.4 Runtime Engine

The runtime entry point is [anyzork/engine/game.py](../../anyzork/engine/game.py).

The engine loop is deterministic:

1. Read player input
2. Resolve built-in verbs or DSL commands
3. Check preconditions against database state
4. Apply effects
5. Emit events and evaluate matching triggers
6. Tick quest state
7. Check win/lose conditions
8. Render output

Built-in commands include `look`, `inventory`, `quests`, `help`, `save`, `quit`, movement shortcuts, container verbs, dialogue verbs, and item-state helpers such as `turn on`.

### 2.5 Command DSL

The command interpreter lives in [anyzork/engine/commands.py](../../anyzork/engine/commands.py). It evaluates structured rules stored in `commands`.

Current precondition families include:

- room and inventory checks
- flag checks
- lock and puzzle checks
- NPC and item presence checks
- container and quantity checks

Current effect families include:

- moving or removing items
- setting flags
- unlocking locks and revealing exits
- moving the player
- spawning items
- health and score changes
- solving puzzles
- discovering quests
- container and quantity operations
- item toggle-state updates

The authoritative effect/precondition contract is documented in [docs/dsl/command-spec.md](../dsl/command-spec.md).

### 2.6 Quest and Trigger Systems

Two higher-level deterministic layers sit on top of the command DSL:

- Quests: player-facing tracking built from flags and objectives
- Triggers: reactive mechanics fired by events like `room_enter`, `flag_set`, `dialogue_node`, `item_taken`, and `item_dropped`

Quests do not gate actions directly. They observe state and present progress. Triggers let the world react without requiring the player to type a command.

### 2.7 Provider Abstraction

Providers implement a shared interface in [anyzork/generator/providers/base.py](../../anyzork/generator/providers/base.py). Narrator mode still relies on that abstraction, so the rest of the system does not care whether the backend is Claude, OpenAI, or Gemini.

### 2.8 Narrator

Narrator mode lives in [anyzork/engine/narrator.py](../../anyzork/engine/narrator.py). It is read-only presentation polish layered on top of deterministic output.

The narrator may restyle text, but it may not:

- mutate the database
- invent rooms, exits, items, or quest state
- override command success or failure

If narrator mode fails, the engine falls back to plain deterministic output.

## 3. Authoring Architecture

The current authoring path is intentionally simple:

1. `anyzork generate` creates a strong ZorkScript authoring prompt.
2. An external LLM writes ZorkScript.
3. `anyzork import` parses and validates that ZorkScript.
4. Deterministic validation runs against the compiled `.zork` database.

## 4. Runtime State Model

The `.zork` file is also the save:

- world data is immutable in shape after generation
- runtime tables track player state, visited rooms, score, quest status, and one-shot execution state
- saving is just persisting the SQLite file

This means the engine never needs a separate save serializer.

## 5. Validation Philosophy

Validation is split across two layers:

1. Import-time validation: ZorkScript syntax, obvious required references, and local sanity checks.
2. Final deterministic validation: whole-world consistency across rooms, locks, commands, quests, triggers, and score metadata.

The validator is there to catch wiring mistakes, not to compensate for an undefined data model.
