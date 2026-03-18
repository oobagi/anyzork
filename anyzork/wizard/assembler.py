"""Assemble wizard field values into a single prompt string.

The assembled prompt is a plain-text string with labeled sections.
Sections for omitted fields are not included. A minimal prompt (only
world description filled) looks identical to a freeform prompt.
"""

from __future__ import annotations

from typing import Any

from anyzork.wizard.fields import FIELDS, SCALE_DETAIL


def assemble_prompt(values: dict[str, Any]) -> str:
    """Assemble wizard field values into a prompt string.

    Args:
        values: Dict mapping field keys to their values.

    Returns:
        The assembled prompt string ready for generate_game().
    """
    sections: list[str] = []

    for field_def in FIELDS:
        raw = values.get(field_def.key)
        if raw is None:
            continue

        # Expand scale shorthand to descriptive form.
        if field_def.key == "scale" and isinstance(raw, str):
            raw = SCALE_DETAIL.get(raw.lower(), raw)

        formatted = field_def.format_for_prompt(raw)
        if formatted:
            sections.append(formatted)

    return "\n\n".join(sections)
