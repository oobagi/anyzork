<div align="center">
  <img src="assets/anyzork-header.png" alt="AnyZork" width="520">
  <h1>AnyZork</h1>
  <p><strong>Use an LLM once to author a world, then play it on a deterministic engine.</strong></p>
  <p>
    <a href="#quickstart"><strong>Quickstart</strong></a>
    ·
    <a href="#make-your-own-game"><strong>Make Your Own Game</strong></a>
    ·
    <a href="#playing-games"><strong>Playing Games</strong></a>
    ·
    <a href="#narrator-mode"><strong>Narrator Mode</strong></a>
    ·
    <a href="#roadmap"><strong>Roadmap</strong></a>
    ·
    <a href="#contributing"><strong>Contributing</strong></a>
    ·
    <a href="#sharing-games"><strong>Sharing Games</strong></a>
    ·
    <a href="#docs"><strong>Docs</strong></a>
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

## Make Your Own Game

```bash
# 1. Generate an authoring prompt (guided wizard or one-liner)
anyzork generate --guided
anyzork generate "A haunted lighthouse on a foggy coast"

# 2. Paste the prompt into any LLM — it returns ZorkScript

# 3. Import and play
anyzork import game.zorkscript
anyzork play game
```

## Playing Games

```bash
anyzork play game.zork               # play a local file
anyzork play game                    # play a library game by name
anyzork play game --slot beta        # named save slot
anyzork play game --slot beta --new  # restart a slot
anyzork list                         # list library games
anyzork saves game                   # list save slots
```

Games imported without `-o` go into `~/.anyzork/games/`. Save slots live in `~/.anyzork/saves/`.

## Narrator Mode

An optional live-LLM layer that rewrites presentation without touching game state.

```bash
pip install -e ".[narrator]"
anyzork play game --narrator
```

Set a provider via env vars or `~/.anyzork/config.toml`:

| Provider | Env Var |
|---|---|
| `claude` | `ANTHROPIC_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `gemini` | `GOOGLE_API_KEY` |

<details>
<summary>Config file example</summary>

```toml
[anyzork]
provider = "openai"
model = "gpt-4o"

[keys]
openai = "your_key_here"
```

</details>

## Roadmap

See [GitHub Issues](https://github.com/oobagi/anyzork/issues) for the full roadmap and planned work.

## Sharing Games

Publish a library game to the official catalog:

```bash
anyzork publish my_game          # wizard walks you through metadata, then uploads
```

`publish` packages the game, walks you through listing metadata (title, author, genres, etc.), and uploads to the catalog in one step. An admin approves submissions from the dashboard before they appear publicly.

Once approved, players can browse and install from the CLI:

```bash
anyzork browse                   # list published games
anyzork install clockwork_archives  # install by catalog ref
anyzork install lighthouse.anyzorkpkg  # install a local package
```

`install` accepts an official catalog ref or a local `.anyzorkpkg` file. It does not install arbitrary remote URLs or raw `.zork` files.

<details>
<summary>Self-hosted catalog</summary>

Point `publish`, `browse`, and `install` at your own catalog server with env vars:

```bash
export ANYZORK_UPLOAD_URL="https://my-server.example.com/api/upload"
export ANYZORK_CATALOG_URL="https://my-server.example.com/api/catalog"
```

</details>

## Contributing

MIT-licensed, solo-maintained. Issues and PRs welcome — small focused changes and clear bug reports are easiest to review.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

## Docs

| Doc | What it covers |
|---|---|
| [Game Design Document](docs/engine/GDD.md) | Mechanics, design constraints, and motivation |
| [System Architecture](docs/engine/SYSTEM-DESIGN.md) | Components, commands, and runtime model |
| [World Schema](docs/engine/WORLD-SCHEMA.md) | `.zork` database reference |
| [ZorkScript Spec](docs/dsl/ZORKSCRIPT.md) | Authoring language reference |
| [Command DSL Spec](docs/dsl/COMMANDS.md) | Runtime rule vocabulary |
| [CLI Reference](docs/guides/CLI.md) | All commands, flags, and options |
| [Configuration](docs/guides/CONFIGURATION.md) | Config file, env vars, and provider setup |
| [Narrator Mode](docs/guides/NARRATOR.md) | Optional LLM prose layer |
| [Sharing Games](docs/server/SHARING.md) | Publishing, browsing, and installing |
| [ADR-001: SQLite Storage](docs/adrs/ADR-001-SQLITE-GAME-STORAGE.md) | Why `.zork` files are SQLite |

## License

MIT
