"""AnyZork CLI — click entry point."""

from __future__ import annotations

import contextlib
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar
from urllib.parse import urlparse
from uuid import uuid4

import click
from rich.console import Console

from anyzork import __version__
from anyzork.config import (
    Config,
)
from anyzork.importer import current_prompt_system_version
from anyzork.services import importing as importing_service
from anyzork.services import library as library_service
from anyzork.sharing import (
    OFFICIAL_CATALOG_URL,
    OFFICIAL_UPLOAD_URL,
    SHARE_PACKAGE_SUFFIX,
    SharePackageError,
)
from anyzork.versioning import RUNTIME_COMPAT_VERSION

console = Console()
CLI_VERSION = (
    f"{__version__} "
    f"(runtime {RUNTIME_COMPAT_VERSION}, prompt {current_prompt_system_version()})"
)
T = TypeVar("T")

if TYPE_CHECKING:
    from anyzork.db.schema import GameDB


def _share_metadata_options(func: Callable[..., object]) -> Callable[..., object]:
    """Add public share-metadata options to a CLI command."""
    options = [
        click.option("--title", type=str, default=None, help="Public title override."),
        click.option("--author", type=str, default=None, help="Public author name."),
        click.option("--description", type=str, default=None, help="Public description."),
        click.option("--tagline", type=str, default=None, help="Short public tagline."),
        click.option(
            "--genre",
            "genres",
            multiple=True,
            help="Public genre tag. Repeat for multiple values.",
        ),
        click.option("--slug", type=str, default=None, help="Public catalog slug override."),
        click.option("--homepage-url", type=str, default=None, help="Public homepage URL."),
        click.option("--cover-image-url", type=str, default=None, help="Public cover image URL."),
    ]
    wrapped = func
    for option in reversed(options):
        wrapped = option(wrapped)
    return wrapped


@click.group()
@click.version_option(version=CLI_VERSION, prog_name="anyzork")
def cli() -> None:
    """AnyZork -- deterministic Zork-style adventure authoring and play."""


@cli.command()
@click.argument("game_ref", type=str, required=False)
@click.option(
    "--slot",
    type=str,
    default="default",
    show_default=True,
    help="Managed save slot name. Progress is written to ~/.anyzork/saves/<game>/<slot>.zork.",
)
@click.option(
    "--new",
    "restart",
    is_flag=True,
    help="Start the selected managed save slot over from the library copy.",
)
@click.option(
    "--restart",
    "restart",
    is_flag=True,
    hidden=True,
)
@click.option(
    "--direct",
    is_flag=True,
    help="Play the given .zork file directly instead of using a managed save slot.",
)
@click.option("--narrator", is_flag=True, help="Enable narrator mode (requires API key).")
@click.option(
    "--provider",
    type=click.Choice(["claude", "openai", "gemini"], case_sensitive=False),
    default=None,
    help="LLM provider for narrator mode (overrides ANYZORK_PROVIDER).",
)
@click.option("--model", type=str, default=None, help="Model for narrator mode.")
def play(
    game_ref: str | None,
    slot: str,
    restart: bool,
    direct: bool,
    narrator: bool,
    provider: str | None,
    model: str | None,
) -> None:
    """Play a library game or existing .zork file."""
    from anyzork.db.schema import GameDB
    from anyzork.engine.game import GameEngine

    if direct and restart:
        raise click.UsageError("--restart cannot be used with --direct.")
    if direct and not game_ref:
        raise click.UsageError("--direct requires GAME_REF.")

    # Also check the ANYZORK_NARRATOR env var / config.
    cfg: Config | None = None
    narrator_enabled = narrator
    if not narrator_enabled:
        try:
            cfg = Config()
            narrator_enabled = cfg.narrator_enabled
        except Exception:
            pass

    if cfg is None:
        cfg = Config()

    if game_ref:
        source_path = library_service.resolve_game_reference(game_ref, cfg)
    else:
        source_path = _prompt_for_play_target(cfg)
        if source_path is None:
            return

    if library_service.is_within(source_path, cfg.saves_dir):
        if restart:
            raise click.UsageError(
                "--new only works for library games or original .zork files, not an existing save."
            )
        play_path = source_path
        console.print(f"[dim]Resuming save:[/dim] [cyan]{play_path}[/cyan]")
    elif direct:
        play_path = source_path
    else:
        play_path, action = library_service.prepare_managed_save(source_path, slot, restart, cfg)
        action_label = {
            "created": "Started save slot",
            "reset": "Restarted save slot",
            "resume": "Resuming save slot",
        }[action]
        console.print(
            f"[dim]{action_label}[/dim] [cyan]{slot}[/cyan] "
            f"[dim]for[/dim] [cyan]{source_path.stem}[/cyan]"
        )
        console.print(f"[dim]Save path:[/dim] [cyan]{play_path}[/cyan]")

    with GameDB(play_path) as db:
        try:
            db.touch_last_played()
            engine = GameEngine(
                db,
                narrator_enabled=narrator_enabled,
                narrator_provider=provider,
                narrator_model=model,
            )
            engine.start()
        except KeyboardInterrupt:
            console.print("\nFarewell, adventurer.", style="dim italic")


