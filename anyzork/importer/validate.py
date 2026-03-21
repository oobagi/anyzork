"""Import-specific validation helpers."""

from __future__ import annotations

from typing import Any

from anyzork.importer._constants import ALLOWED_EXIT_DIRECTIONS, ImportSpecError
from anyzork.validation import validate_game


def _validate_imported_game(db: Any) -> list[str]:
    results = validate_game(db)
    errors = [finding.message for finding in results if finding.severity == "error"]
    if errors:
        preview = "; ".join(errors[:8])
        raise ImportSpecError(f"Imported game failed validation: {preview}")
    return [finding.message for finding in results if finding.severity != "error"]


def _validate_exit_directions(spec: dict[str, Any]) -> None:
    """Reject imported exits that use unsupported direction labels."""
    invalid: list[str] = []
    for exit_row in spec.get("exits", []):
        direction = str(exit_row.get("direction", "")).strip().lower()
        if direction and direction not in ALLOWED_EXIT_DIRECTIONS:
            invalid.append(direction)
    if invalid:
        unique = ", ".join(sorted(set(invalid)))
        allowed = ", ".join(ALLOWED_EXIT_DIRECTIONS)
        raise ImportSpecError(
            f"Unsupported exit direction(s): {unique}. Allowed directions are: {allowed}."
        )
