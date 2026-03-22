"""Tests for anyzork.services.health and the doctor CLI command."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from anyzork import cli as cli_module
from anyzork.cli import cli
from anyzork.config import DEFAULT_CATALOG_URL, DEFAULT_UPLOAD_URL
from anyzork.services.health import fix_issues, run_health_checks


def _create_fake_zork(path: Path, game_id: str = "test-game") -> None:
    """Create a minimal .zork SQLite file with a metadata table."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE metadata ("
        "  id INTEGER PRIMARY KEY,"
        "  game_id TEXT,"
        "  title TEXT,"
        "  source_game_id TEXT,"
        "  source_path TEXT,"
        "  save_slot TEXT,"
        "  is_template INTEGER,"
        "  last_played_at TEXT,"
        "  version TEXT,"
        "  prompt_system_version TEXT"
        ")"
    )
    conn.execute(
        "INSERT INTO metadata (id, game_id, title) VALUES (1, ?, ?)",
        (game_id, "Test Game"),
    )
    conn.commit()
    conn.close()


class _FakeConfig:
    """Minimal config for test isolation."""

    def __init__(self, games_dir: Path, saves_dir: Path) -> None:
        self.games_dir = games_dir
        self.saves_dir = saves_dir
        self.narrator_enabled = False
        self.catalog_url = DEFAULT_CATALOG_URL
        self.upload_url = DEFAULT_UPLOAD_URL


class TestRunHealthChecks:
    def test_no_issues_when_saves_match_games(self, tmp_path: Path) -> None:
        games_dir = tmp_path / "games"
        saves_dir = tmp_path / "saves"
        games_dir.mkdir()
        saves_dir.mkdir()

        _create_fake_zork(games_dir / "my_game.zork", "game-id-1")
        save_dir = saves_dir / "my_game"
        _create_fake_zork(save_dir / "default.zork", "save-id-1")

        cfg = _FakeConfig(games_dir, saves_dir)
        issues = run_health_checks(cfg)
        assert issues == []

    def test_detects_orphan_save(self, tmp_path: Path) -> None:
        games_dir = tmp_path / "games"
        saves_dir = tmp_path / "saves"
        games_dir.mkdir()
        saves_dir.mkdir()

        # Game exists for "my_game" but saves exist for "deleted_game"
        _create_fake_zork(games_dir / "my_game.zork", "game-id-1")
        orphan_dir = saves_dir / "deleted_game"
        _create_fake_zork(orphan_dir / "default.zork", "save-id-2")

        cfg = _FakeConfig(games_dir, saves_dir)
        issues = run_health_checks(cfg)
        assert len(issues) == 1
        assert issues[0].kind == "orphan_save"
        assert issues[0].path == orphan_dir

    def test_detects_empty_save_dir(self, tmp_path: Path) -> None:
        games_dir = tmp_path / "games"
        saves_dir = tmp_path / "saves"
        games_dir.mkdir()
        saves_dir.mkdir()

        _create_fake_zork(games_dir / "my_game.zork", "game-id-1")
        empty_dir = saves_dir / "my_game"
        empty_dir.mkdir()

        cfg = _FakeConfig(games_dir, saves_dir)
        issues = run_health_checks(cfg)
        assert len(issues) == 1
        assert issues[0].kind == "empty_save_dir"
        assert issues[0].path == empty_dir

    def test_no_issues_when_saves_dir_missing(self, tmp_path: Path) -> None:
        games_dir = tmp_path / "games"
        saves_dir = tmp_path / "saves"
        games_dir.mkdir()
        # saves_dir intentionally does not exist

        cfg = _FakeConfig(games_dir, saves_dir)
        issues = run_health_checks(cfg)
        assert issues == []

    def test_detects_multiple_issues(self, tmp_path: Path) -> None:
        games_dir = tmp_path / "games"
        saves_dir = tmp_path / "saves"
        games_dir.mkdir()
        saves_dir.mkdir()

        # One orphan, one empty
        orphan_dir = saves_dir / "deleted_game"
        _create_fake_zork(orphan_dir / "slot1.zork", "save-id-1")
        empty_dir = saves_dir / "another_game"
        empty_dir.mkdir()

        cfg = _FakeConfig(games_dir, saves_dir)
        issues = run_health_checks(cfg)
        assert len(issues) == 2
        kinds = {i.kind for i in issues}
        assert kinds == {"orphan_save", "empty_save_dir"}