def _prompt_for_play_target(cfg: Config) -> Path | None:
    """Prompt for a library game when `play` is launched without a target."""
    from rich.table import Table

    overview = library_service.list_library_overview(cfg)
    if not overview.games:
        console.print(
            f"[dim]No library games found in {cfg.games_dir}[/dim]"
        )
        if overview.saves:
            console.print("[dim]Use anyzork saves to inspect existing save files.[/dim]")
            console.print("[dim]Or pass a direct .zork path to anyzork play.[/dim]")
            return None
        console.print("[dim]Create an authoring prompt with:[/dim]  anyzork generate")
        console.print("[dim]Then compile returned ZorkScript with:[/dim]  anyzork import -")
        return None

    entries: list[Path] = []
    table = Table(title="Choose A Game", show_lines=False)
    table.add_column("#", style="cyan", no_wrap=True)
    table.add_column("Ref", style="cyan", no_wrap=True)
    table.add_column("Title", style="bold")
    table.add_column("Active Saves", justify="right", style="green")

    for game in overview.games:
        entries.append(game.path)
        table.add_row(
            str(len(entries)),
            game.ref,
            game.title,
            str(game.active_saves),
        )

    console.print(table)

    while True:
        choice = click.prompt("Choose a game number", type=str).strip().lower()
        if choice in {"q", "quit", "exit"}:
            console.print("[dim]Canceled.[/dim]")
            return None

        try:
            index = int(choice)
        except ValueError:
            console.print("[dim]Enter one of the numbers above, or q to cancel.[/dim]")
            continue

        if 1 <= index <= len(entries):
            return entries[index - 1]

        console.print("[dim]Enter one of the numbers above, or q to cancel.[/dim]")


def _slugify_name(value: str) -> str:
    """Return a filesystem-friendly slug for save directories / slots."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "game"


def _sanitize_slot_name(value: str) -> str:
    """Return a save-slot filename stem while preserving readable punctuation."""
    slot = value.strip().replace("/", "_").replace("\\", "_")
    return slot or "default"


def _copy_zork_file(source: Path, destination: Path) -> None:
    """Copy a .zork file to a new location, replacing old sidecars first."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    Path(f"{destination}-wal").unlink(missing_ok=True)
    Path(f"{destination}-shm").unlink(missing_ok=True)
    shutil.copy2(source, destination)


def _is_within(path: Path, root: Path) -> bool:
    """Return True when path lives underneath root."""
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _read_zork_metadata(path: Path) -> dict | None:
    """Return metadata for a .zork file, or None on read errors."""
    return _read_game_data(path, lambda db: db.get_all_meta())


def _read_player_state(path: Path) -> dict | None:
    """Return player state for a .zork file, or None on read errors."""
    return _read_game_data(path, lambda db: db.get_player())


def _read_game_data(path: Path, reader: Callable[[GameDB], T]) -> T | None:
    """Read derived data from a .zork file while tolerating failures."""
    from anyzork.db.schema import GameDB

    try:
        with GameDB(path) as db:
            return reader(db)
    except Exception:
        return None


def _save_last_played_timestamp(path: Path) -> str:
    """Return the raw last-played timestamp used for save ordering."""
    return str((_read_zork_metadata(path) or {}).get("last_played_at") or "")


def _format_save_last_played(path: Path) -> str:
    """Return a compact display string for the save timestamp."""
    timestamp = _save_last_played_timestamp(path)
    return timestamp[:16].replace("T", " ") if timestamp else ""


def _sorted_save_files(save_dir: Path) -> list[Path]:
    """Return save files sorted by descending last-played timestamp."""
    return sorted(save_dir.glob("*.zork"), key=_save_last_played_timestamp, reverse=True)


def _format_metadata_versions(meta: dict | None) -> str:
    """Format runtime and prompt-system versions for library/save displays."""
    if not meta:
        return "?"

    runtime_version = str(meta.get("version") or "?")
    prompt_version = meta.get("prompt_system_version")
    if prompt_version:
        return f"{runtime_version} / {prompt_version}"
    return runtime_version


