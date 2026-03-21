"""TUI-friendly authoring helpers built on top of the existing wizard/importer logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from anyzork.importer import build_zorkscript_prompt
from anyzork.wizard.assembler import assemble_prompt
from anyzork.wizard.fields import FIELDS, FieldDef, FieldType
from anyzork.wizard.presets import discover_presets, load_preset

_LIST_FIELD_KEYS = {"locations", "characters", "items"}
_MULTI_VALUE_KEYS = {"tone", "genre_tags"}


@dataclass(frozen=True)
class AuthoringBundle:
    """Normalized authoring state plus preview/export text."""

    fields: dict[str, Any]
    preview_prompt: str
    authoring_prompt: str
    realism: str


def available_presets() -> dict[str, dict[str, Any]]:
    """Return built-in and user-defined authoring presets."""
    return discover_presets()


def load_preset_fields(preset_id: str) -> dict[str, Any] | None:
    """Return normalized field values for a preset."""
    return load_preset(preset_id)


def normalize_field_value(field_def: FieldDef, raw_value: Any) -> Any:
    """Normalize a raw UI value into the wizard/importer shape."""
    if raw_value is None:
        return None

    if isinstance(raw_value, list):
        cleaned = [str(item).strip() for item in raw_value if str(item).strip()]
        return cleaned or None

    text = str(raw_value).strip()
    if not text:
        return None

    if field_def.field_type == FieldType.MULTILINE and field_def.key in _LIST_FIELD_KEYS:
        values = [line.strip() for line in text.splitlines() if line.strip()]
        return values or None

    if field_def.key in _MULTI_VALUE_KEYS:
        values = [
            part.strip()
            for part in text.replace("\n", ",").split(",")
            if part.strip()
        ]
        return values or None

    if field_def.key in {"scale", "realism"}:
        return text.lower()

    return text


def normalize_field_values(raw_values: dict[str, Any]) -> dict[str, Any]:
    """Normalize a full UI field map into authoring values."""
    normalized: dict[str, Any] = {}
    for field_def in FIELDS:
        value = normalize_field_value(field_def, raw_values.get(field_def.key))
        if value is not None:
            normalized[field_def.key] = value
    return normalized


def validate_field_values(values: dict[str, Any]) -> None:
    """Raise ValueError when required authoring fields are missing."""
    world_description = str(values.get("world_description") or "").strip()
    if not world_description:
        raise ValueError("World description is required.")
    if len(world_description) < 5:
        raise ValueError("World description must be at least 5 characters.")


def build_authoring_bundle(raw_values: dict[str, Any]) -> AuthoringBundle:
    """Build preview and final authoring prompt text from UI values."""
    values = normalize_field_values(raw_values)
    validate_field_values(values)
    realism = str(values.get("realism") or "medium")
    preview_prompt = assemble_prompt(values)
    authoring_prompt = build_zorkscript_prompt(
        preview_prompt,
        realism=realism,
        authoring_fields=values,
    )
    return AuthoringBundle(
        fields=values,
        preview_prompt=preview_prompt,
        authoring_prompt=authoring_prompt,
        realism=realism,
    )
