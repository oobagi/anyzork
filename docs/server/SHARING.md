# Sharing Games

AnyZork games can be shared as portable `.zork` packages, published to the official catalog, or installed from it. This guide covers the full sharing workflow.

## Package format

A `.zork` file is a ZIP archive containing a project manifest and ZorkScript source files:

| Entry | Description |
|---|---|
| `manifest.toml` | Project metadata (title, slug, author, description, source file list). |
| `*.zorkscript` | One or more ZorkScript source files that define the game world. |

On import or play, AnyZork compiles the archive's source files into a SQLite database stored in the compilation cache (`~/.anyzork/cache/`). Share packages uploaded to the catalog use the `anyzork-share-package/v1` format with additional listing metadata and an integrity checksum.

Packages have a 50 MB upload limit on the official catalog.

## Publishing a game

The `publish` command packages a library game and uploads it to the catalog in one step.

```
anyzork publish <game_ref>
```

`<game_ref>` is a library game name (stem of any `.zork` file in `~/.anyzork/games/`) or a path to a `.zork` file. You cannot publish a managed save slot -- only library games or original `.zork` files.

### The publish wizard

After resolving the game file, AnyZork launches an interactive listing wizard. Press Enter to accept the suggested value (pulled from the game's embedded metadata) or type your own.

The wizard prompts for:

- **Public title** -- display name in the catalog.
- **Author** -- your name or handle.
- **Description** -- a longer summary of the game.
- **Tagline** -- a short one-liner shown in browse results.
- **Genres** -- comma-separated genre tags (e.g. `fantasy, horror`).
- **Slug** -- the URL-safe identifier used as the catalog ref (defaults to a slugified version of the title).

After confirming, AnyZork builds the `.zork`, uploads it, and prints the assigned slug.

### What happens after upload

Uploaded games are **not immediately visible** in the catalog. They enter a pending review state. The CLI prints a status check command you can use to follow up:

```
anyzork publish --status <slug>
```

See [Checking publish status](#checking-publish-status) below.

## Checking publish status

```
anyzork publish --status <slug>
```

This queries the catalog API and reports one of two states:

- **Live** -- the game is published and visible in `anyzork browse`.
- **Pending** -- the game is submitted but has not yet been approved.

> **Note:** Moderation and approval are not yet automated. Games submitted to the official catalog are reviewed manually. There is currently no self-service way to expedite review.

## Browsing the catalog

```
anyzork browse
```

This fetches the official catalog at `https://anyzork.com/catalog.json` and displays a table of published games. The table shows each game's ref (slug), title, author, genres, room count, runtime version, and package source.

Featured games sort to the top; everything else is alphabetical by title.

Options:

| Flag | Default | Description |
|---|---|---|
| `--limit N` | 20 | Maximum number of entries to display (1--100). |

The bottom of the output reminds you how to install:

```
Install by ref:  anyzork install <ref>
```

## Installing a game

There are two ways to install a shared game.

### From the catalog

```
anyzork install <ref>
```

Where `<ref>` is the slug shown in `anyzork browse`. AnyZork resolves the slug against the official catalog, downloads the `.zork` from the trusted `anyzork.com` domain, verifies the checksum, and extracts the `.zork` file into your library at `~/.anyzork/games/`.

Remote downloads are restricted to the official catalog domain. Arbitrary URLs are rejected.

### From a local package

```
anyzork install path/to/game.zork
```

This installs directly from a `.zork` file on disk -- useful for games shared outside the catalog (email, file transfer, etc.).

### Options

| Flag | Description |
|---|---|
| `--force` | Replace an existing library game with the same destination name. Without this flag, installing over an existing game is an error. |

After installation, AnyZork prints the play command:

```
anyzork play <game_name>
```

## Environment overrides

Two environment variables let you point the CLI at a different catalog or upload endpoint:

| Variable | Default | Description |
|---|---|---|
| `ANYZORK_CATALOG_URL` | `https://anyzork.com/catalog.json` | Catalog JSON used by `browse` and `install`. |
| `ANYZORK_UPLOAD_URL` | `https://anyzork.com/api/games` | Upload endpoint used by `publish`. |

These are mainly useful for local development or self-hosted catalogs.

## Self-hosted catalogs

AnyZork includes a FastAPI-based catalog server that you can run yourself. It provides:

- `GET /catalog.json` -- public catalog in `anyzork-public-catalog/v1` format.
- `POST /api/games` -- upload endpoint (accepts multipart `.zork` uploads).
- `GET /api/games/<slug>/package` -- download endpoint for published packages.
- `GET /api/games/<slug>/status` -- publish status check.
- `GET /admin` -- admin dashboard (HTML).
- Admin endpoints for publishing/unpublishing games (requires `ANYZORK_ADMIN_TOKEN`).

The server stores packages on disk and tracks metadata in a SQLite database under the configured `public_catalog_dir` (default `~/.anyzork/public_catalog/`).

### Running a self-hosted catalog

The catalog app is defined in `anyzork.catalog_api`. To run it locally:

```
uvicorn anyzork.catalog_api:create_catalog_app --factory --host 0.0.0.0 --port 8000
```

Then point the CLI at your instance:

```
export ANYZORK_CATALOG_URL=http://localhost:8000/catalog.json
export ANYZORK_UPLOAD_URL=http://localhost:8000/api/games
```

### Admin moderation

Uploaded games start unpublished. To approve a game, set the `ANYZORK_ADMIN_TOKEN` environment variable on the server and call the admin publish endpoint:

```
curl -X POST http://localhost:8000/api/admin/games/<slug>/publish \
  -H "X-Admin-Token: $ANYZORK_ADMIN_TOKEN"
```

To unpublish:

```
curl -X POST http://localhost:8000/api/admin/games/<slug>/unpublish \
  -H "X-Admin-Token: $ANYZORK_ADMIN_TOKEN"
```

## Current limitations

- **No automated moderation.** All uploads enter a pending state and require manual approval before they appear in `browse` or can be installed by ref.
- **No authentication for uploaders.** Anyone can submit a package to the upload endpoint. There is no account system or upload tokens yet.
- **No versioning for published games.** Re-uploading with the same slug is rejected unless the server-side store allows replacement. There is no update-in-place flow.
- **Remote installs are domain-locked.** `anyzork install <ref>` only downloads from `anyzork.com` (or subdomains). Packages from other origins must be downloaded manually and installed as local `.zork` files.
- **50 MB upload cap.** The catalog API rejects packages larger than 50 MB.
