"""Collect import diagnostics and generate an LLM fix-it prompt."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from anyzork.diagnostics import (
    Diagnostic,
    from_import_spec_error,
    from_zorkscript_error,
)
from anyzork.importer import compile_import_spec
from anyzork.importer._constants import ImportSpecError
from anyzork.lint import lint_spec
from anyzork.zorkscript import ZorkScriptError, parse_zorkscript


@dataclass(frozen=True)
class DoctorResult:
    """Outcome of running the doctor pipeline."""
    diagnostics: list[Diagnostic]
    phase_reached: str  # "parse" | "lint" | "compile"


def collect_diagnostics(source_text: str) -> DoctorResult:
    """Run parse -> lint -> compile and collect all diagnostics."""
    diagnostics: list[Diagnostic] = []

    # Phase 1: Parse
    try:
        spec = parse_zorkscript(source_text)
    except ZorkScriptError as exc:
        diagnostics.append(from_zorkscript_error(exc))
        return DoctorResult(diagnostics=diagnostics, phase_reached="parse")

    # Phase 2: Lint (accumulates all errors)
    diagnostics.extend(lint_spec(spec))

    # Phase 3: Compile (stops at first error)
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_output = Path(tmp_dir) / "doctor_check.zork"
        try:
            _path, warnings = compile_import_spec(spec, tmp_output)
            for warning_str in warnings:
                diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        category="validate",
                        message=warning_str,
                        line=None,
                        hint=None,
                    )
                )
        except ImportSpecError as exc:
            diagnostics.append(from_import_spec_error(exc))
        except Exception as exc:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    category="compile",
                    message=str(exc),
                    line=None,
                    hint=None,
                )
            )

    return DoctorResult(diagnostics=diagnostics, phase_reached="compile")


def build_fix_prompt(
    source_text: str,
    diagnostics: list[Diagnostic],
    *,
    source_files: list[str] | None = None,
) -> str:
    """Build a ready-to-paste LLM fix-it prompt."""
    lines = [
        "Fix the errors in this ZorkScript. Return ONLY the corrected",
        "ZorkScript with no explanation or commentary.",
    ]

    if source_files and len(source_files) > 1:
        lines.append("")
        lines.append(
            "This is a multi-file project. Separate each file with a header line:"
        )
        for f in source_files:
            lines.append(f"  # {f}")

    lines.append("")
    lines.append("## Errors")
    lines.append("")
    for i, diag in enumerate(diagnostics, 1):
        lines.append(f"{i}. {diag}")
    lines.append("")
    lines.append("## ZorkScript Source")
    lines.append("")
    lines.append("```zorkscript")
    lines.append(source_text)
    lines.append("```")
    return "\n".join(lines)


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard. Returns True on success."""
    for cmd in (
        ["pbcopy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    ):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text.encode(), check=True)
                return True
            except subprocess.SubprocessError:
                continue
    return False
