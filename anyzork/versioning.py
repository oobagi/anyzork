"""Central version metadata for AnyZork."""

from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

_RUNTIME_COMPAT_RE = re.compile(r"^r\d+(?:\.\d+)*$")


def _detect_app_version() -> str:
    """Return the installed package version, with a dev fallback."""
    try:
        return package_version("anyzork")
    except PackageNotFoundError:
        return "0.0.0+dev"


APP_VERSION = _detect_app_version()
RUNTIME_COMPAT_VERSION = "r1"


def is_runtime_compat_version(value: str | None) -> bool:
    """Return True when *value* looks like a runtime compatibility version."""
    return bool(value and _RUNTIME_COMPAT_RE.fullmatch(value))