def _resolve_game_reference(game_ref: str, cfg: Config) -> Path:
    """Resolve a CLI game reference to a concrete .zork path."""
    candidate = Path(game_ref).expanduser()
    if candidate.exists():
        return candidate.resolve()

    direct_name = candidate.name if candidate.name.endswith(".zork") else f"{candidate.name}.zork"
    direct_library_path = (cfg.games_dir / direct_name).resolve()
    if direct_library_path.exists():
        return direct_library_path

    library_matches: list[Path] = []
    target_slug = _slugify_name(candidate.stem)
    for zork_path in sorted(cfg.games_dir.glob("*.zork")):
        meta = _read_zork_metadata(zork_path) or {}
        if game_ref == meta.get("game_id"):
            return zork_path.resolve()
        if zork_path.stem == candidate.stem:
            library_matches.append(zork_path.resolve())
            continue
        if _slugify_name(str(meta.get("title", ""))) == target_slug:
            library_matches.append(zork_path.resolve())

    if len(library_matches) == 1:
        return library_matches[0]
    if len(library_matches) > 1:
        raise click.BadParameter(
            f"Multiple library games match '{game_ref}'. Use an explicit path.",
            param_hint="game_ref",
        )

    raise click.BadParameter(
        f"No game found for '{game_ref}'. Use 'anyzork list' or pass a .zork path.",
        param_hint="game_ref",
    )


def _prepare_managed_save(
    source_path: Path,
    slot: str,
    restart: bool,
    cfg: Config,
) -> tuple[Path, str]:
    """Return the managed save path for a source game, cloning when needed."""
    from anyzork.db.schema import GameDB

    source_meta = _read_zork_metadata(source_path) or {}
    source_game_id = source_meta.get("game_id") or _slugify_name(source_path.stem)
    slot_slug = _sanitize_slot_name(slot)
    save_path = cfg.saves_dir / source_game_id / f"{slot_slug}.zork"

    if restart or not save_path.exists():
        _copy_zork_file(source_path, save_path)
        with GameDB(save_path) as db:
            db.set_meta("game_id", str(uuid4()))
            db.set_meta("source_game_id", str(source_game_id))
            db.set_meta("source_path", str(source_path))
            db.set_meta("save_slot", slot)
            db.set_meta("is_template", 0)
            db.touch_last_played()
        return save_path, "reset" if restart else "created"

    with GameDB(save_path) as db:
        db.set_meta("save_slot", slot)
        db.touch_last_played()
    return save_path, "resume"


def _library_game_id(path: Path) -> str | None:
    """Return the stable library game id for a .zork file."""
    meta = _read_zork_metadata(path) or {}
    game_id = meta.get("game_id")
    return str(game_id) if game_id else None


def _normalize_genres(genres: tuple[str, ...]) -> list[str] | None:
    """Return clean genre values or None when no overrides were supplied."""
    cleaned = [genre.strip() for genre in genres if genre.strip()]
    return cleaned or None


def _normalize_optional_text(value: str | None) -> str | None:
    """Return stripped text or None when empty."""
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _prompt_optional_text(label: str, default: str | None = None) -> str | None:
    """Prompt for an optional single-line text field."""
    prompt_default = default or ""
    value = click.prompt(label, default=prompt_default, show_default=bool(default), type=str)
    return _normalize_optional_text(value)


def _prompt_optional_genres(default: list[str] | None = None) -> list[str] | None:
    """Prompt for optional comma-separated genre tags."""
    default_text = ", ".join(default or [])
    raw_value = click.prompt(
        "Genre tags (comma-separated)",
        default=default_text,
        show_default=bool(default_text),
        type=str,
    )
    values = [genre.strip() for genre in raw_value.split(",") if genre.strip()]
    return values or None


def _resolve_publish_listing_metadata(
    source_path: Path,
    *,
    guided: bool,
    title: str | None,
    author: str | None,
    description: str | None,
    tagline: str | None,
    genres: tuple[str, ...],
    slug: str | None,
    homepage_url: str | None,
    cover_image_url: str | None,
) -> tuple[
    str | None,
    str | None,
    str | None,
    str | None,
    list[str] | None,
    str | None,
    str | None,
    str | None,
]:
    """Return resolved public listing metadata for ``publish``."""
    from anyzork.sharing import build_share_manifest

    normalized_title = _normalize_optional_text(title)
    normalized_author = _normalize_optional_text(author)
    normalized_description = _normalize_optional_text(description)
    normalized_tagline = _normalize_optional_text(tagline)
    normalized_genres = _normalize_genres(genres)
    normalized_slug = _normalize_optional_text(slug)
    normalized_homepage_url = _normalize_optional_text(homepage_url)
    normalized_cover_image_url = _normalize_optional_text(cover_image_url)

    if not guided:
        return (
            normalized_title,
            normalized_author,
            normalized_description,
            normalized_tagline,
            normalized_genres,
            normalized_slug,
            normalized_homepage_url,
            normalized_cover_image_url,
        )

    manifest = build_share_manifest(source_path)
    listing = dict(manifest.get("listing", {}))
    title_default = normalized_title or str(listing.get("title") or source_path.stem)
    author_default = normalized_author or str(listing.get("author") or "")
    description_default = normalized_description or str(listing.get("description") or "")
    tagline_default = normalized_tagline or str(listing.get("tagline") or "")
    genres_default = normalized_genres or [
        str(genre).strip() for genre in listing.get("genres", []) if str(genre).strip()
    ]
    homepage_default = normalized_homepage_url or str(listing.get("homepage_url") or "")
    cover_default = normalized_cover_image_url or str(listing.get("cover_image_url") or "")

    console.print("[bold]Publish Listing[/bold]")
    console.print("[dim]Press enter to keep a suggested value, or type your own.[/dim]")

    resolved_title = _prompt_optional_text("Public title", title_default) or title_default
    resolved_author = _prompt_optional_text("Author", author_default)
    resolved_description = _prompt_optional_text("Description", description_default)
    resolved_tagline = _prompt_optional_text("Tagline", tagline_default)
    resolved_genres = _prompt_optional_genres(genres_default)
    resolved_slug = _prompt_optional_text(
        "Slug",
        normalized_slug or _slugify_name(resolved_title or source_path.stem),
    )
    resolved_homepage = _prompt_optional_text("Homepage URL", homepage_default)
    resolved_cover = _prompt_optional_text("Cover image URL", cover_default)

    return (
        resolved_title,
        resolved_author,
        resolved_description,
        resolved_tagline,
        resolved_genres,
        resolved_slug,
        resolved_homepage,
        resolved_cover,
    )


