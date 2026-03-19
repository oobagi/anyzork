"""Preset loading and listing for the prompt builder wizard.

Presets are TOML files stored in anyzork/presets/ (built-in) and
~/.anyzork/presets/ (user-defined). User presets take precedence
on name collision.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table


def _builtin_presets_dir() -> Path:
    """Return the path to the built-in presets directory."""
    return Path(__file__).resolve().parent.parent / "presets"


def _user_presets_dir() -> Path:
    """Return the path to the user presets directory."""
    return Path.home() / ".anyzork" / "presets"


def _load_toml(path: Path) -> dict[str, Any]:
    """Load and parse a TOML file."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def _normalize_preset(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw preset TOML dict into wizard field values.

    Handles the [[fields.locations]] array-of-tables format by
    extracting the 'entry' values into flat lists.
    """
    fields = dict(data.get("fields", {}))

    # Convert array-of-tables entries to flat lists.
    for list_key in ("locations", "characters", "items"):
        raw = fields.get(list_key)
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            fields[list_key] = [item.get("entry", str(item)) for item in raw]

    # Strip whitespace from multiline string fields.
    for key in ("world_description", "story", "special_requests"):
        val = fields.get(key)
        if isinstance(val, str):
            fields[key] = val.strip()

    return fields


def discover_presets() -> dict[str, dict[str, Any]]:
    """Discover all available presets from both built-in and user directories.

    Returns:
        Dict mapping preset ID (filename without .toml) to the parsed
        preset dict containing 'name', 'description', and 'fields'.
        User presets override built-in presets on name collision.
    """
    presets: dict[str, dict[str, Any]] = {}

    for directory in [_builtin_presets_dir(), _user_presets_dir()]:
        if not directory.is_dir():
            continue
        for toml_path in sorted(directory.glob("*.toml")):
            preset_id = toml_path.stem
            try:
                data = _load_toml(toml_path)
                presets[preset_id] = {
                    "name": data.get("name", preset_id),
                    "description": data.get("description", ""),
                    "fields": _normalize_preset(data),
                    "source": str(directory),
                }
            except Exception:
                # Skip malformed presets silently.
                continue

    return presets


def load_preset(name: str) -> dict[str, Any] | None:
    """Load a specific preset by name.

    Args:
        name: The preset ID (filename without .toml extension).

    Returns:
        Dict of wizard field values, or None if not found.
    """
    presets = discover_presets()
    preset = presets.get(name)
    if preset is None:
        return None
    return preset["fields"]


def list_presets(console: Console) -> None:
    """Print a formatted table of available presets."""
    presets = discover_presets()

    if not presets:
        console.print("[yellow]No presets found.[/yellow]")
        return

    table = Table(
        title="Available Presets",
        show_header=True,
        header_style="bold",
        padding=(0, 2),
    )
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="bold")
    table.add_column("Description", style="dim")

    for preset_id, data in sorted(presets.items()):
        table.add_row(preset_id, data["name"], data["description"])

    console.print()
    console.print(table)
    console.print()
    console.print("[dim]Usage: anyzork generate --preset <id>[/dim]")
