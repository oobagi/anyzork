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
| `--report` | Print structured import diagnostics (entity counts, lint findings, compile result). |

```bash
# Paste ZorkScript from clipboard
anyzork import -

# Compile a file
anyzork import game.zorkscript -o mygame.zork

# Print the authoring template
anyzork import --print-template
```

### `lint`

Lint a ZorkScript source file without compiling it.

```
anyzork lint [SPEC_SOURCE]
```

| Option | Description |
|--------|-------------|
| `SPEC_SOURCE` | Path to a ZorkScript file, or `-` (default) to read from stdin. |

Output is lint results grouped by severity with a summary count. Exit code is `0` if no errors are found (warnings are OK), `1` if any errors are present.

```bash
# Lint a file
anyzork lint game.zorkscript

# Lint from stdin
cat game.zorkscript | anyzork lint -
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
| `--slot NAME` | Managed save slot name (default: `default`). |
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
anyzork play haunted-lighthouse --slot speedrun --new

# Play with AI narrator
anyzork play haunted-lighthouse --narrator --provider claude
```

---

## Library Management

### `list`

List library games and summarize their active saves.

```
anyzork list
```

No arguments or options. Displays a table of all library games with ref, title, version, active save count, and latest run timestamp.

### `saves`

List managed save slots.

```
anyzork saves [GAME_REF]
```

| Option | Description |
|--------|-------------|
| `GAME_REF` | Optional. Filter saves to a single library game. |

Shows slot name, game state, score, moves, and last-updated timestamp for each save.

### `delete-save`

Delete a single managed save slot.

```
anyzork delete-save GAME_REF --slot SLOT
```

| Option | Description |
|--------|-------------|
| `GAME_REF` | Library game ref or path. Required. |
| `--slot SLOT` | Save slot name to delete. Required. |

```bash
anyzork delete-save haunted-lighthouse --slot speedrun
```

### `delete`

Delete a library game and all of its managed save slots.

```
anyzork delete GAME_REF [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `GAME_REF` | Library game ref or path. Required. |
| `--yes` | Skip the confirmation prompt. |

```bash
anyzork delete haunted-lighthouse
anyzork delete haunted-lighthouse --yes
```

---

## Sharing & Catalog

### `publish`

Package and upload a library game to the official catalog.

```
anyzork publish GAME_REF
```

| Option | Description |
|--------|-------------|
| `GAME_REF` | Library game ref or path. Required. Must not be a managed save. |

Launches an interactive listing wizard (title, author, description, tagline, genres, slug) before uploading. The game is submitted for review.

### `status`

Check the publish status of a submitted game.

```
anyzork status SLUG
```

| Option | Description |
|--------|-------------|
| `SLUG` | The catalog slug assigned during publish. Required. |

```bash
anyzork status haunted-lighthouse
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

Install a game from the official catalog or a local `.anyzorkpkg` package into the library.

```
anyzork install SOURCE [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `SOURCE` | Catalog slug/ref or path to a local `.anyzorkpkg` file. Required. |
| `--force` | Replace an existing library game with the same destination name. |

```bash
# Install from catalog by ref
anyzork install haunted-lighthouse

# Install from a local package
anyzork install ./mygame.anyzorkpkg --force
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANYZORK_UPLOAD_URL` | Override the default catalog upload endpoint. |
| `ANYZORK_CATALOG_URL` | Override the default catalog browse endpoint. |
| `ANYZORK_PROVIDER` | Default LLM provider for narrator mode (`claude`, `openai`, `gemini`). |