@cli.command("publish")
@click.argument("game_ref", type=str)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output path for the share package.",
)
@click.option("--guided", is_flag=True, help="Launch an interactive listing wizard.")
@_share_metadata_options
def publish_game(
    game_ref: str,
    output: Path | None,
    guided: bool,
    title: str | None,
    author: str | None,
    description: str | None,
    tagline: str | None,
    genres: tuple[str, ...],
    slug: str | None,
    homepage_url: str | None,
    cover_image_url: str | None,
) -> None:
    """Package a library game into a shareable archive."""
    from anyzork.sharing import create_share_package

    cfg = Config()
    source_path = _resolve_game_reference(game_ref, cfg)
    if _is_within(source_path, cfg.saves_dir):
        raise click.BadParameter(
            "Publish a library game or original .zork file, not a managed save slot.",
            param_hint="game_ref",
        )

    if output is None:
        output = Path.cwd() / f"{source_path.stem}{SHARE_PACKAGE_SUFFIX}"

    (
        title,
        author,
        description,
        tagline,
        genre_values,
        slug,
        homepage_url,
        cover_image_url,
    ) = _resolve_publish_listing_metadata(
        source_path,
        guided=guided,
        title=title,
        author=author,
        description=description,
        tagline=tagline,
        genres=genres,
        slug=slug,
        homepage_url=homepage_url,
        cover_image_url=cover_image_url,
    )

    try:
        package_path, manifest = create_share_package(
            source_path,
            output,
            title=title,
            author=author,
            description=description,
            tagline=tagline,
            genres=genre_values,
            slug=slug,
            homepage_url=homepage_url,
            cover_image_url=cover_image_url,
        )
    except SharePackageError as exc:
        console.print(f"[red]Publish failed:[/red] {exc}")
        sys.exit(1)

    listing_title = str(
        manifest.get("listing", {}).get("title")
        or manifest.get("game", {}).get("title")
        or source_path.stem
    )
    console.print(
        f"[bold green]Packaged[/bold green] [cyan]{listing_title}[/cyan] "
        f"[dim]to[/dim] [cyan]{package_path}[/cyan]"
    )
    console.print(f"[dim]Upload it with:[/dim]  anyzork upload {package_path}")
    console.print(f"[dim]Install-test it with:[/dim]  anyzork install {package_path}")


@cli.command("upload")
@click.argument("source", type=str)
@_share_metadata_options
def upload_game(
    source: str,
    title: str | None,
    author: str | None,
    description: str | None,
    tagline: str | None,
    genres: tuple[str, ...],
    slug: str | None,
    homepage_url: str | None,
    cover_image_url: str | None,
) -> None:
    """Upload a shared game package to the public catalog service."""
    from anyzork.sharing import upload_share_package

    genre_values = _normalize_genres(genres)
    package_path = Path(source).expanduser()
    if not package_path.exists() or package_path.suffix != SHARE_PACKAGE_SUFFIX:
        raise click.BadParameter(
            "Upload expects a .anyzorkpkg package. Run 'anyzork publish <game>' first.",
            param_hint="source",
        )

    package_path = package_path.resolve()

    try:
        payload = upload_share_package(
            package_path,
            OFFICIAL_UPLOAD_URL,
            title=title,
            author=author,
            description=description,
            tagline=tagline,
            genres=genre_values,
            slug=slug,
            homepage_url=homepage_url,
            cover_image_url=cover_image_url,
        )
    except SharePackageError as exc:
        console.print(f"[red]Upload failed:[/red] {exc}")
        sys.exit(1)

    game = dict(payload.get("game") or {})
    uploaded_title = str(game.get("title") or title or source)
    uploaded_slug = str(game.get("slug") or "")
    console.print(
        f"[bold green]Uploaded[/bold green] [cyan]{uploaded_title}[/cyan]"
        + (f" [dim]as[/dim] [cyan]{uploaded_slug}[/cyan]" if uploaded_slug else "")
    )
    console.print(f"[dim]Install it with:[/dim]  anyzork install {uploaded_slug or '<slug>'}")