class TestFixIssues:
    def test_fix_deletes_orphan_dir(self, tmp_path: Path) -> None:
        games_dir = tmp_path / "games"
        saves_dir = tmp_path / "saves"
        games_dir.mkdir()
        saves_dir.mkdir()

        orphan_dir = saves_dir / "deleted_game"
        _create_fake_zork(orphan_dir / "default.zork", "save-id-1")

        cfg = _FakeConfig(games_dir, saves_dir)
        issues = run_health_checks(cfg)
        assert len(issues) == 1

        cleaned = fix_issues(issues, cfg)
        assert len(cleaned) == 1
        assert not orphan_dir.exists()

    def test_fix_deletes_empty_dir(self, tmp_path: Path) -> None:
        games_dir = tmp_path / "games"
        saves_dir = tmp_path / "saves"
        games_dir.mkdir()
        saves_dir.mkdir()

        empty_dir = saves_dir / "my_game"
        empty_dir.mkdir()

        cfg = _FakeConfig(games_dir, saves_dir)
        issues = run_health_checks(cfg)
        cleaned = fix_issues(issues, cfg)
        assert len(cleaned) == 1
        assert not empty_dir.exists()

    def test_fix_returns_empty_when_no_issues(self, tmp_path: Path) -> None:
        games_dir = tmp_path / "games"
        saves_dir = tmp_path / "saves"
        games_dir.mkdir()
        saves_dir.mkdir()

        cfg = _FakeConfig(games_dir, saves_dir)
        issues = run_health_checks(cfg)
        cleaned = fix_issues(issues, cfg)
        assert cleaned == []


class TestDoctorCliNoIssues:
    def test_doctor_cli_no_issues(self, monkeypatch, tmp_path: Path) -> None:
        games_dir = tmp_path / "games"
        saves_dir = tmp_path / "saves"
        games_dir.mkdir()
        saves_dir.mkdir()

        _create_fake_zork(games_dir / "my_game.zork", "game-id-1")
        save_dir = saves_dir / "my_game"
        _create_fake_zork(save_dir / "default.zork", "save-id-1")

        class FakeConfig:
            def __init__(self, **_kwargs) -> None:
                self.games_dir = games_dir
                self.saves_dir = saves_dir
                self.narrator_enabled = False
                self.catalog_url = DEFAULT_CATALOG_URL
                self.upload_url = DEFAULT_UPLOAD_URL

        monkeypatch.setattr(cli_module, "Config", FakeConfig)

        runner = CliRunner()
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "All clear" in result.output


class TestDoctorCliWithIssues:
    def test_doctor_cli_shows_issues(self, monkeypatch, tmp_path: Path) -> None:
        games_dir = tmp_path / "games"
        saves_dir = tmp_path / "saves"
        games_dir.mkdir()
        saves_dir.mkdir()

        orphan_dir = saves_dir / "deleted_game"
        _create_fake_zork(orphan_dir / "default.zork", "save-id-1")

        class FakeConfig:
            def __init__(self, **_kwargs) -> None:
                self.games_dir = games_dir
                self.saves_dir = saves_dir
                self.narrator_enabled = False
                self.catalog_url = DEFAULT_CATALOG_URL
                self.upload_url = DEFAULT_UPLOAD_URL

        monkeypatch.setattr(cli_module, "Config", FakeConfig)

        runner = CliRunner()
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "1 issue(s) found" in result.output
        assert "--fix" in result.output


class TestDoctorCliWithFix:
    def test_doctor_cli_fix_cleans_issues(self, monkeypatch, tmp_path: Path) -> None:
        games_dir = tmp_path / "games"
        saves_dir = tmp_path / "saves"
        games_dir.mkdir()
        saves_dir.mkdir()

        orphan_dir = saves_dir / "deleted_game"
        _create_fake_zork(orphan_dir / "default.zork", "save-id-1")

        class FakeConfig:
            def __init__(self, **_kwargs) -> None:
                self.games_dir = games_dir
                self.saves_dir = saves_dir
                self.narrator_enabled = False
                self.catalog_url = DEFAULT_CATALOG_URL
                self.upload_url = DEFAULT_UPLOAD_URL

        monkeypatch.setattr(cli_module, "Config", FakeConfig)

        runner = CliRunner()
        result = runner.invoke(cli, ["doctor", "--fix"])
        assert result.exit_code == 0
        assert "Fixed" in result.output
        assert not orphan_dir.exists()
