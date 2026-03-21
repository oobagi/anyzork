"""Reusable library/save helpers for non-Click entrypoints."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar
from uuid import uuid4

from anyzork.config import Config

if TYPE_CHECKING:
    from collections.abc import Callable

    from anyzork.db.schema import GameDB

T = TypeVar("T")


@dataclass(frozen=True)
class GameSummary:
    """A compact view of a library game."""

    ref: str
    title: str
    path: Path
    version: str
    runs: int
    active_saves: int
    latest_run: str


@dataclass(frozen=True)
class SaveSummary:
    """A compact view of a managed save."""

    game: str
    slot: str
    state: str
    score: int
    moves: int
    updated: str
    path: Path


@dataclass(frozen=True)
class LibraryOverview:
    """Combined library and managed save summaries."""

    games: list[GameSummary]
    saves: list[SaveSummary]


def slugify_name(value: str) -> str:
    """Return a filesystem-friendly slug."""
    import re

    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "game"


def sanitize_slot_name(value: str) -> str:
    """Return a safe save-slot filename stem."""
    slot = value.strip().replace("/", "_").replace("\\", "_")
    return slot or "default"


def copy_zork_file(source: Path, destination: Path) -> None:
    """Copy a .zork file to a new location, replacing sidecars first."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    Path(f"{destination}-wal").unlink(missing_ok=True)
    Path(f"{destination}-shm").unlink(missing_ok=True)
    shutil.copy2(source, destination)


def is_within(path: Path, root: Path) -> bool:
    """Return True when a path lives underneath a root."""
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def read_game_data(path: Path, reader: Callable[[GameDB], T]) -> T | None:
    """Read derived data from a .zork file while tolerating failures."""
    from anyzork.db.schema import GameDB

    try:
        with GameDB(path) as db:
            return reader(db)
    except Exception:
        return None


def read_zork_metadata(path: Path) -> dict | None:
    """Return metadata for a .zork file, or None on read errors."""
    return read_game_data(path, lambda db: db.get_all_meta())


def read_player_state(path: Path) -> dict | None:
    """Return player state for a .zork file, or None on read errors."""
    return read_game_data(path, lambda db: db.get_player())


def save_last_played_timestamp(path: Path) -> str:
    """Return the raw last-played timestamp used for sorting."""
    return str((read_zork_metadata(path) or {}).get("last_played_at") or "")


def format_save_last_played(path: Path) -> str:
    """Return a compact display string for the save timestamp."""
    timestamp = save_last_played_timestamp(path)
    return timestamp[:16].replace("T", " ") if timestamp else ""


def sorted_save_files(save_dir: Path) -> list[Path]:
    """Return save files sorted by descending last-played timestamp."""
    return sorted(save_dir.glob("*.zork"), key=save_last_played_timestamp, reverse=True)


def format_metadata_versions(meta: dict | None) -> str:
    """Format runtime and prompt-system versions for display."""
    if not meta:
        return "?"

    runtime_version = str(meta.get("version") or "?")
    prompt_version = meta.get("prompt_system_version")
    if prompt_version:
        return f"{runtime_version} / {prompt_version}"
    return runtime_version


def resolve_game_reference(game_ref: str, cfg: Config | None = None) -> Path:
    """Resolve a CLI/TUI game reference to a concrete .zork path."""
    cfg = cfg or Config()
    candidate = Path(game_ref).expanduser()
    if candidate.exists():
        return candidate.resolve()

    direct_name = candidate.name if candidate.name.endswith(".zork") else f"{candidate.name}.zork"
    direct_library_path = (cfg.games_dir / direct_name).resolve()
    if direct_library_path.exists():
        return direct_library_path

    library_matches: list[Path] = []
    target_slug = slugify_name(candidate.stem)
    for zork_path in sorted(cfg.games_dir.glob("*.zork")):
        meta = read_zork_metadata(zork_path) or {}
        if game_ref == meta.get("game_id"):
            return zork_path.resolve()
        if zork_path.stem == candidate.stem:
            library_matches.append(zork_path.resolve())
            continue
        if slugify_name(str(meta.get("title", ""))) == target_slug:
            library_matches.append(zork_path.resolve())

    if len(library_matches) == 1:
        return library_matches[0]
    if len(library_matches) > 1:
        raise ValueError(f"Multiple library games match '{game_ref}'. Use an explicit path.")

    raise ValueError(f"No game found for '{game_ref}'.")


def prepare_managed_save(
    source_path: Path,
    slot: str,
    restart: bool,
    cfg: Config | None = None,
) -> tuple[Path, str]:
    """Return the managed save path for a source game, cloning when needed."""
    from anyzork.db.schema import GameDB

    cfg = cfg or Config()
    source_meta = read_zork_metadata(source_path) or {}
    source_game_id = source_meta.get("game_id") or slugify_name(source_path.stem)
    slot_slug = sanitize_slot_name(slot)
    save_path = cfg.saves_dir / source_game_id / f"{slot_slug}.zork"

    if restart or not save_path.exists():
        copy_zork_file(source_path, save_path)
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


def library_game_id(path: Path) -> str | None:
    """Return the stable library game id for a .zork file."""
    meta = read_zork_metadata(path) or {}
    game_id = meta.get("game_id")
    return str(game_id) if game_id else None


def list_library_overview(cfg: Config | None = None) -> LibraryOverview:
    """Return combined summaries for library games and managed saves."""
    cfg = cfg or Config()
    library_files = sorted(cfg.games_dir.glob("*.zork")) if cfg.games_dir.exists() else []
    save_files = sorted(cfg.saves_dir.glob("*/*.zork")) if cfg.saves_dir.exists() else []

    games: list[GameSummary] = []
    saves: list[SaveSummary] = []
    title_by_source_game_id: dict[str, str] = {}

    for zork_file in library_files:
        meta = read_zork_metadata(zork_file) or {}
        game_id = meta.get("game_id")
        if game_id:
            title_by_source_game_id[str(game_id)] = zork_file.stem

        slot_files = []
        if game_id:
            slot_files = sorted((cfg.saves_dir / str(game_id)).glob("*.zork"))
        latest_desc = "new"
        active_saves = 0
        if slot_files:
            latest_save = max(slot_files, key=lambda path: path.stat().st_mtime)
            player = read_player_state(latest_save)
            state = player["game_state"] if player else "?"
            latest_desc = f"{latest_save.stem} ({state})"
            active_saves = sum(
                1
                for save_file in slot_files
                if str((read_player_state(save_file) or {}).get("game_state", "")) == "playing"
            )

        games.append(
            GameSummary(
                ref=zork_file.stem,
                title=str(meta.get("title", "Untitled")),
                path=zork_file.resolve(),
                version=format_metadata_versions(meta),
                runs=len(slot_files),
                active_saves=active_saves,
                latest_run=latest_desc,
            )
        )

    for save_file in sorted(save_files, key=save_last_played_timestamp, reverse=True):
        meta = read_zork_metadata(save_file) or {}
        player = read_player_state(save_file) or {}
        source_game_id = str(meta.get("source_game_id") or "")
        game_label = title_by_source_game_id.get(source_game_id, save_file.parent.name)
        saves.append(
            SaveSummary(
                game=game_label,
                slot=str(meta.get("save_slot") or save_file.stem),
                state=str(player.get("game_state", "?")),
                score=int(player.get("score", 0)),
                moves=int(player.get("moves", 0)),
                updated=format_save_last_played(save_file),
                path=save_file.resolve(),
            )
        )

    return LibraryOverview(games=games, saves=saves)