@cli.command("import")
@click.argument("spec_source", required=False, default="-")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output path for the imported .zork file.",
)
@click.option(
    "--print-template",
    is_flag=True,
    help="Print the public AnyZork ZorkScript authoring template and exit.",
)
def import_game(spec_source: str, output: Path | None, print_template: bool) -> None:
    """Compile ZorkScript into a .zork game."""
    from anyzork.importer import ZORKSCRIPT_AUTHORING_TEMPLATE, ImportSpecError, load_import_source

    if print_template:
        console.print(ZORKSCRIPT_AUTHORING_TEMPLATE)
        return

    cfg = Config()
    resolved_source = _resolve_import_source(spec_source)

    try:
        spec = load_import_source(resolved_source)
    except ImportSpecError as exc:
        console.print(f"[red]Import failed:[/red] {exc}")
        sys.exit(1)

    try:
        result = importing_service.import_zorkscript_spec(
            spec=spec,
            output_path=output,
            cfg=cfg,
        )
    except ImportSpecError as exc:
        console.print(f"[red]Import failed:[/red] {exc}")
        sys.exit(1)
    except Exception as exc:
        console.print(f"[red]Import failed:[/red] {exc}")
        sys.exit(1)

    result_path = result.output_path
    warnings = result.warnings

    console.print(
        "[bold green]Done![/bold green] Imported game saved to "
        f"[cyan]{result_path}[/cyan]"
    )
    if warnings:
        console.print(f"[yellow]Imported with {len(warnings)} warning(s):[/yellow]")
        for warning in warnings[:8]:
            console.print(f"  [yellow]-[/yellow] {warning}")
        if len(warnings) > 8:
            console.print(f"  [dim]...and {len(warnings) - 8} more[/dim]")

    play_ref = result_path
    if result_path.parent.resolve() == cfg.games_dir.resolve():
        play_ref = result_path.stem
    console.print(f"[dim]Play it with:[/dim]  anyzork play {play_ref}")


@cli.command("install")
@click.argument("source", type=str)
@click.option(
    "--force",
    is_flag=True,
    help="Replace an existing installed library game with the same destination name.",
)
def install_game(source: str, force: bool) -> None:
    """Install an official catalog game or local shared package into the library."""
    from anyzork.sharing import install_shared_game, resolve_catalog_game_source

    cfg = Config()
    resolved_source = source
    catalog_game: dict[str, object] | None = None
    allow_remote = False

    if _looks_like_catalog_ref(source):
        try:
            resolved_source, catalog_game = resolve_catalog_game_source(
                OFFICIAL_CATALOG_URL,
                source,
            )
            allow_remote = True
        except SharePackageError as exc:
            console.print(f"[red]Install failed:[/red] {exc}")
            sys.exit(1)
    else:
        source_path = Path(source).expanduser()
        if not source_path.exists() or source_path.suffix != SHARE_PACKAGE_SUFFIX:
            raise click.BadParameter(
                "Install expects an official catalog ref or a local .anyzorkpkg package.",
                param_hint="source",
            )
        resolved_source = str(source_path.resolve())

    try:
        installed_path, manifest = install_shared_game(
            resolved_source,
            cfg.games_dir,
            force=force,
            allow_remote=allow_remote,
        )
    except SharePackageError as exc:
        console.print(f"[red]Install failed:[/red] {exc}")
        sys.exit(1)

    title = str(manifest.get("game", {}).get("title") or installed_path.stem)
    if catalog_game and catalog_game.get("title"):
        title = str(catalog_game["title"])
    console.print(
        f"[bold green]Installed[/bold green] [cyan]{title}[/cyan] "
        f"[dim]to[/dim] [cyan]{installed_path}[/cyan]"
    )
    console.print(f"[dim]Play it with:[/dim]  anyzork play {installed_path.stem}")


