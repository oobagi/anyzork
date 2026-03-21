"""TUI-friendly import helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anyzork.config import Config
from anyzork.importer import compile_import_spec, default_output_path, load_import_source
from anyzork.zorkscript import parse_zorkscript


@dataclass(frozen=True)
class ImportBundle:
    """Result of importing ZorkScript into a compiled game file."""

    spec: dict[str, Any]
    output_path: Path
    warnings: list[str]


def import_zorkscript(
    source: str,
    *,
    output_path: Path | None = None,
    games_dir: Path | None = None,
) -> ImportBundle:
    """Import ZorkScript from raw text or a file path."""
    spec = _load_spec(source)
    target_games_dir = (games_dir or Config().games_dir).expanduser().resolve()
    resolved_output = (
        output_path.expanduser().resolve()
        if output_path is not None
        else default_output_path(spec, target_games_dir)
    )
    result_path, warnings = compile_import_spec(spec, resolved_output)
    return ImportBundle(spec=spec, output_path=result_path, warnings=warnings)


def import_zorkscript_source(
    spec_source: str,
    *,
    output_path: Path | None = None,
    cfg: Config | None = None,
) -> ImportBundle:
    """Import ZorkScript from a CLI-style source string."""
    spec = _load_spec(spec_source)
    return import_zorkscript_spec(spec, output_path=output_path, cfg=cfg)


def import_zorkscript_spec(
    spec: dict[str, Any],
    *,
    output_path: Path | None = None,
    cfg: Config | None = None,
) -> ImportBundle:
    """Compile a pre-parsed ZorkScript spec into a game file."""
    config = cfg or Config()
    resolved_output = (
        output_path.expanduser().resolve()
        if output_path is not None
        else default_output_path(spec, config.games_dir)
    )
    result_path, warnings = compile_import_spec(spec, resolved_output)
    return ImportBundle(spec=spec, output_path=result_path, warnings=warnings)


def _load_spec(source: str) -> dict[str, Any]:
    """Load a ZorkScript spec from either raw text or a path-like string."""
    if "\n" in source:
        return parse_zorkscript(source.strip())
    return load_import_source(source)
