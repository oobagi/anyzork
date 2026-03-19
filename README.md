# AnyZork

Turn a prompt into a playable, portable Zork-style text adventure.

AnyZork uses an LLM to generate a game world once, then runs that world with a deterministic engine. The result is a text adventure that keeps its state, stays internally consistent, and can be shared as a single `.zork` file.

## Why It Exists

Real-time LLM adventures tend to drift. They forget rooms, hallucinate inventory, and change puzzle logic mid-game.

AnyZork takes a different approach:

- Generate once with AI
- Store the game as structured data in SQLite
- Play it with a deterministic runtime

That means no runtime world drift, no changing rules, and no server required to play.

## Features

- Deterministic runtime engine
- Portable `.zork` game files
- Multi-pass world generation
- Command DSL for game logic
- Quest and trigger systems
- Optional narrator mode
- Provider support for Claude, OpenAI, and Gemini
- Guided prompt builder and presets

## Quickstart

### 1. Install

```bash
git clone https://github.com/oobagi/anyzork.git
cd anyzork
pip install -e .
```

Python 3.11+ is required.

### 2. Configure a Provider

The easiest way:

```bash
anyzork init
```

Or set an API key manually:

```bash
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
export GOOGLE_API_KEY=...
```

### 3. Generate a Game

```bash
anyzork generate "A haunted lighthouse on a foggy coast"
```

You can also use the guided wizard:

```bash
anyzork generate --guided
```

### 4. Play

```bash
anyzork play ~/.anyzork/games/haunted_lighthouse_on_a_foggy_coast.zork
```

Optional narrator mode:

```bash
anyzork play game.zork --narrator
```

## CLI Overview

```bash
anyzork generate "your prompt"
anyzork generate --guided
anyzork generate --list-presets
anyzork play game.zork
anyzork init
anyzork config
anyzork list
```

## How It Works

Generation is split into focused passes:

1. Concept
2. Rooms
3. Locks
4. Items
5. NPCs
6. Interactions
7. Puzzles
8. Commands
9. Quests
10. Triggers
11. Validation

At runtime, the engine reads the generated database and executes the game deterministically.

## Docs

- [Design Brief](docs/guides/design-brief.md)
- [System Architecture](docs/architecture/system-design.md)
- [Generation Pipeline](docs/architecture/generation-pipeline.md)
- [World Schema](docs/game-design/world-schema.md)
- [Command DSL Spec](docs/dsl/command-spec.md)
- [Implementation Phases](docs/guides/implementation-phases.md)

## Project Status

The core generator and deterministic runtime are in place and playable. Some areas, like immersive narrator mode and combat, are still planned or in progress.

## License

MIT