@cli.command("browse")
@click.option(
    "--limit",
    type=click.IntRange(1, 100),
    default=20,
    show_default=True,
    help="Maximum number of catalog entries to display.",
)
def browse_games(limit: int) -> None:
    """Browse the official AnyZork game catalog."""
    from rich.table import Table

    from anyzork.sharing import load_public_catalog

    try:
        catalog = load_public_catalog(OFFICIAL_CATALOG_URL)
    except SharePackageError as exc:
        console.print(f"[red]Browse failed:[/red] {exc}")
        sys.exit(1)

    games = sorted(
        catalog["games"],
        key=lambda game: (
            not bool(game.get("featured")),
            str(game.get("title") or "").lower(),
        ),
    )
    games = games[:limit]
    if not games:
        console.print("[dim]No published games found right now.[/dim]")
        return

    if catalog.get("title"):
        console.print(f"[bold]{catalog['title']}[/bold]")
    if catalog.get("updated_at"):
        console.print(f"[dim]Updated:[/dim] {catalog['updated_at']}")
    console.print()

    table = Table(show_lines=False)
    table.add_column("Ref", style="cyan", no_wrap=True)
    table.add_column("Title", style="bold")
    table.add_column("Author", style="magenta")
    table.add_column("Genres", style="green")
    table.add_column("Rooms", justify="right", style="yellow")
    table.add_column("Runtime", style="dim")
    table.add_column("Package", style="dim")

    for game in games:
        genres = ", ".join(game.get("genres", [])) or "-"
        package_source = str(game.get("package_url") or "")
        parsed_source = urlparse(package_source)
        if parsed_source.scheme in {"http", "https"} and parsed_source.netloc:
            package_name = Path(parsed_source.path).name
            package_label = (
                f"{parsed_source.netloc}/{package_name}" if package_name else parsed_source.netloc
            )
        else:
            package_label = Path(package_source).name or package_source
        title = str(game.get("title") or "")
        if game.get("featured"):
            title = f"{title} [dim](featured)[/dim]"
        table.add_row(
            str(game.get("slug") or ""),
            title,
            str(game.get("author") or "-"),
            genres,
            str(game.get("room_count") or 0),
            str(game.get("runtime_compat_version") or "-"),
            package_label,
        )

    console.print(table)
    console.print()
    console.print("[dim]Install by ref:[/dim]  anyzork install <ref>")


def _looks_like_catalog_ref(value: str) -> bool:
    """Return True when a CLI install source should be treated as a catalog slug/ref."""
    if Path(value).expanduser().exists():
        return False

    parsed = urlparse(value)
    if parsed.scheme and parsed.scheme != "file":
        return False

    suffixes = {".zork", ".anyzorkpkg", ".json"}
    if Path(value).suffix.lower() in suffixes:
        return False

    return not ("/" in value or "\\" in value)


def _resolve_import_source(spec_source: str) -> str:
    """Resolve a CLI import source argument to a file path or stdin marker.

    Returns the file path string if the source resolves to an existing file,
    or ``"-"`` for stdin input.  When stdin is a TTY, prints a helper prompt.
    """
    source = spec_source.strip()
    if source in {"", "-"}:
        if sys.stdin.isatty():
            console.print(
                "[dim]Paste your ZorkScript spec, then press Ctrl-D.[/dim]"
            )
        return "-"

    candidate = Path(source).expanduser()
    if candidate.exists():
        return str(candidate)

    return source


def _write_authoring_prompt(
    authoring_prompt: str,
    *,
    output: Path | None,
) -> None:
    """Write or print an external authoring prompt."""
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(authoring_prompt, encoding="utf-8")
        console.print(
            "[bold green]Done![/bold green] Authoring prompt saved to "
            f"[cyan]{output}[/cyan]"
        )
        console.print(
            "[dim]Send that prompt to your LLM, then import the returned "
            "ZorkScript with:[/dim]"
        )
        console.print("[dim]  anyzork import -[/dim]")
        return

    sys.stdout.write(authoring_prompt)
    if not authoring_prompt.endswith("\n"):
        sys.stdout.write("\n")


@cli.command()
@click.argument("prompt", required=False, default=None)
@click.option("--guided", is_flag=True, help="Launch the interactive prompt builder wizard.")
@click.option(
    "--preset",
    type=str,
    default=None,
    help="Load a genre preset (e.g., fantasy-dungeon, zombie-survival).",
)
@click.option("--list-presets", is_flag=True, help="List available presets and exit.")
@click.option(
    "--no-edit",
    is_flag=True,
    help="With --preset, skip the wizard and generate immediately.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the external authoring prompt to a file instead of stdout.",
)
@click.option(
    "--realism",
    type=click.Choice(["low", "medium", "high"]),
    default="medium",
    help="Realism level to request in the external authoring prompt.",
)
def generate(
    prompt: str | None,
    guided: bool,
    preset: str | None,
    list_presets: bool,
    no_edit: bool,
    output: Path | None,
    realism: str,
) -> None:
    """Build a ZorkScript authoring prompt for a new AnyZork game.

    \b
    Usage modes:
      anyzork generate "prompt"          Build a ZorkScript authoring prompt
      anyzork generate                   Launch the interactive wizard
      anyzork generate --guided          Launch the wizard explicitly
      anyzork generate --preset zombie-survival   Load a preset, preview, confirm
      anyzork generate --list-presets    List available presets
    """
    from anyzork.importer import build_zorkscript_prompt

    # ── List presets and exit ──────────────────────────────────────────
    if list_presets:
        from anyzork.wizard.presets import list_presets as _list_presets

        _list_presets(console)
        return

    # ── Resolve prompt: freeform, wizard, or preset ────────────────────
    resolved = _resolve_generation_inputs(prompt, guided, preset, no_edit, console)
    if resolved is None:
        # User quit the wizard or Ctrl+C.
        sys.exit(0)
    resolved_prompt, resolved_realism, authoring_fields = resolved
    realism = resolved_realism or realism

    authoring_prompt = build_zorkscript_prompt(
        resolved_prompt,
        realism=realism,
        authoring_fields=authoring_fields,
    )
    _write_authoring_prompt(authoring_prompt, output=output)


