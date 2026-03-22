"""AnyZork CLI — click entry point."""

from __future__ import annotations

import contextlib
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

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
    SHARE_PACKAGE_SUFFIX,
    SharePackageError,
)
from anyzork.versioning import RUNTIME_COMPAT_VERSION

console = Console()
CLI_VERSION = (
    f"{__version__} "
    f"(runtime {RUNTIME_COMPAT_VERSION}, prompt {current_prompt_system_version()})"
)
@click.group()
@click.version_option(version=CLI_VERSION, prog_name="anyzork")
def cli() -> None:
    """AnyZork -- deterministic Zork-style adventure authoring and play."""


@cli.command()
@click.argument("game_ref", type=str, required=False)
@click.option(
    "--save",
    "slot",
    type=str,
    default="default",
    show_default=True,
    help="Save name. Progress is written to ~/.anyzork/saves/<game>/<save>.zork.",
)
@click.option(
    "--new",
    "restart",
    is_flag=True,
    help="Start a fresh save from the library copy.",
)
@click.option(
    "--restart",
    "restart",
    is_flag=True,
    hidden=True,
)
@click.option("--narrator", is_flag=True, help="Enable narrator mode (requires API key).")
@click.option(
    "--provider",
    type=click.Choice(["claude", "openai", "gemini"], case_sensitive=False),
    default=None,
    help="LLM provider for narrator mode (overrides ANYZORK_PROVIDER).",
)
@click.option("--model", type=str, default=None, help="Model for narrator mode.")
@click.pass_context
def play(
    ctx: click.Context,
    game_ref: str | None,
    slot: str,
    restart: bool,
    narrator: bool,
    provider: str | None,
    model: str | None,
) -> None:
    """Play a library game or existing .zork file."""
    from anyzork.db.schema import GameDB
    from anyzork.engine.game import GameEngine

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

    # Detect whether --save was explicitly provided by the user.
    slot_explicitly_set = ctx.get_parameter_source("slot") not in (
        None,
        click.core.ParameterSource.DEFAULT,
    )

    if library_service.is_within(source_path, cfg.saves_dir):
        if restart:
            raise click.UsageError(
                "--new only works for library games or original .zork files, not an existing save."
            )
        play_path = source_path
        console.print(f"[dim]Resuming save:[/dim] [cyan]{play_path}[/cyan]")
    else:
        # When --save was not explicitly provided, check for multiple saves
        # and prompt the user to choose (interactive TTY only).
        if not slot_explicitly_set and not restart and sys.stdin.isatty():
            picked = _pick_save_slot(source_path, cfg)
            if picked is not None:
                slot, restart = picked

        play_path, action = library_service.prepare_managed_save(source_path, slot, restart, cfg)
        action_label = {
            "created": "Started save",
            "reset": "Restarted save",
            "resume": "Resuming save",
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
            console.print("[dim]Use anyzork list --saves to inspect existing save files.[/dim]")
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


def _read_paste(console: Console) -> str:
    """Read pasted input using bracket paste mode to detect and summarize pastes."""
    import termios
    import tty

    console.print("[dim]Paste the LLM's response, then press Enter:[/dim]")

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    # Enable bracket paste mode: terminal wraps pastes in \e[200~ ... \e[201~
    sys.stdout.write("\033[?2004h")
    sys.stdout.flush()

    collected: list[str] = []

    # Simple approach: read everything in raw mode, then strip escape sequences after
    try:
        tty.setraw(fd)

        raw_chars: list[str] = []
        while True:
            ch = sys.stdin.read(1)
            if not ch or ch == "\x03" or ch == "\x04":
                break
            raw_chars.append(ch)
            # Check for Enter after paste end sequence (submit)
            raw = "".join(raw_chars)
            if "\x1b[201~" in raw and ch in ("\r", "\n"):
                break

    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sys.stdout.write("\033[?2004l")
        sys.stdout.flush()

    # Extract paste content: everything between \x1b[200~ and \x1b[201~
    raw = "".join(raw_chars)
    import re as _paste_re
    pastes = _paste_re.findall(r"\x1b\[200~(.*?)\x1b\[201~", raw, _paste_re.DOTALL)
    if pastes:
        text = "\n".join(pastes)
    else:
        # No bracket paste sequences — use raw input minus control chars
        text = raw

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    char_count = len(text.strip())
    line_count = text.strip().count("\n") + 1 if text.strip() else 0
    if char_count:
        console.print(f"  [dim]\\[pasted {char_count} chars, {line_count} lines][/dim]")

    return text


def _show_error_context(source_text: str, exc: Exception) -> None:
    """Print the lines around a parse error for debugging."""
    import re as _re

    match = _re.search(r"line (\d+)", str(exc))
    if not match:
        return
    error_line = int(match.group(1))
    lines = source_text.split("\n")
    start = max(0, error_line - 3)
    end = min(len(lines), error_line + 2)
    console.print()
    for i in range(start, end):
        marker = "[red]>>>[/red] " if i + 1 == error_line else "    "
        safe = lines[i].replace("[", "\\[")
        console.print(f"  {marker}[dim]{i + 1:4d}[/dim] {safe}")
    console.print()


def _pick_save_slot(source_path: Path, cfg: Config) -> tuple[str, bool] | None:
    """Prompt the user to choose a save slot or start a new game.

    Returns ``(slot_name, restart)`` or ``None`` to cancel.
    """
    save_dir = cfg.saves_dir / source_path.stem
    save_files = library_service.sorted_save_files(save_dir) if save_dir.exists() else []

    console.print()
    console.print("[bold]Saves:[/bold]" if save_files else "[bold]No saves yet.[/bold]")
    entries: list[tuple[str, str]] = []
    for save_file in save_files:
        save_meta = library_service.read_zork_metadata(save_file) or {}
        player = library_service.read_player_state(save_file) or {}
        slot_name = str(save_meta.get("save_slot") or save_file.stem)
        state = str(player.get("game_state", "?"))
        score = int(player.get("score", 0))
        moves = int(player.get("moves", 0))
        updated = library_service.format_save_last_played(save_file)
        label = f"{slot_name} ({state}, score {score}, moves {moves})"
        if updated:
            label += f" [{updated}]"
        entries.append((slot_name, label))
        console.print(f"  [cyan]{len(entries)}[/cyan]. {label}")

    new_index = len(entries) + 1
    console.print(f"  [cyan]{new_index}[/cyan]. [dim]New game[/dim]")

    while True:
        choice = click.prompt("Choose a save", type=str).strip().lower()
        if choice in {"q", "quit", "exit"}:
            return None

        try:
            index = int(choice)
        except ValueError:
            console.print("[dim]Enter one of the numbers above, or q to cancel.[/dim]")
            continue

        if index == new_index:
            new_slot = click.prompt("Name for new save", default="default", type=str)
            return (new_slot.strip() or "default", True)

        if 1 <= index <= len(entries):
            return (entries[index - 1][0], False)

        console.print("[dim]Enter one of the numbers above, or q to cancel.[/dim]")


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
    """Walk the user through the publish listing wizard."""
    from anyzork.sharing import build_share_manifest

    manifest = build_share_manifest(source_path)
    listing = dict(manifest.get("listing", {}))
    title_default = str(listing.get("title") or source_path.stem)
    author_default = str(listing.get("author") or "")
    description_default = str(listing.get("description") or "")
    tagline_default = str(listing.get("tagline") or "")
    genres_default = [
        str(genre).strip() for genre in listing.get("genres", []) if str(genre).strip()
    ]

    console.print("[bold]Publish Listing[/bold]")
    console.print("[dim]Press enter to keep a suggested value, or type your own.[/dim]")
    console.print()

    resolved_title = _prompt_optional_text("Public title", title_default) or title_default
    resolved_author = _prompt_optional_text("Author", author_default)
    resolved_description = _prompt_optional_text("Description", description_default)
    resolved_tagline = _prompt_optional_text("Tagline", tagline_default)
    resolved_genres = _prompt_optional_genres(genres_default)
    resolved_slug = _prompt_optional_text(
        "Slug",
        library_service.slugify_name(resolved_title or source_path.stem),
    )

    return (
        resolved_title,
        resolved_author,
        resolved_description,
        resolved_tagline,
        resolved_genres,
        resolved_slug,
        None,
        None,
    )


@cli.command("publish")
@click.argument("game_ref", type=str, required=False)
@click.option("--status", "status_slug", type=str, default=None, help="Check publish status for a catalog slug.")
def publish_game(game_ref: str | None, status_slug: str | None) -> None:
    """Package and upload a .zork archive or project directory to the catalog."""
    if status_slug is not None:
        _check_publish_status(status_slug)
        return

    if game_ref is None:
        raise click.UsageError("Missing argument 'GAME_REF'.")

    import tempfile

    from anyzork.archive import is_zork_archive, pack_project
    from anyzork.sharing import create_share_package, upload_share_package

    cfg = Config()

    # Accept project directories, .zork archive paths, or library refs.
    candidate = Path(game_ref).expanduser()
    if candidate.is_dir() and (candidate / "manifest.toml").exists():
        # Project directory — pack it into a .zork archive first.
        with tempfile.TemporaryDirectory(prefix="anyzork-pack-") as tmp:
            source_path = pack_project(candidate, Path(tmp) / f"{candidate.name}.zork")
            return _do_publish(source_path, cfg)
    elif candidate.is_file() and is_zork_archive(candidate):
        source_path = candidate.resolve()
    else:
        try:
            source_path = library_service.resolve_game_reference(game_ref, cfg)
        except ValueError as exc:
            raise click.BadParameter(str(exc), param_hint="game_ref") from exc

    if library_service.is_within(source_path, cfg.saves_dir):
        raise click.BadParameter(
            "Publish a library game or .zork archive, not a managed save.",
            param_hint="game_ref",
        )

    # Verify the source is a valid .zork archive.
    if not is_zork_archive(source_path):
        raise click.BadParameter(
            "Publish expects a .zork archive or project directory.",
            param_hint="game_ref",
        )

    _do_publish(source_path, cfg)


def _do_publish(source_path: Path, cfg: Config) -> None:
    """Run the publish wizard and upload for a .zork archive."""
    import tempfile

    from anyzork.sharing import create_share_package, upload_share_package

    (
        title,
        author,
        description,
        tagline,
        genre_values,
        slug,
        homepage_url,
        cover_image_url,
    ) = _resolve_publish_listing_metadata(source_path)

    console.print()
    if not click.confirm("Ready to publish?", default=True):
        console.print("[dim]Canceled.[/dim]")
        return

    with tempfile.TemporaryDirectory(prefix="anyzork-publish-") as tmp:
        output = Path(tmp) / f"{source_path.stem}{SHARE_PACKAGE_SUFFIX}"

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
        console.print(f"[dim]Uploading[/dim] [cyan]{listing_title}[/cyan][dim]...[/dim]")

        try:
            payload = upload_share_package(
                package_path,
                cfg.upload_url,
            )
        except SharePackageError as exc:
            console.print(f"[red]Upload failed:[/red] {exc}")
            sys.exit(1)

    game = dict(payload.get("game") or {})
    uploaded_slug = str(game.get("slug") or slug or "")
    console.print(
        f"[bold green]Published![/bold green] [cyan]{listing_title}[/cyan]"
        + (f" [dim]as[/dim] [cyan]{uploaded_slug}[/cyan]" if uploaded_slug else "")
    )
    console.print(
        f"[dim]Submitted for review. Check status with:[/dim]"
        f"  anyzork publish --status {uploaded_slug}"
    )


def _check_publish_status(slug: str) -> None:
    """Check the publish status of a submitted game."""
    import json as _json
    from urllib.error import HTTPError
    from urllib.request import urlopen

    cfg = Config()
    url = cfg.catalog_url.replace("/catalog.json", f"/api/games/{slug}/status")
    try:
        with urlopen(url, timeout=10) as resp:
            data = _json.loads(resp.read().decode())
    except HTTPError as exc:
        if exc.code == 404:
            console.print(f"[red]No game found for slug[/red] [cyan]{slug}[/cyan]")
            sys.exit(1)
        raise
    except OSError as exc:
        console.print(f"[red]Could not reach catalog:[/red] {exc}")
        sys.exit(1)

    title = data.get("title", slug)
    if data.get("published"):
        console.print(
            f"[bold green]Live[/bold green] — [cyan]{title}[/cyan]"
            " is published and visible in browse."
        )
    else:
        console.print(
            f"[yellow]Pending[/yellow] — [cyan]{title}[/cyan]"
            " is submitted but not yet approved."
        )


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
def import_game(
    spec_source: str, output: Path | None, print_template: bool
) -> None:
    """Compile ZorkScript into a .zork game."""
    from anyzork.importer import ZORKSCRIPT_AUTHORING_TEMPLATE, ImportSpecError, load_import_source
    from anyzork.zorkscript import ZorkScriptError

    if print_template:
        console.print(ZORKSCRIPT_AUTHORING_TEMPLATE)
        return

    cfg = Config()
    resolved_source = _resolve_import_source(spec_source)

    # -- Parse spec ----------------------------------------------------------
    # Check for project directory or archive
    source_path = Path(resolved_source).expanduser()
    spec = None

    from anyzork.project import is_project_dir

    if is_project_dir(source_path):
        from anyzork.manifest import ManifestError
        from anyzork.project import load_project
        from anyzork.zorkscript import parse_zorkscript

        try:
            project = load_project(source_path)
            spec = parse_zorkscript(project.text)
        except ManifestError as exc:
            console.print(f"[red]Project error:[/red] {exc}")
            sys.exit(1)
        except ZorkScriptError as exc:
            from anyzork.diagnostics import from_zorkscript_error, render_diagnostic

            diag = from_zorkscript_error(exc)
            render_diagnostic(diag, console)
            _print_doctor_hint(spec_source)
            sys.exit(1)
    elif source_path.is_file():
        from anyzork.archive import is_zork_archive, load_project_from_archive

        if is_zork_archive(source_path):
            from anyzork.zorkscript import parse_zorkscript

            try:
                project = load_project_from_archive(source_path)
                spec = parse_zorkscript(project.text)
            except ZorkScriptError as exc:
                from anyzork.diagnostics import from_zorkscript_error, render_diagnostic

                diag = from_zorkscript_error(exc)
                render_diagnostic(diag, console)
                _print_doctor_hint(spec_source)
                sys.exit(1)
        else:
            try:
                spec = load_import_source(resolved_source)
            except ZorkScriptError as exc:
                from anyzork.diagnostics import from_zorkscript_error, render_diagnostic

                diag = from_zorkscript_error(exc)
                render_diagnostic(diag, console)
                _print_doctor_hint(spec_source)
                sys.exit(1)
            except ImportSpecError as exc:
                console.print(f"[red]Import failed:[/red] {exc}")
                _print_doctor_hint(spec_source)
                sys.exit(1)
    else:
        try:
            spec = load_import_source(resolved_source)
        except ZorkScriptError as exc:
            from anyzork.diagnostics import from_zorkscript_error, render_diagnostic

            diag = from_zorkscript_error(exc)
            render_diagnostic(diag, console)
            _print_doctor_hint(spec_source)
            sys.exit(1)
        except ImportSpecError as exc:
            console.print(f"[red]Import failed:[/red] {exc}")
            _print_doctor_hint(spec_source)
            sys.exit(1)

    # -- Compile -------------------------------------------------------------
    try:
        result = importing_service.import_zorkscript_spec(
            spec=spec,
            output_path=output,
            cfg=cfg,
        )
    except ImportSpecError as exc:
        console.print(f"[red]Import failed:[/red] {exc}")
        _print_doctor_hint(spec_source)
        sys.exit(1)
    except Exception as exc:
        console.print(f"[red]Import failed:[/red] {exc}")
        _print_doctor_hint(spec_source)
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



@cli.command("doctor")
@click.argument("source", required=False, default="-")
def doctor(source: str) -> None:
    """Diagnose ZorkScript errors, get an LLM fix, and re-import."""
    from anyzork.services.doctor import build_fix_prompt, collect_diagnostics, copy_to_clipboard

    resolved_source = _resolve_import_source(source)

    # Read raw text (handle project directory and archive)
    source_path = Path(resolved_source).expanduser()
    is_project = False
    if source_path.is_dir():
        from anyzork.manifest import ManifestError
        from anyzork.project import load_project

        try:
            project_src = load_project(source_path)
        except ManifestError as exc:
            console.print(f"[red]Project error:[/red] {exc}")
            sys.exit(1)
        raw_text = project_src.text
        is_project = True
    elif source_path.is_file():
        from anyzork.archive import is_zork_archive, load_project_from_archive

        if is_zork_archive(source_path):
            project_src = load_project_from_archive(source_path)
            raw_text = project_src.text
        else:
            raw_text = source_path.read_text(encoding="utf-8")
    elif resolved_source == "-":
        raw_text = sys.stdin.read()
    else:
        raw_text = Path(resolved_source).read_text(encoding="utf-8")

    result = collect_diagnostics(raw_text)

    if not result.diagnostics:
        console.print("No errors found — this script should import cleanly.")
        return

    n_errors = sum(1 for d in result.diagnostics if d.severity == "error")
    n_warnings = sum(1 for d in result.diagnostics if d.severity == "warning")
    console.print(f"Found {n_errors} error(s) and {n_warnings} warning(s).", highlight=False)

    file_list = project_src.manifest.source_files if is_project else None
    prompt = build_fix_prompt(raw_text, result.diagnostics, source_files=file_list)

    if copy_to_clipboard(prompt):
        console.print("Fix prompt copied to clipboard.")
    else:
        console.print()
        console.print(prompt, highlight=False)
        console.print()

    if not sys.stdin.isatty():
        return

    # Paste-back flow: user pastes corrected output, we save and re-import
    console.print("[dim]Paste into your LLM, then paste the corrected output back here.[/dim]")
    pasted = _read_paste(console)

    if not pasted.strip():
        return

    # Save the corrected output
    corrected = pasted.strip()
    if is_project:
        from anyzork.services.paste_splitter import split_pasted_output

        manifest = project_src.manifest
        files = split_pasted_output(corrected, manifest.source_files)
        saved_files: list[str] = []
        for filename, content in files.items():
            (source_path / filename).write_text(content + "\n", encoding="utf-8")
            saved_files.append(filename)
            console.print(f"  [green]✓[/green] Updated {filename}")
        # Update manifest if file list changed
        if saved_files and set(saved_files) != set(manifest.source_files):
            files_toml = ", ".join(f'"{f}"' for f in saved_files)
            project = manifest
            manifest_content = (
                "[project]\n"
                f'title = "{project.title}"\n'
                f'slug = "{project.slug}"\n'
                f'author = "{project.author}"\n'
                f'description = "{project.description}"\n'
                "tags = []\n\n"
                "[source]\n"
                f"files = [{files_toml}]\n"
            )
            (source_path / "manifest.toml").write_text(manifest_content, encoding="utf-8")
    elif source_path.is_file():
        source_path.write_text(corrected + "\n", encoding="utf-8")
        console.print(f"  [green]✓[/green] Updated {source_path.name}")

    # Re-import
    console.print()
    console.print("[dim]Compiling...[/dim]")
    try:
        from anyzork.zorkscript import parse_zorkscript

        if is_project:
            from anyzork.project import load_project as _lp
            project_reloaded = _lp(source_path)
            spec = parse_zorkscript(project_reloaded.text)
        else:
            spec = parse_zorkscript(corrected)

        importing_service.import_zorkscript_spec(spec=spec, cfg=Config())
        console.print(f"  [green]✓[/green] Imported: {source_path.stem}")
        console.print()
        console.print(f"[bold green]Fixed![/bold green] Play it with:  anyzork play {source_path.stem}")
    except Exception as exc:
        console.print(f"  [yellow]⚠[/yellow] Still has errors: {exc}")
        _show_error_context(corrected, exc)
        console.print(f"[dim]Run doctor again:[/dim]  anyzork doctor {source}")


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
                cfg.catalog_url,
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
                "Install expects an official catalog ref or a local .zork package.",
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

    cfg = Config()
    try:
        catalog = load_public_catalog(cfg.catalog_url)
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

    suffixes = {".zork", ".json"}
    if Path(value).suffix.lower() in suffixes:
        return False

    return not ("/" in value or "\\" in value)


def _print_doctor_hint(source_ref: str) -> None:
    """Suggest running 'anyzork doctor' after an import failure."""
    console.print(
        f"[dim]Run 'anyzork doctor {source_ref}' to generate a fix prompt "
        f"for your LLM.[/dim]"
    )



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
    help="Write the generation prompt to a file (non-interactive).",
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
    """Build a ZorkScript authoring prompt and paste back the LLM response.

    \b
    Usage modes:
      anyzork generate "prompt"          Generate from a freeform concept
      anyzork generate                   Launch the interactive wizard
      anyzork generate --guided          Launch the wizard explicitly
      anyzork generate --preset zombie-survival   Load a preset, preview, confirm
      anyzork generate --list-presets    List available presets
      anyzork generate "prompt" -o out   Write the prompt to a file (scripting)
    """
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

    # ── Create project directory ──────────────────────────────────────
    from anyzork.manifest import _slugify
    from anyzork.services.stepgen import build_generation_prompt, OUTPUT_FILES
    from anyzork.services.doctor import copy_to_clipboard

    concept_slug = _slugify(
        str(authoring_fields.get("world_description", resolved_prompt))[:30]
    )
    project_dir = Path(concept_slug)

    # Handle existing directory
    if project_dir.exists():
        i = 2
        while Path(f"{concept_slug}-{i}").exists():
            i += 1
        project_dir = Path(f"{concept_slug}-{i}")

    project_dir.mkdir()
    console.print(f"[bold green]Created project:[/bold green] {project_dir}/")
    console.print()

    # ── Build prompt ─────────────────────────────────────────────────
    generation_prompt = build_generation_prompt(
        resolved_prompt,
        realism=realism,
        authoring_fields=authoring_fields,
    )

    # ── Non-interactive: write prompt to file ────────────────────────
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(generation_prompt, encoding="utf-8")
        # Write manifest with all expected files
        all_files = OUTPUT_FILES
        files_toml = ", ".join(f'"{f}"' for f in all_files)
        title_escaped = resolved_prompt[:80].replace(chr(34), chr(39))
        manifest_content = (
            "[project]\n"
            f'title = "{title_escaped}"\n'
            f'slug = "{project_dir.name}"\n'
            'author = ""\n'
            'description = ""\n'
            "tags = []\n"
            "\n"
            "[source]\n"
            f"files = [{files_toml}]\n"
        )
        (project_dir / "manifest.toml").write_text(manifest_content, encoding="utf-8")
        console.print(
            f"[bold green]Done![/bold green] Prompt written to [cyan]{output}[/cyan]"
        )
        console.print(f"[dim]Import with:[/dim]  anyzork import {project_dir}")
        return

    # ── Interactive: copy prompt, paste back, auto-import ────────────
    if copy_to_clipboard(generation_prompt):
        console.print("Prompt copied to clipboard.")
    else:
        console.print(generation_prompt, highlight=False)

    console.print("[dim]Paste into your LLM. Copy the entire response back (including file headers).[/dim]")

    if sys.stdin.isatty():
        pasted_text = _read_paste(console)

        while not pasted_text.strip():
            console.print("[yellow]No input received. Try pasting again.[/yellow]")
            pasted_text = _read_paste(console)

        from anyzork.services.paste_splitter import split_pasted_output

        files = split_pasted_output(pasted_text, OUTPUT_FILES)
        saved_files: list[str] = []

        for filename, content in files.items():
            file_path = project_dir / filename
            file_path.write_text(content + "\n", encoding="utf-8")
            saved_files.append(filename)
            line_count = content.count("\n") + 1
            console.print(f"  [green]✓[/green] Saved {filename} ({line_count} lines)")

        # Write manifest with actual saved files
        if saved_files:
            files_toml = ", ".join(f'"{f}"' for f in saved_files)
            title_escaped = resolved_prompt[:80].replace(chr(34), chr(39))
            manifest_content = (
                "[project]\n"
                f'title = "{title_escaped}"\n'
                f'slug = "{project_dir.name}"\n'
                'author = ""\n'
                'description = ""\n'
                "tags = []\n"
                "\n"
                "[source]\n"
                f"files = [{files_toml}]\n"
            )
            (project_dir / "manifest.toml").write_text(manifest_content, encoding="utf-8")

        # Auto-import
        console.print()
        console.print("[dim]Compiling...[/dim]")
        try:
            from anyzork.project import load_project
            from anyzork.zorkscript import parse_zorkscript

            from anyzork.archive import pack_project

            project = load_project(project_dir)
            spec = parse_zorkscript(project.text)
            cfg = Config()

            # Compile
            importing_service.import_zorkscript_spec(spec=spec, cfg=cfg)

            # Pack archive into games_dir so `play` can find it
            cfg.games_dir.mkdir(parents=True, exist_ok=True)
            archive_path = pack_project(project_dir, cfg.games_dir / f"{project_dir.name}.zork")

            console.print(f"  [green]✓[/green] Imported: {project_dir.name}")
            console.print()
            console.print(f"[bold green]Done![/bold green] Play it with:  anyzork play {project_dir.name}")
        except Exception as exc:
            console.print(f"  [yellow]⚠[/yellow] Import failed: {exc}")
            _show_error_context(project.text, exc)
            console.print(
                f"[dim]Fix with:[/dim]  anyzork doctor {project_dir}"
            )


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
@click.option("--saves", is_flag=True, help="Show managed saves instead of games.")
def list_games(saves: bool) -> None:
    """List library games, or managed saves with --saves."""
    from rich.table import Table

    from anyzork.archive import is_zork_archive

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

    if not saves:
        library_table = Table(title="Game Library", show_lines=False)
        library_table.add_column("Ref", style="cyan", no_wrap=True)
        library_table.add_column("Title", style="bold")
        library_table.add_column("Version", style="dim")
        library_table.add_column("Active Saves", justify="right", style="green")
        library_table.add_column("Latest Run", style="dim")

        for game in overview.games:
            version_label = game.version or ""
            version_str = version_label

            library_table.add_row(
                game.ref,
                game.title,
                version_str,
                str(game.active_saves),
                game.latest_run,
            )

        console.print(library_table)
        return

    if saves:
        save_files = sorted(
            cfg.saves_dir.glob("*/*.zork"),
            key=library_service.save_last_played_timestamp,
            reverse=True,
        ) if cfg.saves_dir.exists() else []

        if not save_files:
            console.print()
            console.print(f"[dim]No managed saves found in {cfg.saves_dir}[/dim]")
            return

        # Build slug-to-title mapping from library games
        title_by_slug: dict[str, str] = {}
        library_files = sorted(cfg.games_dir.glob("*.zork")) if cfg.games_dir.exists() else []
        for zork_file in library_files:
            slug = zork_file.stem
            if is_zork_archive(zork_file):
                ameta = library_service.read_archive_metadata(zork_file) or {}
                title_by_slug[slug] = str(ameta.get("title") or slug)
            else:
                lmeta = library_service.read_zork_metadata(zork_file) or {}
                title_by_slug[slug] = str(lmeta.get("title") or slug)

        saves_table = Table(title="Managed Saves", show_lines=False)
        saves_table.add_column("Ref", style="cyan", no_wrap=True)
        saves_table.add_column("Title", style="bold")
        saves_table.add_column("Save", style="bold")
        saves_table.add_column("State", style="dim")
        saves_table.add_column("Score", justify="right", style="green")
        saves_table.add_column("Moves", justify="right", style="green")
        saves_table.add_column("Updated", style="dim")

        for save_file in save_files:
            save_meta = library_service.read_zork_metadata(save_file) or {}
            player = library_service.read_player_state(save_file) or {}
            save_slug = save_file.parent.name
            game_label = title_by_slug.get(save_slug, save_slug)
            saves_table.add_row(
                save_slug,
                game_label,
                str(save_meta.get("save_slot") or save_file.stem),
                str(player.get("game_state", "?")),
                str(player.get("score", 0)),
                str(player.get("moves", 0)),
                library_service.format_save_last_played(save_file),
            )

        console.print()
        console.print(saves_table)



@cli.command("delete")
@click.argument("game_ref", type=str)
@click.option("--save", "slot", default=None, help="Delete only this save instead of the whole game.")
@click.option("--yes", is_flag=True, help="Delete without prompting for confirmation.")
def delete_game(game_ref: str, slot: str | None, yes: bool) -> None:
    """Delete a library game (and saves), or a single save with --save."""
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

    game_slug = source_path.stem

    # Delete a single save
    if slot is not None:
        save_path = cfg.saves_dir / game_slug / f"{library_service.sanitize_slot_name(slot)}.zork"
        if not save_path.exists():
            console.print(
                f"[dim]No save named[/dim] [cyan]{slot}[/cyan] "
                f"[dim]for[/dim] [cyan]{source_path.stem}[/cyan]"
            )
            return
        save_path.unlink()
        console.print(
            f"[green]Deleted save[/green] [cyan]{slot}[/cyan] "
            f"[dim]for[/dim] [cyan]{source_path.stem}[/cyan]"
        )
        with contextlib.suppress(OSError):
            save_path.parent.rmdir()
        return

    # Delete the whole game + all saves
    save_dir = cfg.saves_dir / game_slug
    save_count = len(list(save_dir.glob("*.zork"))) if save_dir.exists() else 0

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
