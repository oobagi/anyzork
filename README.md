<div align="center">
  <img src="assets/anyzork-header.png" alt="AnyZork" width="520">
  <h1>AnyZork</h1>
  <p><strong>Use an LLM once to author a world, then play it on a deterministic engine.</strong></p>
  <p>
    <a href="#quickstart"><strong>Quickstart</strong></a>
    ·
    <a href="#features"><strong>Features</strong></a>
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

Try the bundled example:

```bash
anyzork import examples/alchemist_tower.zorkscript -o tower.zork
anyzork play tower.zork
```

## Features

**[Make Your Own Game](docs/guides/CLI.md)** — Generate a prompt, paste it into any LLM to get ZorkScript, then import and play. A guided wizard or a one-liner gets you started.

**[Playing Games](docs/guides/CLI.md)** — Play local files or library games, manage named save slots, and list your collection. See the [CLI reference](docs/guides/CLI.md) for every command and flag.

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