def _resolve_generation_inputs(
    prompt: str | None,
    guided: bool,
    preset_name: str | None,
    no_edit: bool,
    console: Console,
) -> tuple[str, str | None, dict[str, object]] | None:
    """Determine the final prompt string and realism based on CLI arguments.

    Returns ``(prompt, realism_override, authoring_fields)`` or ``None`` if the user quit.
    """
    from anyzork.wizard import run_wizard
    from anyzork.wizard.assembler import assemble_prompt
    from anyzork.wizard.presets import load_preset

    # Case 1: Preset mode.
    if preset_name is not None:
        preset_fields = load_preset(preset_name)
        if preset_fields is None:
            console.print(f"[red]Unknown preset: '{preset_name}'[/red]")
            console.print("[dim]Use --list-presets to see available presets.[/dim]")
            sys.exit(1)

        if no_edit:
            # Skip wizard, generate immediately from preset values.
            return assemble_prompt(preset_fields), preset_fields.get("realism"), preset_fields

        # Launch wizard with preset values pre-filled.
        return run_wizard(console, preset=preset_fields)

    # Case 2: Freeform prompt provided without --guided.
    if prompt is not None and not guided:
        return prompt, None, {"world_description": prompt}

    # Case 3: Freeform prompt provided WITH --guided — seed the wizard.
    if prompt is not None and guided:
        return run_wizard(console, initial_prompt=prompt)

    # Case 4: No prompt, --guided flag or no arguments at all — launch wizard.
    # In non-interactive environments, require a prompt argument.
    if not sys.stdin.isatty():
        console.print(
            "[red]No prompt provided and stdin is not a terminal.[/red]\n"
            "[dim]Provide a prompt argument or use --preset with --no-edit, "
            "then import the result with anyzork import.[/dim]"
        )
        sys.exit(1)

    return run_wizard(console)

@cli.command("list")
def list_games() -> None:
    """List library games and summarize their active saves."""
    from rich.table import Table

    cfg = Config()
    overview = library_service.list_library_overview(cfg)

    if not overview.games and not overview.saves:
        console.print(
            "[dim]No library games found in "
            f"{cfg.games_dir} and no saves found in {cfg.saves_dir}[/dim]"
        )
        console.print("[dim]Create an authoring prompt with:[/dim]  anyzork generate")
        console.print("[dim]Then compile returned ZorkScript with:[/dim]  anyzork import -")
        return

    library_table = Table(title="Game Library", show_lines=False)
    library_table.add_column("Ref", style="cyan", no_wrap=True)
    library_table.add_column("Title", style="bold")
    library_table.add_column("Version", style="dim")
    library_table.add_column("Active Saves", justify="right", style="green")
    library_table.add_column("Latest Run", style="dim")

    for game in overview.games:
        meta = library_service.read_zork_metadata(game.path)
        save_ver = str(meta.get("version", "?")) if meta else "?"
        version_label = game.version
        if save_ver != RUNTIME_COMPAT_VERSION:
            version_str = f"[yellow]{version_label}[/yellow]"
        else:
            version_str = version_label

        library_table.add_row(
            game.ref,
            game.title,
            version_str,
            str(game.active_saves),
            game.latest_run,
        )

    console.print(library_table)


