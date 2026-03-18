# AnyZork - AI-Powered Text Adventure Generator

A CLI tool that takes a user prompt and generates a complete, playable Zork-style text adventure game.

## Start Here

**Read the design brief first:** [docs/guides/design-brief.md](docs/guides/design-brief.md) — explains the problem, the solution, and every major design decision with full rationale.

## Core Concept

The LLM generates the world as **structured data + deterministic command logic** stored in a SQLite database (`.zork` file). A **deterministic game engine** runs it at play-time. No LLM at runtime (except optional narrator mode) = no hallucination, no inconsistency.

**Two phases:**
1. **Generation** (LLM) — multi-pass world builder populates a `.zork` database
2. **Runtime** (deterministic) — state machine engine reads from the database

## Documentation

| Doc | Path | Status |
|-----|------|--------|
| System Architecture | [docs/architecture/system-design.md](docs/architecture/system-design.md) | Done |
| ADR-001: SQLite | [docs/architecture/adrs/adr-001-sqlite-game-storage.md](docs/architecture/adrs/adr-001-sqlite-game-storage.md) | Done |
| Game Design Document | [docs/game-design/gdd.md](docs/game-design/gdd.md) | Done |
| World Schema | [docs/game-design/world-schema.md](docs/game-design/world-schema.md) | Done |
| Command DSL Spec | [docs/dsl/command-spec.md](docs/dsl/command-spec.md) | Done |
| Generation Pipeline | [docs/architecture/generation-pipeline.md](docs/architecture/generation-pipeline.md) | Done |
| Provider Guide | [docs/providers/integration.md](docs/providers/integration.md) | Done |
| Design Brief | [docs/guides/design-brief.md](docs/guides/design-brief.md) | Done |
| Implementation Phases | [docs/guides/implementation-phases.md](docs/guides/implementation-phases.md) | Active |

## Tech Stack

- **Language**: Python 3.11+
- **CLI**: click + rich
- **Database**: SQLite (one `.zork` file = one portable game)
- **LLM Providers**: Claude API, OpenAI API, Gemini API (bring your own key)
- **Config**: pydantic-settings (env vars with `ANYZORK_` prefix)

## Agents

Specialized agents in `.claude/agents/` (sourced from [agency-agents](https://github.com/msitarzewski/agency-agents)):

| Agent | File | Role |
|-------|------|------|
| Game Designer | `.claude/agents/game-designer.md` | Systems/mechanics, GDD, gameplay loops |
| Narrative Designer | `.claude/agents/narrative-designer.md` | Story, lore, dialogue, world-building |
| Level Designer | `.claude/agents/level-designer.md` | Room layout, spatial flow, pacing |
| Software Architect | `.claude/agents/engineering-software-architect.md` | System design, ADRs |
| Code Reviewer | `.claude/agents/engineering-code-reviewer.md` | Code quality, security |
| Reality Checker | `.claude/agents/testing-reality-checker.md` | Validation, production readiness |
| Technical Artist | `.claude/agents/technical-artist.md` | Visual/technical polish |
| Game Audio Engineer | `.claude/agents/game-audio-engineer.md` | Audio design |

## Key Features

- **Deterministic runtime** — game state lives in SQLite, commands are DSL rules, no LLM drift
- **Command DSL** — LLM generates structured precondition/effect rules, engine interprets them
- **Multi-pass generation** — rooms -> exits -> locks -> items -> NPCs -> puzzles -> commands -> lore
- **Narrator mode** — optional thin LLM layer that flavors deterministic output with prose (can't change state)
- **Portable games** — `.zork` files are just SQLite, copy/share freely
- **Seed system** — same prompt + seed = reproducible world
- **Configurable providers** — bring your own API key (Claude, OpenAI, or Gemini)
