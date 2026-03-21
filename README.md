<div align="center">
  <img src="assets/anyzork-header.png" alt="AnyZork" width="520">
  <h1>AnyZork</h1>
  <p><strong>A Zork-style text adventure generator. Describe a world to any LLM, get back a complete game, and play it on a fully deterministic engine — no AI needed at runtime.</strong></p>
  <p>
    <a href="#quickstart"><strong>Quickstart</strong></a>
    ·
    <a href="#make-your-own-game"><strong>Make Your Own</strong></a>
    ·
    <a href="#docs"><strong>Docs</strong></a>
    ·
    <a href="#contributing"><strong>Contributing</strong></a>
  </p>
</div>

---

## Quickstart

> Requires Python 3.11+

```bash
git clone https://github.com/oobagi/anyzork.git
cd anyzork && python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Browse and play a community game:

```bash
anyzork browse                        # see what's available
anyzork install haunted-lighthouse    # add it to your library
anyzork play haunted-lighthouse       # start playing
```

## Make Your Own Game

Generate a prompt, send it to any LLM (Claude, GPT, Gemini, etc.), then compile the response into a playable game:

```bash
# one-liner — generates a prompt you paste into your LLM
anyzork generate "haunted lighthouse on a cliff" -o prompt.txt

# or use the interactive wizard
anyzork generate --guided

# compile the LLM's ZorkScript response into a .zork game
anyzork import lighthouse.zorkscript -o lighthouse.zork
anyzork play lighthouse.zork
```

See the [CLI reference](docs/guides/CLI.md) for all commands and flags, including genre presets, lint, and `--report`.

## Features

**[Playing Games](docs/guides/CLI.md)** — Play local files or library games, manage named save slots, and list your collection.

**[Narrator Mode](docs/guides/NARRATOR.md)** — An optional live-LLM layer that rewrites room descriptions and event text without touching game state. Supports Claude, OpenAI, and Gemini.

**[Sharing Games](docs/server/SHARING.md)** — Publish games to the official catalog, browse community submissions, and install with a single command.

## Docs

| Doc | What it covers |
|---|---|
| [Game Design Document](docs/engine/GDD.md) | Mechanics, design constraints, and motivation |
| [System Architecture](docs/engine/SYSTEM-DESIGN.md) | Components, commands, and runtime model |
| [World Schema](docs/engine/WORLD-SCHEMA.md) | `.zork` database reference |
| [ZorkScript Spec](docs/dsl/ZORKSCRIPT.md) | Authoring language reference |
| [Command DSL Spec](docs/dsl/COMMANDS.md) | Runtime rule vocabulary |
| [Author Tooling](docs/design/AUTHOR-TOOLING.md) | Lint, import diagnostics, and `--report` design |
| [CLI Reference](docs/guides/CLI.md) | All commands, flags, and options |
| [Configuration](docs/guides/CONFIGURATION.md) | Config file, env vars, and provider setup |
| [Narrator Mode](docs/guides/NARRATOR.md) | Optional LLM prose layer |
| [Sharing Games](docs/server/SHARING.md) | Publishing, browsing, and installing |
| [ADR-001: SQLite Storage](docs/adrs/ADR-001-SQLITE-GAME-STORAGE.md) | Why `.zork` files are SQLite |
| [Roadmap](ROADMAP.md) | Ordered plan and milestone tracking |

## Contributing

MIT-licensed, solo-maintained. Issues and PRs welcome — small focused changes and clear bug reports are easiest to review.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

## License

MIT
