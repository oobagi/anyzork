from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from anyzork.cli import cli


def _minimal_zorkscript() -> str:
    return """\
game {
  title    "CLI Import Game"
  author   "Imported through the CLI."
  max_score 0
  win      [test_win]
}

player {
  start foyer
  hp    100
}

room foyer {
  name        "Foyer"
  description "A quiet foyer."
  short       "A quiet foyer."
  region      "house"
  start       true
}

flag test_win "Test win condition"

on "win" in [foyer] {
  effect set_flag(test_win)
  success "You win."
  once
}
"""


def test_cli_import_reads_zorkscript_from_stdin(tmp_path: Path) -> None:
    runner = CliRunner()
    output_path = tmp_path / "cli_imported.zork"

    result = runner.invoke(
        cli,
        ["import", "-o", str(output_path)],
        input=_minimal_zorkscript(),
    )

    assert result.exit_code == 0, result.output
    assert output_path.exists()
    assert "Imported game saved to" in result.output


def test_cli_import_template_prints_zorkscript_prompt() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["import", "--print-template"])

    assert result.exit_code == 0
    assert "ZorkScript" in result.output
    assert "game {" in result.output
