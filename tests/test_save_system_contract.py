from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from anyzork import cli as cli_module
from anyzork.db.schema import GameDB
from tests.build_test_game import build_test_game


def _save_system_ready() -> bool:
    """Return True once the managed save architecture exists again."""
    try:
        cfg = cli_module.Config()
    except Exception:
        return False

    play_param_names = {param.name for param in cli_module.play.params}
    return hasattr(cfg, "saves_dir") and "slot" in play_param_names


def _stamp_future_metadata(
    path: Path,
    *,
    game_id: str,
    is_template: int,
    source_game_id: str | None = None,
    source_path: str | None = None,
    save_slot: str | None = None,
    last_played_at: str | None = None,
) -> None:
    """Add future save metadata columns to a fixture file."""
    columns = {
        "game_id": "TEXT",
        "source_game_id": "TEXT",
        "source_path": "TEXT",
        "save_slot": "TEXT",
        "last_played_at": "TEXT",
        "is_template": "INTEGER NOT NULL DEFAULT 0",
    }
    with sqlite3.connect(path) as conn:
        existing = {
            row[1] for row in conn.execute("PRAGMA table_info(metadata)").fetchall()
        }
        for column, ddl in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE metadata ADD COLUMN {column} {ddl}")
        conn.execute(
            """
            UPDATE metadata
            SET game_id = ?,
                source_game_id = ?,
                source_path = ?,
                save_slot = ?,
                last_played_at = ?,
                is_template = ?
            WHERE id = 1
            """,
            (
                game_id,
                source_game_id,
                source_path,
                save_slot,
                last_played_at,
                is_template,
            ),
        )
        conn.commit()


def _fixture_library_game(tmp_path: Path) -> Path:
    """Prepare a library-style game file with future provenance metadata."""
    source = build_test_game()
    library_dir = tmp_path / "library"
    library_dir.mkdir(parents=True, exist_ok=True)
    target = library_dir / "lantern_archive.zork"
    shutil.copy2(source, target)
    _stamp_future_metadata(
        target,
        game_id="lantern_archive_game",
        is_template=1,
        source_path=str(target),
    )
    return target


def _read_metadata(path: Path) -> dict:
    db = GameDB(path)
    try:
        return db.get_all_meta() or {}
    finally:
        db.close()


def test_metadata_migration_backfills_future_save_columns(tmp_path: Path) -> None:
    if not _save_system_ready():
        pytest.skip("Save system metadata migration has not landed yet.")

    legacy_path = build_test_game()
    migrated = tmp_path / "legacy_world.zork"
    shutil.copy2(legacy_path, migrated)

    db = GameDB(migrated)
    try:
        meta_columns = {row["name"] for row in db._fetchall("PRAGMA table_info(metadata)")}
        assert {
            "game_id",
            "source_game_id",
            "source_path",
            "save_slot",
            "last_played_at",
            "is_template",
        }.issubset(meta_columns)

        meta = db.get_all_meta() or {}
        assert meta["game_id"]
        assert meta["source_game_id"] is None
        assert meta["source_path"] is None
        assert meta["save_slot"] is None
        assert meta["last_played_at"] is None
        assert meta["is_template"] == 0
    finally:
        db.close()


def test_play_creates_and_resets_managed_save_slot(monkeypatch, tmp_path: Path) -> None:
    if not _save_system_ready():
        pytest.skip("Managed save slots have not landed yet.")

    runner = CliRunner()
    library_game = _fixture_library_game(tmp_path)
    saves_dir = tmp_path / "saves"
    saved_db_path_holder: dict[str, Path] = {}

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = tmp_path / "library"
            self.saves_dir = saves_dir

    def fake_start(self) -> None:
        saved_db_path_holder["path"] = self.db.path

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr("anyzork.engine.game.GameEngine.start", fake_start)

    first = runner.invoke(cli_module.cli, ["play", "lantern_archive", "--slot", "case-a"])
    assert first.exit_code == 0

    save_files = list(saves_dir.glob("*/case-a.zork"))
    assert len(save_files) == 1
    save_file = save_files[0]
    save_meta = _read_metadata(save_file)
    source_meta = _read_metadata(library_game)
    assert save_meta["is_template"] == 0
    assert save_meta["save_slot"] == "case-a"
    assert save_meta["source_game_id"] == source_meta["game_id"]
    assert save_meta["game_id"] != source_meta["game_id"]
    assert saved_db_path_holder["path"] == save_file

    with GameDB(save_file) as db:
        db.update_player(current_room_id="observatory")

    restarted = runner.invoke(
        cli_module.cli,
        ["play", "lantern_archive", "--slot", "case-a", "--new"],
    )
    assert restarted.exit_code == 0

    with GameDB(save_file) as db:
        assert db.get_player()["current_room_id"] == "entrance_hall"


