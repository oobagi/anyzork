"""Tests for anyzork.manifest, anyzork.project, and related CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from anyzork.cli import cli
from anyzork.manifest import ManifestError, _slugify, load_manifest
from anyzork.project import is_project_dir, load_project

# -- Shared ZorkScript fragments for multi-file projects ---------------------

_GAME_ZORKSCRIPT = """\
game {
  title "CLI Import Game"
  author "Imported through the CLI."
  max_score 0
  win [game_won]
}

player {
  start foyer
}

flag game_won "Tracks victory."
"""

_ROOMS_ZORKSCRIPT = """\
room foyer {
  name "Foyer"
  description "A quiet foyer."
  short "A quiet foyer."

  start true

  exit north -> study
}

room study {
  name "Study"
  description "A cramped study."
  short "A cramped study."


  exit south -> foyer
}
"""

_COMMANDS_ZORKSCRIPT = """\
on "win game" in [foyer, study] {
  effect set_flag(game_won)
  success "You win."
}
"""


def _make_project(
    tmp_path: Path,
    *,
    title: str = "CLI Import Game",
    slug: str | None = None,
    author: str = "",
    source_files: list[str] | None = None,
    extra_manifest: str = "",
) -> Path:
    """Create a project directory with a manifest and source files."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir(exist_ok=True)

    if source_files is None:
        source_files = ["game.zorkscript", "rooms.zorkscript", "commands.zorkscript"]

    slug_str = slug or _slugify(title)
    files_toml = ", ".join(f'"{f}"' for f in source_files)
    manifest = f"""\
[project]
title = "{title}"
slug = "{slug_str}"
author = "{author}"
description = ""
tags = []

[source]
files = [{files_toml}]
{extra_manifest}
"""
    (project_dir / "manifest.toml").write_text(manifest, encoding="utf-8")

    # Write source files
    file_contents = {
        "game.zorkscript": _GAME_ZORKSCRIPT,
        "rooms.zorkscript": _ROOMS_ZORKSCRIPT,
        "commands.zorkscript": _COMMANDS_ZORKSCRIPT,
    }
    for f in source_files:
        content = file_contents.get(f, "")
        (project_dir / f).write_text(content, encoding="utf-8")

    return project_dir


# ==========================================================================
# Manifest tests
# ==========================================================================


class TestManifestValid:
    def test_load_valid_manifest(self, tmp_path: Path) -> None:
        project_dir = _make_project(tmp_path)
        manifest = load_manifest(project_dir)
        assert manifest.title == "CLI Import Game"
        assert manifest.slug == "cli-import-game"
        assert manifest.source_files == [
            "game.zorkscript",
            "rooms.zorkscript",
            "commands.zorkscript",
        ]


class TestManifestMissingTitle:
    def test_missing_title(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "no_title"
        project_dir.mkdir()
        (project_dir / "manifest.toml").write_text(
            '[project]\n[source]\nfiles = ["game.zorkscript"]\n',
            encoding="utf-8",
        )
        (project_dir / "game.zorkscript").write_text("", encoding="utf-8")
        with pytest.raises(ManifestError, match="title is required"):
            load_manifest(project_dir)


class TestManifestMissingFiles:
    def test_missing_files(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "no_files"
        project_dir.mkdir()
        (project_dir / "manifest.toml").write_text(
            '[project]\ntitle = "Test"\n[source]\n',
            encoding="utf-8",
        )
        with pytest.raises(ManifestError, match="files is required"):
            load_manifest(project_dir)


class TestManifestMissingSourceFile:
    def test_missing_source_file(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "missing_src"
        project_dir.mkdir()
        (project_dir / "manifest.toml").write_text(
            '[project]\ntitle = "Test"\n[source]\nfiles = ["missing.zorkscript"]\n',
            encoding="utf-8",
        )
        with pytest.raises(ManifestError, match="source file not found"):
            load_manifest(project_dir)


class TestManifestAutoSlug:
    def test_auto_slug(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "auto_slug"
        project_dir.mkdir()
        (project_dir / "manifest.toml").write_text(
            '[project]\ntitle = "My Great Game!"\n[source]\nfiles = ["g.zorkscript"]\n',
            encoding="utf-8",
        )
        (project_dir / "g.zorkscript").write_text("", encoding="utf-8")
        manifest = load_manifest(project_dir)
        assert manifest.slug == "my-great-game"


class TestManifestNoManifest:
    def test_no_manifest(self, tmp_path: Path) -> None:
        with pytest.raises(ManifestError, match=r"No manifest\.toml"):
            load_manifest(tmp_path)


# ==========================================================================
# Project loading tests
# ==========================================================================


class TestProjectConcatenation:
    def test_concatenation_order(self, tmp_path: Path) -> None:
        project_dir = _make_project(tmp_path)
        project = load_project(project_dir)
        # All three files should appear in the concatenated text
        assert "game {" in project.text
        assert "room foyer {" in project.text
        assert 'on "win game"' in project.text
        # game.zorkscript content should appear before rooms.zorkscript
        game_pos = project.text.index("game {")
        rooms_pos = project.text.index("room foyer {")
        commands_pos = project.text.index('on "win game"')
        assert game_pos < rooms_pos < commands_pos


class TestProjectSourceMapLineMapping:
    def test_source_map_line_mapping(self, tmp_path: Path) -> None:
        project_dir = _make_project(tmp_path)
        project = load_project(project_dir)
        # Line 1 should map to the first file
        loc = project.map_line(1)
        assert loc.filename == "game.zorkscript"
        assert loc.line == 1


class TestIsProjectDir:
    def test_is_project_dir(self, tmp_path: Path) -> None:
        project_dir = _make_project(tmp_path)
        assert is_project_dir(project_dir) is True

    def test_not_project_dir(self, tmp_path: Path) -> None:
        assert is_project_dir(tmp_path) is False

    def test_file_not_project_dir(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hello", encoding="utf-8")
        assert is_project_dir(f) is False


# ==========================================================================
# Slugify tests
# ==========================================================================


class TestSlugify:
    def test_basic(self) -> None:
        assert _slugify("Hello World") == "hello-world"

    def test_special_chars(self) -> None:
        assert _slugify("My Game!!! v2.0") == "my-game-v2-0"

    def test_leading_trailing(self) -> None:
        assert _slugify("  --hello--  ") == "hello"


# ==========================================================================
# CLI tests
# ==========================================================================



class TestCliImportProject:
    def test_import_project_dir(self, tmp_path: Path) -> None:
        project_dir = _make_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["import", str(project_dir), "-o", str(tmp_path / "out.zork")]
        )
        assert result.exit_code == 0
        assert "Done" in result.output



class TestCliDoctorProject:
    def test_doctor_project_dir(self, tmp_path: Path) -> None:
        project_dir = _make_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["doctor", str(project_dir)])
        assert result.exit_code == 0
        assert "should import cleanly" in result.output
