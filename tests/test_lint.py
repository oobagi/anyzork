"""Tests for anyzork.diagnostics and anyzork.lint modules."""

from __future__ import annotations

import copy
from pathlib import Path

from click.testing import CliRunner

from anyzork.cli import cli
from anyzork.diagnostics import (
    Diagnostic,
    from_import_spec_error,
    from_validation_error,
    from_zorkscript_error,
)
from anyzork.importer._constants import ImportSpecError
from anyzork.lint import lint_spec
from anyzork.validation import ValidationError
from anyzork.zorkscript import ZorkScriptError

# ── diagnostics.py ───────────────────────────────────────────────────────


class TestDiagnosticStr:
    def test_formats_with_line_and_hint(self) -> None:
        d = Diagnostic("error", "parse", "unexpected token", 42, "check syntax")
        assert str(d) == (
            "[ERROR][parse] line 42: unexpected token\n  hint: check syntax"
        )

    def test_formats_without_line_or_hint(self) -> None:
        d = Diagnostic("warning", "spatial", "one-way exit", None, None)
        assert str(d) == "[WARNING][spatial] one-way exit"


class TestFromZorkScriptError:
    def test_extracts_line_and_strips_prefix(self) -> None:
        exc = ZorkScriptError("unexpected '}'", line=10)
        diag = from_zorkscript_error(exc)
        assert diag.severity == "error"
        assert diag.category == "parse"
        assert diag.line == 10
        assert diag.message == "unexpected '}'"
        assert "line 10" not in diag.message

    def test_no_line(self) -> None:
        exc = ZorkScriptError("empty input")
        diag = from_zorkscript_error(exc)
        assert diag.line is None
        assert diag.message == "empty input"


class TestFromImportSpecError:
    def test_wraps_as_compile_error(self) -> None:
        exc = ImportSpecError("bad format version")
        diag = from_import_spec_error(exc)
        assert diag.severity == "error"
        assert diag.category == "compile"
        assert diag.message == "bad format version"
        assert diag.line is None
        assert diag.hint is None


class TestFromValidationError:
    def test_passes_through_fields(self) -> None:
        ve = ValidationError(severity="warning", category="spatial", message="loop")
        diag = from_validation_error(ve)
        assert diag.severity == "warning"
        assert diag.category == "spatial"
        assert diag.message == "loop"


# ── lint.py ──────────────────────────────────────────────────────────────


class TestLintSpecValid:
    def test_valid_spec_returns_empty(self, minimal_import_spec: dict) -> None:
        assert lint_spec(minimal_import_spec) == []


class TestLintStructure:
    def test_missing_game_block(self, minimal_import_spec: dict) -> None:
        spec = copy.deepcopy(minimal_import_spec)
        del spec["game"]
        diags = lint_spec(spec)
        assert any(d.category == "structure" and "game" in d.message for d in diags)

    def test_missing_game_title(self, minimal_import_spec: dict) -> None:
        spec = copy.deepcopy(minimal_import_spec)
        spec["game"]["title"] = ""
        diags = lint_spec(spec)
        assert any(
            d.category == "structure" and "title" in d.message for d in diags
        )

    def test_missing_player_block(self, minimal_import_spec: dict) -> None:
        spec = copy.deepcopy(minimal_import_spec)
        del spec["player"]
        diags = lint_spec(spec)
        assert any(d.category == "structure" and "player" in d.message for d in diags)

    def test_no_rooms(self, minimal_import_spec: dict) -> None:
        spec = copy.deepcopy(minimal_import_spec)
        spec["rooms"] = []
        diags = lint_spec(spec)
        assert any(d.category == "structure" and "rooms" in d.message for d in diags)

    def test_duplicate_entity_ids(self, minimal_import_spec: dict) -> None:
        spec = copy.deepcopy(minimal_import_spec)
        spec["items"] = [
            {"id": "foyer", "name": "Rug", "description": "A rug."},
        ]
        diags = lint_spec(spec)
        assert any(
            d.category == "structure" and "duplicate" in d.message for d in diags
        )


class TestLintReference:
    def test_bad_start_room_id(self, minimal_import_spec: dict) -> None:
        spec = copy.deepcopy(minimal_import_spec)
        spec["player"]["start_room_id"] = "foyerr"
        diags = lint_spec(spec)
        ref_diags = [d for d in diags if d.category == "reference"]
        assert any("start_room_id" in d.message for d in ref_diags)
        # "foyerr" is close to "foyer" so there should be a "did you mean?" hint
        assert any(d.hint and "did you mean" in d.hint for d in ref_diags)

    def test_exit_referencing_nonexistent_room(
        self, minimal_import_spec: dict
    ) -> None:
        spec = copy.deepcopy(minimal_import_spec)
        spec["exits"][0]["to_room_id"] = "nowhere"
        diags = lint_spec(spec)
        assert any(
            d.category == "reference" and "nowhere" in d.message for d in diags
        )

    def test_item_referencing_nonexistent_room(
        self, minimal_import_spec: dict
    ) -> None:
        spec = copy.deepcopy(minimal_import_spec)
        spec["items"] = [
            {"id": "key", "name": "Key", "description": "A key.", "room_id": "vault"},
        ]
        diags = lint_spec(spec)
        assert any(
            d.category == "reference" and "vault" in d.message for d in diags
        )


