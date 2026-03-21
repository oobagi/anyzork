# AnyZork

CLI for authoring and playing deterministic Zork-style text adventures.

## Start Here

Read [docs/engine/GDD.md](docs/engine/GDD.md) first. It explains the product motivation, supported mechanics, and the architecture boundaries that matter most.

## Core Concept

AnyZork ships a simple authoring-to-runtime loop:

1. `anyzork generate` builds a ZorkScript authoring prompt.
2. An external LLM returns ZorkScript.
3. `anyzork import` compiles that ZorkScript into a portable SQLite `.zork` file.
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
| ADR-001: SQLite | [docs/adrs/ADR-001-SQLITE-GAME-STORAGE.md](docs/adrs/ADR-001-SQLITE-GAME-STORAGE.md) | Why `.zork` files are SQLite |

## Tech Stack

- Python 3.11+
- `click` + `rich` CLI
- SQLite `.zork` files for game and save state
- `pydantic-settings` config with `ANYZORK_` env vars
- Claude / OpenAI / Gemini support for optional narrator mode

## Agents

Specialized agents live in `.Codex/agents/`:

| Agent | File | Role |
|-------|------|------|
| Game Designer | `.Codex/agents/game-designer.md` | Mechanics, gameplay loops, balance |
| Narrative Designer | `.Codex/agents/narrative-designer.md` | Story, world-building, prompt tone |
| Level Designer | `.Codex/agents/level-designer.md` | Room layout, pacing, spatial flow |
| Software Architect | `.Codex/agents/engineering-software-architect.md` | System design, ADRs, integration |
| Code Reviewer | `.Codex/agents/engineering-code-reviewer.md` | Code quality, regressions, safety |
| Reality Checker | `.Codex/agents/testing-reality-checker.md` | Validation and production readiness |
| Technical Artist | `.Codex/agents/technical-artist.md` | Presentation polish |
| Game Audio Engineer | `.Codex/agents/game-audio-engineer.md` | Audio design ideas |

## Key Features

- Deterministic runtime with SQLite-backed world state
- ZorkScript-based authoring and local compilation
- Structured command DSL for game logic
- Quest, trigger, container, dialogue, and item-state systems
- Portable single-file games and saves
- Optional narrator mode layered on top of deterministic output