@cli.command("saves")
@click.argument("game_ref", type=str, required=False)
def list_saves(game_ref: str | None) -> None:
    """List managed save slots for all games or a single library game."""
    from rich.table import Table

    cfg = Config()
    title = "Managed Saves"
    game_filter_path: Path | None = None
    if game_ref is not None:
        try:
            game_filter_path = library_service.resolve_game_reference(game_ref, cfg)
        except ValueError as exc:
            raise click.BadParameter(str(exc), param_hint="game_ref") from exc

        if library_service.is_within(game_filter_path, cfg.saves_dir):
            raise click.BadParameter(
                "Pass a library game, not an individual save file.",
                param_hint="game_ref",
            )

        meta = library_service.read_zork_metadata(game_filter_path) or {}
        game_id = meta.get("game_id")
        title = f"Managed Saves for {meta.get('title', game_filter_path.stem)}"
        if not game_id:
            console.print(f"[red]Missing game_id metadata in {game_filter_path}[/red]")
            return
        save_files = library_service.sorted_save_files(cfg.saves_dir / str(game_id))
    else:
        save_files = sorted(
            cfg.saves_dir.glob("*/*.zork"),
            key=library_service.save_last_played_timestamp,
            reverse=True,
        ) if cfg.saves_dir.exists() else []

    if not save_files:
        if game_ref is not None and game_filter_path is not None:
            console.print(
                f"[dim]No managed saves found for[/dim] [cyan]{game_filter_path.stem}[/cyan]"
            )
        else:
            console.print(f"[dim]No managed saves found in {cfg.saves_dir}[/dim]")
        return

    title_by_source_game_id: dict[str, str] = {}
    ref_by_source_game_id: dict[str, str] = {}
    library_files = sorted(cfg.games_dir.glob("*.zork")) if cfg.games_dir.exists() else []
    for zork_file in library_files:
        meta = library_service.read_zork_metadata(zork_file) or {}
        source_game_id = meta.get("game_id")
        if source_game_id:
            title_by_source_game_id[str(source_game_id)] = str(meta.get("title") or zork_file.stem)
            ref_by_source_game_id[str(source_game_id)] = zork_file.stem

    table = Table(title=title, show_lines=False)
    table.add_column("Ref", style="cyan", no_wrap=True)
    table.add_column("Title", style="bold")
    table.add_column("Slot", style="bold")
    table.add_column("State", style="dim")
    table.add_column("Score", justify="right", style="green")
    table.add_column("Moves", justify="right", style="green")
    table.add_column("Updated", style="dim")

    for save_file in save_files:
        save_meta = library_service.read_zork_metadata(save_file) or {}
        player = library_service.read_player_state(save_file) or {}
        source_game_id = str(save_meta.get("source_game_id") or "")
        game_ref = ref_by_source_game_id.get(source_game_id, save_file.parent.name)
        game_label = title_by_source_game_id.get(source_game_id, save_file.parent.name)
        table.add_row(
            game_ref,
            game_label,
            str(save_meta.get("save_slot") or save_file.stem),
            str(player.get("game_state", "?")),
            str(player.get("score", 0)),
            str(player.get("moves", 0)),
            library_service.format_save_last_played(save_file),
        )

    console.print(table)


@cli.command("delete-save")
@click.argument("game_ref", type=str)
@click.option("--slot", required=True, help="Managed save slot to delete.")
def delete_save(game_ref: str, slot: str) -> None:
    """Delete a managed save slot for a library game."""
    cfg = Config()
    try:
        source_path = library_service.resolve_game_reference(game_ref, cfg)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="game_ref") from exc

    if library_service.is_within(source_path, cfg.saves_dir):
        raise click.BadParameter(
            "Pass a library game, not an individual save file.",
            param_hint="game_ref",
        )

    game_id = library_service.library_game_id(source_path)
    if not game_id:
        console.print(f"[red]Missing game_id metadata in {source_path}[/red]")
        return

    save_path = cfg.saves_dir / game_id / f"{library_service.sanitize_slot_name(slot)}.zork"
    if not save_path.exists():
        console.print(
            f"[dim]No save slot named[/dim] [cyan]{slot}[/cyan] "
            f"[dim]for[/dim] [cyan]{source_path.stem}[/cyan]"
        )
        return

    save_path.unlink()
    console.print(
        f"[green]Deleted save slot[/green] [cyan]{slot}[/cyan] "
        f"[dim]for[/dim] [cyan]{source_path.stem}[/cyan]"
    )

    with contextlib.suppress(OSError):
        save_path.parent.rmdir()


@cli.command("delete")
@click.argument("game_ref", type=str)
@click.option("--yes", is_flag=True, help="Delete without prompting for confirmation.")
def delete_game(game_ref: str, yes: bool) -> None:
    """Delete a library game and all of its managed save slots."""
    cfg = Config()
    try:
        source_path = library_service.resolve_game_reference(game_ref, cfg)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="game_ref") from exc

    if library_service.is_within(source_path, cfg.saves_dir):
        raise click.BadParameter(
            "Delete the library game, not an individual save file. Use delete-save for slots.",
            param_hint="game_ref",
        )

    game_id = library_service.library_game_id(source_path)
    save_dir = cfg.saves_dir / game_id if game_id else None
    save_count = len(list(save_dir.glob("*.zork"))) if save_dir and save_dir.exists() else 0

    if not yes:
        prompt = (
            f"Delete library game '{source_path.stem}' and {save_count} managed save(s)?"
        )
        if not click.confirm(prompt, default=False):
            console.print("[dim]Delete cancelled.[/dim]")
            return

    source_path.unlink()
    if save_dir and save_dir.exists():
        shutil.rmtree(save_dir)

    console.print(
        f"[green]Deleted library game[/green] [cyan]{source_path.stem}[/cyan] "
        f"[dim]and {save_count} managed save(s).[/dim]"
    )

def main() -> None:
    """Entry point wired in pyproject.toml."""
    cli()


if __name__ == "__main__":
    main()
