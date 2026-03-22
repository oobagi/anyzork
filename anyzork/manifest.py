"""Game project manifest parser."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


class ManifestError(ValueError):
    """Raised when a manifest.toml is invalid."""


@dataclass(frozen=True)
class Manifest:
    """Parsed game project manifest."""

    title: str
    slug: str
    author: str
    description: str
    tags: list[str]
    source_files: list[str]  # ordered list of .zorkscript filenames

    @property
    def cover_art_path(self) -> str | None:
        return None  # future


def load_manifest(project_dir: Path) -> Manifest:
    """Load and validate manifest.toml from a project directory."""
    manifest_path = project_dir / "manifest.toml"
    if not manifest_path.exists():
        raise ManifestError(f"No manifest.toml found in {project_dir}")

    with open(manifest_path, "rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})
    source = data.get("source", {})

    title = project.get("title")
    if not title:
        raise ManifestError("manifest.toml: [project].title is required")

    source_files = source.get("files")
    if not source_files:
        raise ManifestError(
            "manifest.toml: [source].files is required and must list at least one .zorkscript file"
        )

    # Validate all source files exist
    for filename in source_files:
        file_path = project_dir / filename
        if not file_path.exists():
            raise ManifestError(f"manifest.toml: source file not found: {filename}")

    slug = project.get("slug") or _slugify(title)

    return Manifest(
        title=title,
        slug=slug,
        author=project.get("author", ""),
        description=project.get("description", ""),
        tags=project.get("tags", []),
        source_files=source_files,
    )


def _slugify(title: str) -> str:
    """Convert a title to a URL-safe slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")