class TestLintDsl:
    def test_unknown_precondition_type(self, minimal_import_spec: dict) -> None:
        spec = copy.deepcopy(minimal_import_spec)
        spec["commands"][0]["preconditions"] = [{"type": "is_raining"}]
        diags = lint_spec(spec)
        dsl_diags = [d for d in diags if d.category == "dsl"]
        assert any("precondition" in d.message for d in dsl_diags)
        assert any(d.hint and "valid types" in d.hint for d in dsl_diags)

    def test_unknown_effect_type(self, minimal_import_spec: dict) -> None:
        spec = copy.deepcopy(minimal_import_spec)
        spec["commands"][0]["effects"] = [{"type": "explode"}]
        diags = lint_spec(spec)
        dsl_diags = [d for d in diags if d.category == "dsl"]
        assert any("effect" in d.message for d in dsl_diags)
        assert any(d.hint and "valid types" in d.hint for d in dsl_diags)


class TestLintExitDirection:
    def test_invalid_direction(self, minimal_import_spec: dict) -> None:
        spec = copy.deepcopy(minimal_import_spec)
        spec["exits"][0]["direction"] = "northwest"
        diags = lint_spec(spec)
        assert any(
            d.category == "reference" and "direction" in d.message for d in diags
        )


class TestLintSpatial:
    def test_one_way_exit_is_warning(self, minimal_import_spec: dict) -> None:
        spec = copy.deepcopy(minimal_import_spec)
        # Remove the reverse exit so foyer->study is one-way
        spec["exits"] = [spec["exits"][0]]
        diags = lint_spec(spec)
        spatial = [d for d in diags if d.category == "spatial"]
        assert len(spatial) == 1
        assert spatial[0].severity == "warning"
        assert "one-way" in spatial[0].message

    def test_valid_spec_with_one_way_exits_code_zero(
        self, minimal_import_spec: dict
    ) -> None:
        """Warnings-only means exit code 0 (no errors)."""
        spec = copy.deepcopy(minimal_import_spec)
        spec["exits"] = [spec["exits"][0]]
        diags = lint_spec(spec)
        errors = [d for d in diags if d.severity == "error"]
        assert errors == []


# ── CLI tests ────────────────────────────────────────────────────────────


class TestLintCli:
    def test_valid_file_no_issues(
        self, tmp_path: Path, minimal_zorkscript: str
    ) -> None:
        src = tmp_path / "game.zork"
        src.write_text(minimal_zorkscript, encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(cli, ["lint", str(src)])
        assert result.exit_code == 0
        assert "No issues found" in result.output

    def test_invalid_file_exits_with_code_1(self, tmp_path: Path) -> None:
        src = tmp_path / "bad.zork"
        src.write_text("this is not valid zorkscript at all", encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(cli, ["lint", str(src)])
        assert result.exit_code == 1


# ── --report CLI tests ───────────────────────────────────────────────────


_ZORKSCRIPT_ONE_WAY_EXIT = """\
game {
  title "One-Way Game"
  author "Test author."
  max_score 0
  win [game_won]
}

player {
  start foyer
}

room foyer {
  name "Foyer"
  description "A quiet foyer."
  short "A quiet foyer."

  start true

  exit north -> study
}

room study {
  name "Study"
  description "A cramped study."
  short "A cramped study."

}

flag game_won "Tracks victory."

on "win game" in [foyer, study] {
  effect set_flag(game_won)
  success "You win."
}
"""


class TestImportReportCli:
    def test_report_valid_file(
        self, tmp_path: Path, minimal_zorkscript: str
    ) -> None:
        """--report on a valid file shows entity counts and no errors."""
        src = tmp_path / "game.zork"
        src.write_text(minimal_zorkscript, encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(
            cli, ["import", str(src), "-o", str(tmp_path / "out.zork"), "--report"]
        )
        assert result.exit_code == 0
        assert "Entities:" in result.output
        assert "rooms" in result.output
        assert "No issues found" in result.output or "0 errors" in result.output

    def test_report_file_with_lint_warnings(self, tmp_path: Path) -> None:
        """--report on a file with one-way exits shows warnings."""
        src = tmp_path / "oneway.zork"
        src.write_text(_ZORKSCRIPT_ONE_WAY_EXIT, encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(
            cli, ["import", str(src), "-o", str(tmp_path / "out.zork"), "--report"]
        )
        # Warnings don't cause a non-zero exit code
        assert result.exit_code == 0
        assert "one-way" in result.output.lower() or "WARNING" in result.output

    def test_report_file_fails_compilation(self, tmp_path: Path) -> None:
        """--report on an unparseable file shows failure indicator."""
        src = tmp_path / "broken.zork"
        src.write_text("this is not valid zorkscript", encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(
            cli, ["import", str(src), "--report"]
        )
        assert result.exit_code == 1
        assert "FAILED" in result.output
        assert "1 error" in result.output
