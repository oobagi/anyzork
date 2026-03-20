# AnyZork

CLI for authoring and playing deterministic Zork-style text adventures.

## Start Here

Read [docs/guides/design-brief.md](docs/guides/design-brief.md) first. It explains the product shape, the current authoring flow, and the architecture boundaries that matter most.

## Core Concept

AnyZork ships a simple authoring-to-runtime loop:

1. `anyzork generate` builds a ZorkScript authoring prompt.
2. An external LLM returns ZorkScript.
3. `anyzork import` compiles that ZorkScript into a portable SQLite `.zork` file.
4. `anyzork play` runs the game with a deterministic engine.

No LLM is required at runtime unless the player explicitly enables narrator mode.

## Core Docs

| Doc | Path | Purpose |
|-----|------|---------|
| Design Brief | [docs/guides/design-brief.md](docs/guides/design-brief.md) | Product framing and major decisions |
| System Architecture | [docs/architecture/system-design.md](docs/architecture/system-design.md) | Current component map and command surface |
| ADR-001: SQLite | [docs/architecture/adrs/adr-001-sqlite-game-storage.md](docs/architecture/adrs/adr-001-sqlite-game-storage.md) | Why `.zork` files are SQLite |
| Game Design Document | [docs/game-design/gdd.md](docs/game-design/gdd.md) | Supported mechanics and design constraints |
| World Schema | [docs/game-design/world-schema.md](docs/game-design/world-schema.md) | Human-oriented schema reference |
| ZorkScript Spec | [docs/dsl/zorkscript-spec.md](docs/dsl/zorkscript-spec.md) | Authoring language reference |
| Command DSL Spec | [docs/dsl/command-spec.md](docs/dsl/command-spec.md) | Runtime rule vocabulary |
| Implementation Phases | [docs/guides/implementation-phases.md](docs/guides/implementation-phases.md) | Remaining roadmap / future work |

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
