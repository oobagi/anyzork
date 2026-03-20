# AnyZork

Turn a prompt into a playable, portable Zork-style text adventure.

AnyZork helps you author a game world once, compile it into a portable SQLite `.zork` file, and then run that world with a deterministic engine. The result is a text adventure that keeps its state, stays internally consistent, and can be shared as a single file.

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
- ZorkScript authoring wizard
- Command DSL for game logic
- Quest and trigger systems
- Optional narrator mode
- Guided prompt builder and presets

## Quickstart

### 1. Install

```bash
git clone https://github.com/oobagi/anyzork.git
cd anyzork
pip install -e .
```

Python 3.11+ is required.

### 2. Generate a ZorkScript Prompt

```bash
anyzork generate "A haunted lighthouse on a foggy coast"
```

You can also use the guided wizard:

```bash
anyzork generate --guided
```

This writes a ZorkScript authoring prompt. Send that prompt to your LLM, then save the returned ZorkScript to a file or pipe it directly into `anyzork import`.

### 3. Import

```bash
anyzork import haunted_lighthouse.zorkscript -o haunted_lighthouse.zork
```

You can also import from stdin:

```bash
cat haunted_lighthouse.zorkscript | anyzork import -
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
anyzork import -
anyzork play game.zork
anyzork list
```

## How It Works

The shipped authoring flow is:

1. `anyzork generate` builds a ZorkScript authoring prompt.
2. You send that prompt to an LLM and get back ZorkScript.
3. `anyzork import` compiles the ZorkScript into a `.zork` file.
4. `anyzork play` runs the resulting database deterministically.

## Docs

- [Design Brief](docs/guides/design-brief.md)
- [System Architecture](docs/architecture/system-design.md)
- [ADR-001: SQLite Game Storage](docs/architecture/adrs/adr-001-sqlite-game-storage.md)
- [Game Design Document](docs/game-design/gdd.md)
- [World Schema](docs/game-design/world-schema.md)
- [ZorkScript Spec](docs/dsl/zorkscript-spec.md)
- [Command DSL Spec](docs/dsl/command-spec.md)
- [Implementation Phases](docs/guides/implementation-phases.md)

## Project Status

The `generate -> import -> play` flow is shipped and playable. The remaining roadmap is focused on deeper narrator-mode immersion and optional combat.

## License

MIT
