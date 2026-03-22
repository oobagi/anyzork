"""Compilation cache -- compiles .zork archives to .db SQLite files on demand."""

from __future__ import annotations

import hashlib
from pathlib import Path

from anyzork.config import Config


def _archive_hash(archive_path: Path) -> str:
    """SHA-256 hash of a .zork archive file."""
    h = hashlib.sha256()
    with open(archive_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _hash_path(db_path: Path) -> Path:
    """Return the sidecar path that stores the source archive hash."""
    return db_path.with_suffix(".hash")


def _read_cached_hash(db_path: Path) -> str | None:
    """Read the source hash stored alongside a cached .db file."""
    hp = _hash_path(db_path)
    try:
        return hp.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def _write_cached_hash(db_path: Path, source_hash: str) -> None:
    """Write the source hash alongside a cached .db file."""
    _hash_path(db_path).write_text(source_hash, encoding="utf-8")


def ensure_compiled(archive_path: Path, cfg: Config | None = None) -> Path:
    """Ensure a .zork archive has a current compiled .db in the cache.

    Returns the path to the compiled .db file.
    Recompiles if the cache is stale or missing.
    """
    from anyzork.archive import load_project_from_archive
    from anyzork.importer import compile_import_spec
    from anyzork.zorkscript import parse_zorkscript

    config = cfg or Config()
    config.cache_dir.mkdir(parents=True, exist_ok=True)

    db_path = config.cache_dir / f"{archive_path.stem}.db"
    current_hash = _archive_hash(archive_path)

    # Check if cache is current
    if db_path.exists():
        cached_hash = _read_cached_hash(db_path)
        if cached_hash == current_hash:
            return db_path

    # Recompile
    project = load_project_from_archive(archive_path)
    spec = parse_zorkscript(project.text)

    compiled_path, _warnings = compile_import_spec(spec, db_path)

    # Store the source hash in sidecar file
    _write_cached_hash(compiled_path, current_hash)

    return compiled_path


def clear_cache(game_slug: str | None = None, cfg: Config | None = None) -> int:
    """Clear compiled cache files. Returns number of files removed."""
    config = cfg or Config()
    if not config.cache_dir.exists():
        return 0

    count = 0
    if game_slug:
        target = config.cache_dir / f"{game_slug}.db"
        if target.exists():
            target.unlink()
            _hash_path(target).unlink(missing_ok=True)
            count = 1
    else:
        for db_file in config.cache_dir.glob("*.db"):
            db_file.unlink()
            _hash_path(db_file).unlink(missing_ok=True)
            count += 1
    return count
