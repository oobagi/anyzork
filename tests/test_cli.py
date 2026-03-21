from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from anyzork import cli as cli_module
from anyzork.cli import cli


def test_generate_outputs_prompt_for_freeform_concept() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["generate", "A haunted lighthouse on a foggy coast"])

    assert result.exit_code == 0, result.output
    assert "A haunted lighthouse on a foggy coast" in result.output
    assert "You are authoring a complete, playable text adventure in ZorkScript" in result.output


def test_import_reads_zorkscript_from_stdin(tmp_path: Path, minimal_zorkscript: str) -> None:
    runner = CliRunner()
    output_path = tmp_path / "cli_imported.zork"

    result = runner.invoke(
        cli,
        ["import", "-o", str(output_path)],
        input=minimal_zorkscript,
    )

    assert result.exit_code == 0, result.output
    assert output_path.exists()
    assert "Imported game saved to" in result.output


def test_play_creates_and_restarts_managed_save_slot(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    library_dir.mkdir()
    target_game = library_dir / "fixture_game.zork"
    target_game.write_bytes(compiled_game_path.read_bytes())
    started_paths: list[Path] = []

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir

    def fake_start(self) -> None:
        started_paths.append(self.db.path)

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr("anyzork.engine.game.GameEngine.start", fake_start)

    first = runner.invoke(cli, ["play", "fixture_game", "--slot", "alpha"])
    assert first.exit_code == 0, first.output
    assert len(started_paths) == 1
    save_path = started_paths[-1]
    assert save_path.exists()
    assert save_path.parent.name

    second = runner.invoke(cli, ["play", "fixture_game", "--slot", "alpha", "--new"])
    assert second.exit_code == 0, second.output
    assert len(started_paths) == 2
    assert started_paths[-1] == save_path


def test_playing_a_zork_file_path_creates_a_managed_save(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    runner = CliRunner()
    saves_dir = tmp_path / "saves"
    source_game = tmp_path / "local_game.zork"
    source_game.write_bytes(compiled_game_path.read_bytes())
    started_paths: list[Path] = []

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = tmp_path / "library"
            self.saves_dir = saves_dir

    def fake_start(self) -> None:
        started_paths.append(self.db.path)

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr("anyzork.engine.game.GameEngine.start", fake_start)

    result = runner.invoke(cli, ["play", str(source_game)])

    assert result.exit_code == 0, result.output
    assert len(started_paths) == 1
    assert started_paths[0] != source_game
    assert started_paths[0].exists()
    assert saves_dir in started_paths[0].parents
