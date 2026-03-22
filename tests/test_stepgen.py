"""Tests for single-prompt generation."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from anyzork.cli import cli
from anyzork.services.stepgen import OUTPUT_FILES, build_generation_prompt


class TestBuildGenerationPrompt:
    def test_includes_concept(self) -> None:
        prompt = build_generation_prompt("haunted lighthouse")
        assert "haunted lighthouse" in prompt

    def test_includes_file_headers(self) -> None:
        prompt = build_generation_prompt("test world")
        for filename in OUTPUT_FILES:
            assert f"# {filename}" in prompt

    def test_includes_example_game(self) -> None:
        prompt = build_generation_prompt("test")
        # Should include the full template example
        assert "game {" in prompt
        assert "room cell {" in prompt
        assert "item oil_lantern {" in prompt
        assert "npc guard {" in prompt
        assert "interaction weapon_on_character {" in prompt

    def test_includes_quality_requirements(self) -> None:
        prompt = build_generation_prompt("test", authoring_fields={"scale": "large"})
        assert "13-25 rooms" in prompt

    def test_includes_realism_guidance(self) -> None:
        prompt = build_generation_prompt("test", realism="high")
        assert "Realism: high" in prompt

    def test_no_step_references(self) -> None:
        prompt = build_generation_prompt("test")
        assert "STEP 1" not in prompt
        assert "STEP 2" not in prompt
        assert "STEP 3" not in prompt


class TestOutputFiles:
    def test_expected_files(self) -> None:
        assert "game.zorkscript" in OUTPUT_FILES
        assert "rooms.zorkscript" in OUTPUT_FILES
        assert "items.zorkscript" in OUTPUT_FILES
        assert "npcs.zorkscript" in OUTPUT_FILES
        assert "commands.zorkscript" in OUTPUT_FILES

    def test_count(self) -> None:
        assert len(OUTPUT_FILES) == 7


class TestGenerateCli:
    def test_generate_creates_project_with_output(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli,
                ["generate", "haunted mansion", "-o", "prompt.txt"],
            )
            assert result.exit_code == 0, result.output
            assert Path("prompt.txt").exists()
            content = Path("prompt.txt").read_text()
            assert "haunted mansion" in content

    def test_generate_deduplicates_project_dir(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result1 = runner.invoke(cli, ["generate", "test game", "-o", "p1.txt"])
            assert result1.exit_code == 0
            result2 = runner.invoke(cli, ["generate", "test game", "-o", "p2.txt"])
            assert result2.exit_code == 0
            # Second run should create a different directory
            assert Path("test-game").exists()
            assert Path("test-game-2").exists()

