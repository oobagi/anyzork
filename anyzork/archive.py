"""Pack and unpack .zork zip archives."""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from anyzork.manifest import ManifestError, load_manifest

if TYPE_CHECKING:
    from anyzork.project import ProjectSource

ZORK_ARCHIVE_SUFFIX = ".zork"


def pack_project(project_dir: Path, output_path: Path | None = None) -> Path:
    """Pack a project directory into a .zork zip archive.

    Returns the path to the created archive.
    """
    manifest = load_manifest(project_dir)

    if output_path is None:
        output_path = project_dir.parent / f"{manifest.slug}{ZORK_ARCHIVE_SUFFIX}"

    output_path = output_path.expanduser().resolve()

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Write manifest
        zf.write(project_dir / "manifest.toml", "manifest.toml")
        # Write source files
        for filename in manifest.source_files:
            zf.write(project_dir / filename, filename)

    return output_path


def unpack_archive(archive_path: Path, output_dir: Path | None = None) -> Path:
    """Extract a .zork archive to a project directory.

    Returns the path to the extracted directory.
    """
    archive_path = archive_path.expanduser().resolve()

    if not zipfile.is_zipfile(archive_path):
        raise ManifestError(f"Not a valid .zork archive: {archive_path}")

    if output_dir is None:
        output_dir = archive_path.parent / archive_path.stem

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "r") as zf:
        zf.extractall(output_dir)

    # Validate the extracted project
    load_manifest(output_dir)

    return output_dir


def is_zork_archive(path: Path) -> bool:
    """Check if a file is a .zork zip archive."""
    if not path.is_file():
        return False
    return zipfile.is_zipfile(path)


def load_project_from_archive(archive_path: Path) -> ProjectSource:
    """Load a project directly from a .zork archive without extracting to disk.

    Uses a temp directory internally, cleaned up after loading.
    """
    from anyzork.project import load_project

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(tmp_path)
        return load_project(tmp_path)