def test_list_separates_library_games_and_saves(monkeypatch, tmp_path: Path) -> None:
    if not _save_system_ready():
        pytest.skip("Managed library/save listing has not landed yet.")

    runner = CliRunner()
    library_game = _fixture_library_game(tmp_path)
    saves_dir = tmp_path / "saves"
    save_dir = saves_dir / "slot-game-id"
    save_dir.mkdir(parents=True, exist_ok=True)
    save_file = save_dir / "case-a.zork"
    shutil.copy2(library_game, save_file)
    _stamp_future_metadata(
        save_file,
        game_id="run_case_a",
        is_template=0,
        source_game_id="lantern_archive_game",
        source_path=str(library_game),
        save_slot="case-a",
        last_played_at="2026-03-19T12:00:00+00:00",
    )

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.games_dir = tmp_path / "library"
            self.saves_dir = saves_dir

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(cli_module.cli, ["list"])

    assert result.exit_code == 0
    assert "Game Library" in result.output
    assert "Managed Saves" in result.output
    assert "lantern_archive" in result.output
    assert "case-a" in result.output
    assert "Ref" in result.output


def test_saves_lists_slots_for_one_library_game(monkeypatch, tmp_path: Path) -> None:
    if not _save_system_ready():
        pytest.skip("Managed library/save listing has not landed yet.")

    runner = CliRunner()
    library_game = _fixture_library_game(tmp_path)
    saves_dir = tmp_path / "saves"
    save_dir = saves_dir / "lantern_archive_game"
    save_dir.mkdir(parents=True, exist_ok=True)
    save_file = save_dir / "case-a.zork"
    shutil.copy2(library_game, save_file)
    _stamp_future_metadata(
        save_file,
        game_id="run_case_a",
        is_template=0,
        source_game_id="lantern_archive_game",
        source_path=str(library_game),
        save_slot="case-a",
        last_played_at="2026-03-19T12:00:00+00:00",
    )

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.games_dir = tmp_path / "library"
            self.saves_dir = saves_dir

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(cli_module.cli, ["saves", "lantern_archive"])

    assert result.exit_code == 0
    assert "Saves for" in result.output
    assert "case-a" in result.output


def test_delete_save_removes_named_slot(monkeypatch, tmp_path: Path) -> None:
    if not _save_system_ready():
        pytest.skip("Managed delete-save has not landed yet.")

    runner = CliRunner()
    library_game = _fixture_library_game(tmp_path)
    saves_dir = tmp_path / "saves"
    save_dir = saves_dir / "lantern_archive_game"
    save_dir.mkdir(parents=True, exist_ok=True)
    save_file = save_dir / "case-a.zork"
    shutil.copy2(library_game, save_file)
    _stamp_future_metadata(
        save_file,
        game_id="run_case_a",
        is_template=0,
        source_game_id="lantern_archive_game",
        source_path=str(library_game),
        save_slot="case-a",
        last_played_at="2026-03-19T12:00:00+00:00",
    )

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.games_dir = tmp_path / "library"
            self.saves_dir = saves_dir

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(
        cli_module.cli,
        ["delete-save", "lantern_archive", "--slot", "case-a"],
    )

    assert result.exit_code == 0
    assert not save_file.exists()


def test_delete_removes_library_game_and_managed_saves(monkeypatch, tmp_path: Path) -> None:
    if not _save_system_ready():
        pytest.skip("Managed delete has not landed yet.")

    runner = CliRunner()
    library_game = _fixture_library_game(tmp_path)
    saves_dir = tmp_path / "saves"
    save_dir = saves_dir / "lantern_archive_game"
    save_dir.mkdir(parents=True, exist_ok=True)
    save_file = save_dir / "case-a.zork"
    shutil.copy2(library_game, save_file)
    _stamp_future_metadata(
        save_file,
        game_id="run_case_a",
        is_template=0,
        source_game_id="lantern_archive_game",
        source_path=str(library_game),
        save_slot="case-a",
        last_played_at="2026-03-19T12:00:00+00:00",
    )

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.games_dir = tmp_path / "library"
            self.saves_dir = saves_dir

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(cli_module.cli, ["delete", "lantern_archive", "--yes"])

    assert result.exit_code == 0
    assert not library_game.exists()
    assert not save_dir.exists()
