# AnyZork System Architecture

## 1. Overview

AnyZork is a CLI tool that turns a natural-language idea into a playable text adventure. The shipped authoring path is intentionally split into two steps:

1. Authoring: `anyzork generate` produces a ZorkScript authoring prompt.
2. Import/runtime: an external LLM returns ZorkScript, `anyzork import` compiles it into a `.zork` archive, and the deterministic engine plays it with no LLM in the loop unless optional narrator mode is enabled.

The separation is the product. The model creates content once; the engine owns state forever.

```text
Prompt -> `anyzork generate` -> external LLM -> `anyzork import` -> .zork archive -> Game Engine -> Player
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

- `anyzork generate [prompt]` — build a ZorkScript authoring prompt (freeform, guided wizard, or preset)
- `anyzork import <file|->` — compile ZorkScript into a `.zork` game file
- `anyzork doctor <file|->` — check a ZorkScript source file for errors and generate a fix prompt
- `anyzork publish <game>` — package a library game and upload it to the catalog
- `anyzork publish --status <slug>` — check the publish status of a submitted game
- `anyzork install <source>` — install a game from the catalog or a local `.zork` package
- `anyzork browse` — browse the public catalog
- `anyzork play [game]` — play a library game or `.zork` file
- `anyzork list` — list library games and their active saves
- `anyzork list --saves` — also show detailed managed save slots
- `anyzork delete <game>` — delete a library game and all its saves

The CLI handles argument parsing, import/export UX, package creation, catalog publishing and status tracking, install flows, catalog browsing, and launching the runtime engine.

### 2.2 Config

Configuration lives in [anyzork/config.py](../../anyzork/config.py) and uses `pydantic-settings`.

Sources, from lowest to highest priority:

1. Defaults
2. `~/.anyzork/config.toml`
3. `.env`
4. Environment variables
5. CLI overrides

Supported providers for narrator mode today are `claude`, `openai`, and `gemini`.
Browse/install talk to the official AnyZork catalog, publish talks to the official AnyZork upload API, and public installs are intentionally limited to official refs plus local `.zork` artifacts.

### 2.3 Public Catalog Service

Client-side packaging, installation, and upload logic lives in [anyzork/sharing.py](../../anyzork/sharing.py). The server-side catalog is a small FastAPI app at [anyzork/catalog_api.py](../../anyzork/catalog_api.py), backed by SQLite + package-file storage in [anyzork/catalog_store.py](../../anyzork/catalog_store.py).

The service exposes:

- `POST /api/games` for uploaded `.zork` files and metadata
- `GET /api/games` for public game listings
- `GET /api/games/{slug}` for one public entry
- `GET /api/games/{slug}/status` for publish status checks
- `GET /api/games/{slug}/package` for package downloads
- `GET /catalog.json` for the CLI catalog contract
- `GET /admin` for the admin dashboard
- `GET /healthz` for health checks

This is deployment infrastructure for the official AnyZork hosted catalog. The end-user CLI is intentionally aligned to that single service instead of supporting arbitrary user-hosted catalogs.

### 2.4 Database Layer

The database wrapper lives in [anyzork/db/schema.py](../../anyzork/db/schema.py). `.zork` archives hold the authored world as `manifest.toml` + `.zorkscript` source files. SQLite is used internally as a compilation cache (`~/.anyzork/cache/*.db`) and for save files (`~/.anyzork/saves/`).

Important tables:

| Table | Purpose |
|---|---|
| `metadata` | Title, prompt, seed, intro/win text, score caps, win/lose conditions, version tracking, realism level |
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

### 2.5 Runtime Engine

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

### 2.6 Command DSL

The command interpreter lives in [anyzork/engine/commands.py](../../anyzork/engine/commands.py). It evaluates structured rules stored in `commands`.

Current precondition families include:

- room and inventory checks
- flag checks
- lock and puzzle checks
- NPC and item presence/accessibility checks
- container and quantity checks
- item toggle-state checks

Current effect families include:

- moving or removing items
- setting flags
- unlocking locks, revealing exits, locking exits, hiding exits
- moving the player
- spawning items
- health and score changes
- solving puzzles
- discovering, completing, or failing quests
- container and quantity operations
- item toggle-state updates
- NPC manipulation (moving, killing, removing)
- description changes

The authoritative effect/precondition contract is documented in [docs/dsl/COMMANDS.md](../dsl/COMMANDS.md).

### 2.7 Quest and Trigger Systems

Two higher-level deterministic layers sit on top of the command DSL:

- Quests: player-facing tracking built from flags and objectives
- Triggers: reactive mechanics fired by events like `room_enter`, `flag_set`, `dialogue_node`, `item_taken`, and `item_dropped`

Quests do not gate actions directly. They observe state and present progress. Triggers let the world react without requiring the player to type a command.

### 2.8 Provider Abstraction

Providers implement a shared interface in [anyzork/engine/providers/base.py](../../anyzork/engine/providers/base.py). Narrator mode still relies on that abstraction, so the rest of the system does not care whether the backend is Claude, OpenAI, or Gemini.

### 2.9 Narrator

Narrator mode lives in [anyzork/engine/narrator.py](../../anyzork/engine/narrator.py). It is read-only presentation polish layered on top of deterministic output.

The narrator may restyle text, but it may not:

- mutate the database
- invent rooms, exits, items, or quest state
- override command success or failure

If narrator mode fails, the engine falls back to plain deterministic output.

### 2.10 Diagnostic System

Diagnostics are produced by [anyzork/diagnostics.py](../../anyzork/diagnostics.py) and [anyzork/lint.py](../../anyzork/lint.py).

`diagnostics.py` defines a unified `Diagnostic` dataclass with fields for severity (error, warning, info), message, and optional source location. All lint and import validation findings are expressed as `Diagnostic` instances, giving consumers a single type to work with.

`lint.py` exposes `lint_spec()`, which takes a parsed ZorkScript spec and returns a list of `Diagnostic` objects. It checks for common authoring mistakes -- dangling references, unused flags, unreachable rooms, and similar structural issues -- without compiling to a database.

The main consumers are:

- `anyzork doctor` — runs `lint_spec()`, prints results grouped by severity with a summary count, and generates a fix prompt for LLM-assisted repair. Exits 0 if no errors (warnings are OK), 1 if errors are found.

### 2.11 ZorkScript Parser

The parser lives in [anyzork/zorkscript.py](../../anyzork/zorkscript.py). It is a hand-written recursive descent tokenizer and block parser that converts ZorkScript source text into the normalized import-spec dict consumed by `compile_import_spec`. Parse errors include line numbers via `ZorkScriptError`.

### 2.12 Services Layer

Reusable service helpers in [anyzork/services/](../../anyzork/services/) decouple business logic from the CLI so that other entrypoints (e.g., a TUI) can share the same operations:

- `authoring` — field normalization, validation, and `AuthoringBundle` construction for the prompt builder
- `importing` — `import_zorkscript` and `import_zorkscript_spec` wrappers around the compiler
- `library` — game resolution, managed save preparation, and `LibraryOverview` queries
- `play` — `PlaySession` wrapping the deterministic engine for programmatic turn-by-turn interaction

### 2.13 Versioning

Central version metadata lives in [anyzork/versioning.py](../../anyzork/versioning.py). Two version axes are tracked:

- `APP_VERSION` — the installed package version (from `importlib.metadata`).
- `RUNTIME_COMPAT_VERSION` — a short tag (currently `r1`) embedded in every `.zork` file so the engine can reject incompatible databases.

The prompt-generation system also has its own fingerprint (`prompt_system_version`), derived from the SHA-256 of all files involved in prompt assembly. This lets the catalog and CLI detect when a game was authored with a different prompt system.

## 3. Authoring Architecture

The authoring path has three input modes, all producing the same output:

1. **Freeform**: `anyzork generate "a haunted lighthouse"` wraps the user's idea into a ZorkScript authoring prompt.
2. **Guided wizard**: `anyzork generate --guided` walks the user through structured world-building fields (setting, characters, items, tone, scale, realism) and assembles a richer prompt.
3. **Presets**: `anyzork generate --preset fantasy-dungeon` loads a TOML preset from `anyzork/presets/` or `~/.anyzork/presets/`. With `--no-edit` the prompt is emitted immediately; without it the wizard opens with preset values pre-filled.

The wizard lives in [anyzork/wizard/](../../anyzork/wizard/): `fields.py` defines the field schema, `wizard.py` drives the interactive CLI flow, `assembler.py` renders fields into prompt text, and `presets.py` discovers and loads TOML presets.

After a prompt is resolved, `build_zorkscript_prompt()` in [anyzork/importer.py](../../anyzork/importer.py) wraps it with the full ZorkScript authoring template — a grammar reference, a complete example game, and realism-level guidance. The user sends that template to an external LLM, which returns ZorkScript source.

The import pipeline then:

1. Parses ZorkScript via the hand-written recursive descent parser in [anyzork/zorkscript.py](../../anyzork/zorkscript.py).
2. Compiles the parsed spec into a `.zork` archive (with an internal SQLite compilation cache).
3. Runs deterministic validation against the compiled database.

## 4. Runtime State Model

The `.zork` archive holds the authored source; the engine plays against a compiled SQLite database (either the compilation cache or a managed save copy):

- world data is immutable in shape after generation
- runtime tables track player state, visited rooms, score, quest status, and one-shot execution state
- saving is just persisting the SQLite save file

Save files are managed copies of the compiled database stored in `~/.anyzork/saves/`.

## 5. Validation Philosophy

Validation is split across two layers:

1. Import-time validation: ZorkScript syntax, obvious required references, and local sanity checks.
2. Final deterministic validation: whole-world consistency across rooms, locks, commands, quests, triggers, and score metadata.

The validator is there to catch wiring mistakes, not to compensate for an undefined data model.
