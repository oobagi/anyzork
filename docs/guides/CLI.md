# CLI Reference

AnyZork CLI for deterministic Zork-style adventure authoring and play.

```
anyzork [OPTIONS] COMMAND [ARGS]
```

Global options:

| Flag | Description |
|------|-------------|
| `--version` | Show version (app version, runtime compat version, prompt system version) and exit. |
| `--help` | Show help and exit. |

---

## Authoring

### `generate`

Build a ZorkScript authoring prompt for a new game. The output is a prompt you send to an LLM; the LLM returns ZorkScript you then compile with `import`.

```
anyzork generate [PROMPT] [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `PROMPT` | Freeform world description. If omitted, the interactive wizard launches. |
| `--guided` | Launch the interactive prompt builder wizard. |
| `--preset NAME` | Load a genre preset (e.g., `fantasy-dungeon`, `zombie-survival`). |
| `--list-presets` | List available presets and exit. |
| `--no-edit` | With `--preset`, skip the wizard and generate immediately. |
| `-o, --output PATH` | Write the authoring prompt to a file instead of stdout. |
| `--realism LEVEL` | Realism level: `low`, `medium` (default), or `high`. |

```bash
# Freeform prompt to stdout
anyzork generate "haunted lighthouse on a cliff"

# Interactive wizard
anyzork generate --guided

# Preset, no wizard, saved to file
anyzork generate --preset zombie-survival --no-edit -o prompt.txt
```

### `import`

Compile ZorkScript into a `.zork` game file and add it to the library.

```
anyzork import [SPEC_SOURCE] [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `SPEC_SOURCE` | Path to a ZorkScript file, or `-` (default) to read from stdin. |
| `-o, --output PATH` | Output path for the `.zork` file. |
| `--print-template` | Print the ZorkScript authoring template and exit. |

```bash
# Paste ZorkScript from clipboard
anyzork import -

# Compile a file
anyzork import game.zorkscript -o mygame.zork

# Print the authoring template
anyzork import --print-template
```

### `repair`

Diagnose ZorkScript errors, generate an LLM fix prompt, and optionally paste back the corrected output to re-import. The fix prompt is copied to the clipboard when possible.

```
anyzork repair [SOURCE]
```

| Option | Description |
|--------|-------------|
| `SOURCE` | Path to a ZorkScript file, project directory, or `-` (default) to read from stdin. |

When run interactively, the command prints diagnostics, copies a fix prompt to the clipboard, and waits for the user to paste the corrected LLM response. The pasted output is saved and automatically re-imported.

```bash
# Diagnose and repair a file
anyzork repair game.zorkscript

# Diagnose a project directory
anyzork repair my-game/

# Diagnose from stdin
cat game.zorkscript | anyzork repair -
```

---

## Playing

### `play`

Play a library game or an existing `.zork` file.

```
anyzork play [GAME_REF] [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `GAME_REF` | Library ref, game title slug, game ID, or path to a `.zork` file. If omitted, an interactive game picker is shown. |
| `--save NAME` | Managed save slot name (default: `default`). |
| `--new` | Start the save slot over from the library copy. |
| `--narrator` | Enable narrator mode (requires an LLM API key). |
| `--provider PROVIDER` | LLM provider for narrator mode: `claude`, `openai`, or `gemini`. Overrides `ANYZORK_PROVIDER`. |
| `--model MODEL` | Model name for narrator mode. |

```bash
# Pick a game interactively
anyzork play

# Play by library ref
anyzork play haunted-lighthouse

# Start a new run in a named slot
anyzork play haunted-lighthouse --save speedrun --new

# Play with AI narrator
anyzork play haunted-lighthouse --narrator --provider claude
```

---

## Environment

### `doctor`

Run health checks on the local anyzork environment. Scans for orphaned save directories (saves whose source game has been removed from the library) and empty save directories.

```
anyzork doctor [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--fix` | Auto-clean issues found (delete orphaned/empty save dirs). |

```bash
# Check for issues
anyzork doctor

# Auto-fix issues
anyzork doctor --fix
```

### `narrator`

View and configure narrator settings. On first run (no API key configured), launches a setup wizard. When a key is already configured, shows current settings and a menu to change provider, model, API key, or toggle narrator on/off.

```
anyzork narrator
```

No options. All configuration is done through the interactive menu.

```bash
# First-time setup (walks through provider choice, API key, enable toggle)
anyzork narrator

# Reconfigure (shows current settings, offers change menu)
anyzork narrator
```

---

## Library Management

### `list`

List library games and summarize their active saves.

```
anyzork list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--saves` | Show managed saves instead of the games table. |

Without `--saves`, displays a table of all library games with ref, title, version, active save count, and latest run timestamp. With `--saves`, shows managed save slots with game ref, title, save name, game state, score, moves, and last-updated timestamp.

### `delete`

Delete a library game and all of its managed save slots.

```
anyzork delete GAME_REF [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `GAME_REF` | Library game ref or path. Required. |
| `--save NAME` | Delete only this save slot instead of the whole game. |
| `--yes` | Skip the confirmation prompt. |

```bash
anyzork delete haunted-lighthouse
anyzork delete haunted-lighthouse --yes
anyzork delete haunted-lighthouse --save speedrun
```

---

## Sharing & Catalog

### `publish`

Package and upload a library game to the official catalog.

```
anyzork publish GAME_REF [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `GAME_REF` | Library game ref or path. Required (unless using `--status`). Must not be a managed save. |
| `--status SLUG` | Check the publish status of a previously submitted game by its catalog slug. |

Launches an interactive listing wizard (title, author, description, tagline, genres, slug) before uploading. The game is submitted for review.

```bash
# Publish a game
anyzork publish haunted-lighthouse

# Check publish status
anyzork publish --status haunted-lighthouse
```

### `browse`

Browse the official AnyZork game catalog.

```
anyzork browse [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--limit N` | Maximum entries to display, 1--100 (default: `20`). |

### `install`

Install a game from the official catalog or a local `.zork` package into the library.

```
anyzork install SOURCE [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `SOURCE` | Catalog slug/ref or path to a local `.zork` package. Required. |
| `--force` | Replace an existing library game with the same destination name. |

```bash
# Install from catalog by ref
anyzork install haunted-lighthouse

# Install from a local package
anyzork install ./mygame.zork --force
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANYZORK_UPLOAD_URL` | Override the default catalog upload endpoint. |
| `ANYZORK_CATALOG_URL` | Override the default catalog browse endpoint. |
| `ANYZORK_PROVIDER` | Default LLM provider for narrator mode (`claude`, `openai`, `gemini`). |
