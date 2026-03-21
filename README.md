<div align="center">
  <img src="assets/anyzork-header.png" alt="AnyZork" width="520">
  <h1>AnyZork</h1>
  <p><strong>Build deterministic <a href="https://en.wikipedia.org/wiki/Zork">Zork</a>-style text adventures with AI-assisted authoring.</strong></p>
  <p>Generate a ZorkScript authoring prompt, have an LLM write the world, compile it into a portable SQLite <code>.zork</code> file, and play it with a deterministic engine.</p>
  <p>
    <a href="#quickstart"><strong>Quickstart</strong></a>
    ·
    <a href="#core-concepts"><strong>Core Concepts</strong></a>
    ·
    <a href="#how-it-works"><strong>How It Works</strong></a>
    ·
    <a href="#sharing-games"><strong>Sharing Games</strong></a>
    ·
    <a href="#docs"><strong>Docs</strong></a>
  </p>
</div>

---

## Quickstart

Install from a fresh clone:

```bash
git clone https://github.com/oobagi/anyzork.git
cd anyzork
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Requires Python 3.11+.

Try the included example without using an LLM:

```bash
anyzork import examples/minimal_game.zorkscript -o starter.zork
anyzork play starter.zork
```

If you want optional narrator mode, install the narrator extra:

```bash
pip install -e ".[narrator]"
```

Create your own game:

```bash
anyzork generate --guided
# paste the generated authoring prompt into your LLM
# save the response as game.zorkscript
anyzork import game.zorkscript -o game.zork
anyzork play game.zork
```

Prefer a one-line prompt? Use:

```bash
anyzork generate "A haunted lighthouse on a foggy coast"
```

Optional narrator mode:

```bash
anyzork play game.zork --narrator
```

> AnyZork uses an LLM during authoring, not during normal play. Runtime stays deterministic unless you explicitly enable narrator mode.

## Project Status

AnyZork is open source and MIT-licensed, but it is currently maintained as a solo project.

External pull requests and general code contributions are not being accepted right now.

If you run into a reproducible bug, feel free to open an issue. For security-sensitive problems, use the guidance in [SECURITY.md](SECURITY.md).

## Narrator Setup

Narrator mode is optional and only affects presentation during play. Configure a provider with either standard provider env vars or `ANYZORK_` overrides:

```bash
export ANYZORK_PROVIDER=openai
export OPENAI_API_KEY=your_key_here
anyzork play game.zork --narrator
```

Supported providers:

- `claude` with `ANTHROPIC_API_KEY` or `ANYZORK_ANTHROPIC_API_KEY`
- `openai` with `OPENAI_API_KEY` or `ANYZORK_OPENAI_API_KEY`
- `gemini` with `GOOGLE_API_KEY` or `ANYZORK_GOOGLE_API_KEY`

You can also store defaults in `~/.anyzork/config.toml`:

```toml
[anyzork]
provider = "openai"
model = "gpt-4o"

[keys]
openai = "your_key_here"
```

If narrator mode fails, AnyZork falls back to deterministic engine output.

## Core Concepts

| Term | What it is | Read more |
|---|---|---|
| **AnyZork** | A CLI for authoring and playing deterministic text adventures inspired by [Zork](https://en.wikipedia.org/wiki/Zork). | [Design Brief](docs/guides/design-brief.md) |
| **ZorkScript** | AnyZork's human-readable authoring DSL. An external LLM writes this text format. | [ZorkScript Spec](docs/dsl/zorkscript-spec.md) |
| **`.zork` file** | A portable SQLite database containing the compiled game world and runtime state. | [World Schema](docs/game-design/world-schema.md) and [ADR-001](docs/architecture/adrs/adr-001-sqlite-game-storage.md) |
| **Narrator mode** | An optional read-only LLM layer during play. | [System Architecture](docs/architecture/system-design.md) |

## How It Works

```text
idea -> anyzork generate -> external LLM -> ZorkScript -> anyzork import -> .zork -> anyzork play
```

1. `anyzork generate` builds the authoring prompt.
2. Your external LLM writes the world in ZorkScript.
3. `anyzork import` validates and compiles that into a `.zork` file.
4. `anyzork play` runs the resulting game deterministically.

Import from stdin if you prefer:

```bash
cat game.zorkscript | anyzork import -
```

For the full architecture and rationale, see the [Design Brief](docs/guides/design-brief.md) and [System Architecture](docs/architecture/system-design.md).

## Sharing Games

Package a library game or `.zork` file for sharing:

```bash
anyzork publish game.zork -o lighthouse.anyzorkpkg
```

`publish` creates a portable `.anyzorkpkg` archive containing the compiled `game.zork` plus a small manifest. By default the manifest pulls title/description from the compiled game metadata, and you can override the public listing fields directly from the CLI:

```bash
anyzork publish game.zork -o lighthouse.anyzorkpkg \
  --author "Jaden" \
  --description "A foggy lighthouse mystery." \
  --genre mystery \
  --genre short
```

If you want a step-by-step walkthrough instead of flags:

```bash
anyzork publish game.zork --guided
```

Creators can upload packages to the official catalog service, and players can browse/install from the CLI:

```bash
anyzork publish game.zork -o lighthouse.anyzorkpkg
anyzork upload lighthouse.anyzorkpkg
anyzork browse
anyzork install clockwork_archives
anyzork install lighthouse.anyzorkpkg
```

`install` is intentionally narrow: it accepts an official catalog ref or a local
`.anyzorkpkg` file. It does not install arbitrary remote URLs or raw `.zork`
files.

## Development

Set up a local development environment with:

```bash
python -m pip install -e '.[dev]'
```

Common checks:

```bash
ruff check .
pytest -q
python -m build
```

## Docs

| Doc | What it covers |
|---|---|
| [Design Brief](docs/guides/design-brief.md) | Product framing and the core authoring/runtime split |
| [System Architecture](docs/architecture/system-design.md) | Current components, command surface, and runtime model |
| [Game Design Document](docs/game-design/gdd.md) | Supported mechanics and design constraints |
| [World Schema](docs/game-design/world-schema.md) | Human-oriented reference for the `.zork` database |
| [ZorkScript Spec](docs/dsl/zorkscript-spec.md) | The authoring language reference |
| [Command DSL Spec](docs/dsl/command-spec.md) | The runtime rule vocabulary |
| [ADR-001: SQLite Game Storage](docs/architecture/adrs/adr-001-sqlite-game-storage.md) | Why `.zork` files are SQLite |
| [Implementation Phases](docs/guides/implementation-phases.md) | Remaining roadmap and future work |

## License

MIT
