"""Tests for the compilation cache and archive-based play flow."""

from __future__ import annotations

import zipfile
from pathlib import Path

from click.testing import CliRunner

from anyzork import cli as cli_module
from anyzork.cli import cli
from anyzork.config import DEFAULT_CATALOG_URL, DEFAULT_UPLOAD_URL
from anyzork.importer import compile_import_spec
from anyzork.services import library as library_service
from anyzork.services.cache import clear_cache, ensure_compiled


def _make_project_dir(tmp_path: Path, minimal_zorkscript: str) -> Path:
    """Create a minimal project directory with manifest.toml + .zorkscript."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "manifest.toml").write_text(
        '[project]\n'
        'title = "Fixture Game"\n'
        'slug = "fixture-game"\n'
        'author = "Test Author"\n'
        'description = "A test game."\n'
        'tags = ["test"]\n'
        '\n'
        '[source]\n'
        'files = ["game.zorkscript"]\n',
        encoding="utf-8",
    )
    (project_dir / "game.zorkscript").write_text(minimal_zorkscript, encoding="utf-8")
    return project_dir


def _pack_archive(project_dir: Path, output_path: Path) -> Path:
    """Pack a project directory into a .zork zip archive."""
    from anyzork.archive import pack_project

    return pack_project(project_dir, output_path)


def test_ensure_compiled_creates_db(
    tmp_path: Path, minimal_zorkscript: str
) -> None:
    """First compilation creates .db in cache_dir."""
    from anyzork.config import Config

    project_dir = _make_project_dir(tmp_path, minimal_zorkscript)
    archive_path = _pack_archive(project_dir, tmp_path / "fixture-game.zork")
    cache_dir = tmp_path / "cache"

    cfg = Config(cache_dir=cache_dir, games_dir=tmp_path, saves_dir=tmp_path / "saves")

    db_path = ensure_compiled(archive_path, cfg)

    assert db_path.exists()
    assert db_path.parent == cache_dir
    assert db_path.suffix == ".db"

    # The hash sidecar should also exist
    hash_path = db_path.with_suffix(".hash")
    assert hash_path.exists()
    assert len(hash_path.read_text().strip()) == 16


def test_ensure_compiled_uses_cache(
    tmp_path: Path, minimal_zorkscript: str
) -> None:
    """Second call returns same .db without recompiling."""
    from anyzork.config import Config

    project_dir = _make_project_dir(tmp_path, minimal_zorkscript)
    archive_path = _pack_archive(project_dir, tmp_path / "fixture-game.zork")
    cache_dir = tmp_path / "cache"

    cfg = Config(cache_dir=cache_dir, games_dir=tmp_path, saves_dir=tmp_path / "saves")

    db_path_1 = ensure_compiled(archive_path, cfg)
    mtime_1 = db_path_1.stat().st_mtime

    db_path_2 = ensure_compiled(archive_path, cfg)
    mtime_2 = db_path_2.stat().st_mtime

    assert db_path_1 == db_path_2
    assert mtime_1 == mtime_2  # file was not rewritten


def test_ensure_compiled_recompiles_on_change(
    tmp_path: Path, minimal_zorkscript: str
) -> None:
    """Changing archive content invalidates cache."""
    from anyzork.config import Config

    project_dir = _make_project_dir(tmp_path, minimal_zorkscript)
    archive_path = _pack_archive(project_dir, tmp_path / "fixture-game.zork")
    cache_dir = tmp_path / "cache"

    cfg = Config(cache_dir=cache_dir, games_dir=tmp_path, saves_dir=tmp_path / "saves")

    db_path_1 = ensure_compiled(archive_path, cfg)
    hash_1 = db_path_1.with_suffix(".hash").read_text().strip()

    # Modify the archive by changing the zorkscript content
    modified_zorkscript = minimal_zorkscript.replace(
        '"A quiet foyer."', '"A noisy foyer."'
    )
    (project_dir / "game.zorkscript").write_text(modified_zorkscript, encoding="utf-8")
    _pack_archive(project_dir, archive_path)

    db_path_2 = ensure_compiled(archive_path, cfg)
    hash_2 = db_path_2.with_suffix(".hash").read_text().strip()

    assert db_path_1 == db_path_2  # same path
    assert hash_1 != hash_2  # different content hash


def test_clear_cache_all(tmp_path: Path, minimal_zorkscript: str) -> None:
    """Clears all .db files."""
    from anyzork.config import Config

    project_dir = _make_project_dir(tmp_path, minimal_zorkscript)
    archive_path = _pack_archive(project_dir, tmp_path / "fixture-game.zork")
    cache_dir = tmp_path / "cache"

    cfg = Config(cache_dir=cache_dir, games_dir=tmp_path, saves_dir=tmp_path / "saves")

    ensure_compiled(archive_path, cfg)
    assert any(cache_dir.glob("*.db"))

    count = clear_cache(cfg=cfg)

    assert count == 1
    assert not any(cache_dir.glob("*.db"))
    assert not any(cache_dir.glob("*.hash"))


def test_clear_cache_specific(tmp_path: Path, minimal_zorkscript: str) -> None:
    """Clears one game's cache."""
    from anyzork.config import Config

    project_dir = _make_project_dir(tmp_path, minimal_zorkscript)
    archive_path = _pack_archive(project_dir, tmp_path / "fixture-game.zork")
    cache_dir = tmp_path / "cache"

    cfg = Config(cache_dir=cache_dir, games_dir=tmp_path, saves_dir=tmp_path / "saves")

    ensure_compiled(archive_path, cfg)

    count = clear_cache("fixture-game", cfg)

    assert count == 1
    assert not any(cache_dir.glob("*.db"))


