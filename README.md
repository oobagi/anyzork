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

### Public Game Sharing

- [ ] Public game finder — upload and share games
- [ ] Browse, upvote, and downvote shared games
- [ ] Reporting and moderation for junk uploads

### Narrator Improvements

- [ ] Narrate rooms, actions, dialogue, inventory, quests, and system feedback
- [ ] Hide standard UI chrome when narrator prose is available
- [ ] Tighten prompts and context to reduce cost and latency
- [ ] Aggressive caching for repeated room visits and actions
- [ ] Graceful fallback when provider calls fail
- [ ] Read world context from metadata instead of reconstructing each turn

### Engine Depth

- [ ] Quest failure states — quests that can be failed, not just completed
- [ ] Reactive NPC triggers — NPCs respond to theft, aggression, and world changes with dialogue or actions
- [ ] Trap system — hazards that fire on room entry, item interaction, or wrong actions
- [ ] Deterministic turn-based combat

### Future Features

- [ ] Author/debug tools (`anyzork inspect`, `anyzork doctor`, playtest/replay)
- [ ] Richer systems: move-count/clock triggers, NPC blockers, deterministic hints

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
| [Design Brief](docs/guides/design-brief.md) | Product framing and the authoring/runtime split |
| [System Architecture](docs/architecture/system-design.md) | Components, commands, and runtime model |
| [Game Design Document](docs/game-design/gdd.md) | Mechanics and design constraints |
| [World Schema](docs/game-design/world-schema.md) | `.zork` database reference |
| [ZorkScript Spec](docs/dsl/zorkscript-spec.md) | Authoring language reference |
| [Command DSL Spec](docs/dsl/command-spec.md) | Runtime rule vocabulary |
| [ADR-001: SQLite Storage](docs/architecture/adrs/adr-001-sqlite-game-storage.md) | Why `.zork` files are SQLite |
| [Implementation Phases](docs/guides/implementation-phases.md) | Roadmap and future work |

## License

MIT
