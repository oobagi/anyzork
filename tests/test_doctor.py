"""Tests for anyzork.services.doctor and the doctor CLI command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from anyzork.cli import cli
from anyzork.services.doctor import build_fix_prompt, collect_diagnostics

_BROKEN_PARSE = """\
game {
  title
}
"""

_BROKEN_REFS = """\
game {
  title "Bad Refs"
  win [game_won]
}

player {
  start nonexistent_room
}

room foyer {
  name "Foyer"
  description "A foyer."
  short "A foyer."
  start true
}

flag game_won "Win flag."
"""


class TestCollectParseError:
    def test_collect_parse_error(self) -> None:
        result = collect_diagnostics(_BROKEN_PARSE)
        assert result.phase_reached == "parse"
        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].severity == "error"
        assert result.diagnostics[0].category == "parse"


class TestCollectLintErrors:
    def test_collect_lint_errors(self) -> None:
        result = collect_diagnostics(_BROKEN_REFS)
        assert result.phase_reached == "compile"
        assert len(result.diagnostics) >= 1
        categories = {d.category for d in result.diagnostics}
        assert "reference" in categories or "structure" in categories


class TestCollectNoErrors:
    def test_collect_no_errors(self, minimal_zorkscript: str) -> None:
        result = collect_diagnostics(minimal_zorkscript)
        assert result.diagnostics == []


class TestBuildFixPromptFormat:
    def test_build_fix_prompt_format(self) -> None:
        result = collect_diagnostics(_BROKEN_PARSE)
        prompt = build_fix_prompt(_BROKEN_PARSE, result.diagnostics)
        assert "1." in prompt
        assert "```zorkscript" in prompt
        assert "## Errors" in prompt
        assert "Fix the errors" in prompt


class TestBuildFixPromptIncludesHints:
    def test_build_fix_prompt_includes_hints(self) -> None:
        result = collect_diagnostics(_BROKEN_REFS)
        prompt = build_fix_prompt(_BROKEN_REFS, result.diagnostics)
        assert "## Errors" in prompt


class TestRepairCliNoErrors:
    def test_repair_cli_no_errors(self, tmp_path: Path, minimal_zorkscript: str) -> None:
        src = tmp_path / "good.zork"
        src.write_text(minimal_zorkscript, encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(cli, ["repair", str(src)])
        assert result.exit_code == 0
        assert "should import cleanly" in result.output


class TestRepairCliWithErrors:
    def test_repair_cli_with_errors(self, tmp_path: Path) -> None:
        src = tmp_path / "broken.zork"
        src.write_text(_BROKEN_PARSE, encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(cli, ["repair", str(src)])
        assert result.exit_code == 0
        assert "error" in result.output.lower()


class TestImportFailureShowsDoctorHint:
    def test_import_failure_shows_doctor_hint(self, tmp_path: Path) -> None:
        src = tmp_path / "broken.zork"
        src.write_text(_BROKEN_PARSE, encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(cli, ["import", str(src)])
        assert "anyzork repair" in result.output