def test_play_with_archive(
    monkeypatch, tmp_path: Path, minimal_zorkscript: str
) -> None:
    """Full flow: create project -> pack -> play -> verify save created."""
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    cache_dir = tmp_path / "cache"
    library_dir.mkdir()

    project_dir = _make_project_dir(tmp_path, minimal_zorkscript)
    archive_path = _pack_archive(project_dir, library_dir / "fixture-game.zork")
    started_paths: list[Path] = []

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir
            self.cache_dir = cache_dir
            self.catalog_url = DEFAULT_CATALOG_URL
            self.upload_url = DEFAULT_UPLOAD_URL

    def fake_start(self) -> None:
        started_paths.append(self.db.path)

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr("anyzork.engine.game.GameEngine.start", fake_start)

    result = runner.invoke(cli, ["play", "fixture-game", "--save", "alpha"])

    assert result.exit_code == 0, result.output
    assert len(started_paths) == 1
    save_path = started_paths[-1]
    assert save_path.exists()
    assert saves_dir in save_path.parents

    # Verify cache was created
    assert any(cache_dir.glob("*.db"))

    # Verify the save is a valid SQLite database
    from anyzork.db.schema import GameDB

    with GameDB(save_path) as db:
        meta = db.get_all_meta()
        assert meta is not None
        assert meta["save_slot"] == "alpha"


def test_list_shows_archive_games(
    monkeypatch, tmp_path: Path, minimal_zorkscript: str
) -> None:
    """list command shows games from .zork archives."""
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    cache_dir = tmp_path / "cache"
    library_dir.mkdir()

    project_dir = _make_project_dir(tmp_path, minimal_zorkscript)
    _pack_archive(project_dir, library_dir / "fixture-game.zork")

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir
            self.cache_dir = cache_dir
            self.catalog_url = DEFAULT_CATALOG_URL
            self.upload_url = DEFAULT_UPLOAD_URL

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(cli, ["list"])

    assert result.exit_code == 0, result.output
    assert "Game Library" in result.output
    assert "fixture-game" in result.output
    assert "Fixture Game" in result.output


def test_resolve_game_reference_finds_archive(
    tmp_path: Path, minimal_zorkscript: str
) -> None:
    """resolve_game_reference can find an archive by stem."""
    from anyzork.config import Config

    library_dir = tmp_path / "library"
    library_dir.mkdir()

    project_dir = _make_project_dir(tmp_path, minimal_zorkscript)
    _pack_archive(project_dir, library_dir / "fixture-game.zork")

    cfg = Config(
        games_dir=library_dir,
        saves_dir=tmp_path / "saves",
        cache_dir=tmp_path / "cache",
    )

    resolved = library_service.resolve_game_reference("fixture-game", cfg)
    assert resolved == (library_dir / "fixture-game.zork").resolve()


def test_read_archive_metadata(tmp_path: Path, minimal_zorkscript: str) -> None:
    """read_archive_metadata extracts project info from .zork archives."""
    project_dir = _make_project_dir(tmp_path, minimal_zorkscript)
    archive_path = _pack_archive(project_dir, tmp_path / "fixture-game.zork")

    meta = library_service.read_archive_metadata(archive_path)

    assert meta is not None
    assert meta["title"] == "Fixture Game"
    assert meta["author"] == "Test Author"
    assert meta["slug"] == "fixture-game"
    assert meta["tags"] == ["test"]


def test_read_archive_metadata_returns_none_for_sqlite(
    compiled_game_path: Path,
) -> None:
    """read_archive_metadata returns None for SQLite .zork files."""
    meta = library_service.read_archive_metadata(compiled_game_path)
    assert meta is None


def test_clear_cache_programmatic(
    tmp_path: Path, minimal_zorkscript: str
) -> None:
    """clear_cache removes cached .db files."""
    from anyzork.config import Config

    library_dir = tmp_path / "library"
    cache_dir = tmp_path / "cache"
    library_dir.mkdir()

    project_dir = _make_project_dir(tmp_path, minimal_zorkscript)
    archive_path = _pack_archive(project_dir, library_dir / "fixture-game.zork")

    cfg = Config(
        games_dir=library_dir,
        saves_dir=tmp_path / "saves",
        cache_dir=cache_dir,
    )
    ensure_compiled(archive_path, cfg)
    assert any(cache_dir.glob("*.db"))

    count = clear_cache(cfg=cfg)
    assert count == 1
    assert not any(cache_dir.glob("*.db"))
