"""Type coercion and slugify helpers for the import-spec compiler."""

from __future__ import annotations

import json
import re
from typing import Any


def slugify_title(title: str) -> str:
    """Return a filesystem-friendly slug for imported game titles."""
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return slug or "game"


def json_value(value: Any) -> str:
    return json.dumps(value if value is not None else [])


def json_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def bool_to_int(value: Any) -> int:
    return 1 if bool(value) else 0


def flag_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip().lower()
    return "true" if text in {"1", "true", "yes"} else "false"
