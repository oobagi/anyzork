# AnyZork

CLI for authoring and playing deterministic Zork-style text adventures.

## Start Here

Read [docs/engine/GDD.md](docs/engine/GDD.md) first. It explains the product motivation, supported mechanics, and the architecture boundaries that matter most.

## Core Concept

AnyZork ships a simple authoring-to-runtime loop:

1. `anyzork generate` builds a ZorkScript authoring prompt.
2. An external LLM returns ZorkScript.
3. `anyzork import` compiles that ZorkScript into a portable `.zork` archive.
4. `anyzork play` runs the game with a deterministic engine.

No LLM is required at runtime unless the player explicitly enables narrator mode.

## Versioning Rules

- `app_version` is the packaged AnyZork release version. It is sourced from installed package metadata via `anyzork/versioning.py`. Bump the package version when you intentionally ship a new AnyZork release.
- `runtime_compat_version` is the deterministic engine/save compatibility contract. Bump it only when runtime behavior or the `.zork` metadata/save contract changes in a backward-incompatible way.
- `prompt_system_version` fingerprints the shipped authoring system in `anyzork/importer.py`. It changes automatically when prompt-generation files change, so agents do not need to bump it by hand.
- Prompt or wizard changes should not bump `runtime_compat_version` unless they also change what the runtime expects from compiled games.
- Do not hardcode app version strings in multiple places. Keep version reads centralized through `anyzork/versioning.py`.

## Core Docs

| Doc | Path | Purpose |
|-----|------|---------|
| Game Design Document | [docs/engine/GDD.md](docs/engine/GDD.md) | Motivation, mechanics, and design constraints |
| System Architecture | [docs/engine/SYSTEM-DESIGN.md](docs/engine/SYSTEM-DESIGN.md) | Component map and command surface |
| World Schema | [docs/engine/WORLD-SCHEMA.md](docs/engine/WORLD-SCHEMA.md) | `.zork` database reference |
| ZorkScript Spec | [docs/dsl/ZORKSCRIPT.md](docs/dsl/ZORKSCRIPT.md) | Authoring language reference |
| Command DSL Spec | [docs/dsl/COMMANDS.md](docs/dsl/COMMANDS.md) | Runtime rule vocabulary |
| CLI Reference | [docs/guides/CLI.md](docs/guides/CLI.md) | All commands, flags, and options |
| Configuration | [docs/guides/CONFIGURATION.md](docs/guides/CONFIGURATION.md) | Config file, env vars, providers |
| Narrator Mode | [docs/guides/NARRATOR.md](docs/guides/NARRATOR.md) | Optional LLM prose layer |
| Sharing Games | [docs/server/SHARING.md](docs/server/SHARING.md) | Publishing, browsing, installing |
| ADR-001: SQLite | [docs/adrs/ADR-001-SQLITE-GAME-STORAGE.md](docs/adrs/ADR-001-SQLITE-GAME-STORAGE.md) | Original SQLite rationale (superseded) |

## Tech Stack

- Python 3.11+
- `click` + `rich` CLI
- `.zork` archives (zip) for game distribution; SQLite for compilation cache and save state
- `pydantic-settings` config with `ANYZORK_` env vars
- Claude / OpenAI / Gemini support for optional narrator mode

## Agents

| Agent | Role |
|-------|------|
| ZorkScript Author | Game generation, CLI management, publishing |

### Skills

| Skill | Trigger |
|-------|---------|
| `/zork` | `/zork <concept>` — generate a game or manage library |

## Key Features

- Deterministic runtime with archive-backed world data and SQLite compilation cache
- ZorkScript-based authoring and local compilation
- Structured command DSL for game logic
- Quest, trigger, container, dialogue, item-state, faction, combat, NPC behavior, and variable systems
- Portable single-file games and saves
- Optional narrator mode layered on top of deterministic output
