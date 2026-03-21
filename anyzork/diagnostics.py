"""Unified diagnostic type that converts from the project's error types."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from anyzork.importer._constants import ImportSpecError
    from anyzork.validation import ValidationError
    from anyzork.zorkscript import ZorkScriptError


_LINE_PREFIX_RE = re.compile(r"^line \d+: ")


@dataclass(frozen=True)
class Diagnostic:
    """A single diagnostic finding with severity, category, and optional location."""

    severity: str  # "error" | "warning"
    category: str  # "parse", "compile", "structure", "reference", "spatial", etc.
    message: str  # Human-readable, no Rich markup
    line: int | None  # Source line number, if known
    hint: str | None  # Optional fix suggestion

    def __str__(self) -> str:
        tag = self.severity.upper()
        loc = f"line {self.line}: " if self.line else ""
        base = f"[{tag}][{self.category}] {loc}{self.message}"
        if self.hint:
            base += f"\n  hint: {self.hint}"
        return base


def from_zorkscript_error(exc: ZorkScriptError) -> Diagnostic:
    """Convert a ZorkScriptError into a Diagnostic."""
    msg = str(exc)
    # ZorkScriptError prepends "line N: " when a line number is set.
    # Strip that prefix so the message stays clean.
    msg = _LINE_PREFIX_RE.sub("", msg)
    return Diagnostic(
        severity="error",
        category="parse",
        message=msg,
        line=exc.line,
        hint=None,
    )


def from_import_spec_error(exc: ImportSpecError) -> Diagnostic:
    """Convert an ImportSpecError into a Diagnostic."""
    return Diagnostic(
        severity="error",
        category="compile",
        message=str(exc),
        line=None,
        hint=None,
    )


def from_validation_error(ve: ValidationError) -> Diagnostic:
    """Convert a ValidationError into a Diagnostic."""
    return Diagnostic(
        severity=ve.severity,
        category=ve.category,
        message=ve.message,
        line=None,
        hint=None,
    )


def render_diagnostic(diag: Diagnostic, console: Console) -> None:
    """Print a single diagnostic with Rich color coding."""
    color = {"error": "red", "warning": "yellow"}.get(diag.severity, "white")
    tag = diag.severity.upper()
    loc = f"line {diag.line}: " if diag.line else ""
    console.print(
        f"[{color}]\\[{tag}][{diag.category}][/{color}] {loc}{diag.message}"
    )
    if diag.hint:
        console.print(f"  [dim]hint: {diag.hint}[/dim]")
