from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from anyzork.cli import cli


def test_cli_generate_prints_zorkscript_prompt() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["generate", "A stormy manor murder mystery."])

    assert result.exit_code == 0, result.output
    assert "ZorkScript" in result.output
    assert "A stormy manor murder mystery." in result.output
    assert "game {" in result.output


def test_cli_generate_writes_prompt_to_file(tmp_path: Path) -> None:
    runner = CliRunner()
    output = tmp_path / "author_prompt.txt"

    result = runner.invoke(
        cli,
        [
            "generate",
            "A family thriller across two houses.",
            "--realism",
            "high",
            "-o",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "A family thriller across two houses." in content
    assert "Realism: high" in content
    assert "ZorkScript" in content
