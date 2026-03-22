"""Game project loader -- concatenates ZorkScript files with source mapping."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from anyzork.manifest import Manifest, load_manifest


@dataclass(frozen=True)
class SourceLocation:
    """Maps a line in concatenated text back to its source file."""

    filename: str
    line: int  # 1-based line number in the source file


@dataclass(frozen=True)
class ProjectSource:
    """Concatenated ZorkScript source with source mapping."""

    text: str
    manifest: Manifest
    _boundaries: list[tuple[str, int]]  # (filename, start_line_in_concat) - 1-based

    def map_line(self, concat_line: int) -> SourceLocation:
        """Map a concatenated line number back to a source file location."""
        for i in range(len(self._boundaries) - 1, -1, -1):
            filename, start = self._boundaries[i]
            if concat_line >= start:
                return SourceLocation(filename=filename, line=concat_line - start + 1)
        # Fallback (shouldn't happen)
        return SourceLocation(filename=self._boundaries[0][0], line=concat_line)


def load_project(project_dir: Path) -> ProjectSource:
    """Load and concatenate all ZorkScript files from a project directory."""
    manifest = load_manifest(project_dir)

    parts: list[str] = []
    boundaries: list[tuple[str, int]] = []
    current_line = 1

    for filename in manifest.source_files:
        file_path = project_dir / filename
        content = file_path.read_text(encoding="utf-8")
        boundaries.append((filename, current_line))
        parts.append(content)
        # Count lines in this file, then advance past the \n\n separator
        line_count = content.count("\n") + (0 if content.endswith("\n") else 1)
        separator_lines = 2 if content.endswith("\n") else 1
        current_line += line_count + separator_lines

    combined = "\n\n".join(parts)
    return ProjectSource(text=combined, manifest=manifest, _boundaries=boundaries)


def is_project_dir(path: Path) -> bool:
    """Check if a path is a game project directory (has manifest.toml)."""
    return path.is_dir() and (path / "manifest.toml").exists()
