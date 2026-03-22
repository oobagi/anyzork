"""Tests for anyzork.archive and related CLI commands."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from anyzork.archive import (
    is_zork_archive,
    load_project_from_archive,
    pack_project,
    unpack_archive,
)
from anyzork.cli import cli
from anyzork.manifest import load_manifest

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


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal project directory with manifest and source files."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir(exist_ok=True)

    source_files = ["game.zorkscript", "rooms.zorkscript", "commands.zorkscript"]
    files_toml = ", ".join(f'"{f}"' for f in source_files)
    manifest = f"""\
[project]
title = "CLI Import Game"
slug = "cli-import-game"
author = ""
description = ""
tags = []

[source]
files = [{files_toml}]
"""
    (project_dir / "manifest.toml").write_text(manifest, encoding="utf-8")

    file_contents = {
        "game.zorkscript": _GAME_ZORKSCRIPT,
        "rooms.zorkscript": _ROOMS_ZORKSCRIPT,
        "commands.zorkscript": _COMMANDS_ZORKSCRIPT,
    }
    for f in source_files:
        (project_dir / f).write_text(file_contents[f], encoding="utf-8")

    return project_dir


# ==========================================================================
# Archive library tests
# ==========================================================================


class TestPackCreatesArchive:
    def test_pack_creates_archive(self, tmp_path: Path) -> None:
        project_dir = _make_project(tmp_path)
        archive_path = pack_project(project_dir)
        assert archive_path.exists()
        assert archive_path.suffix == ".zork"
        assert archive_path.stat().st_size > 0


class TestUnpackExtractsArchive:
    def test_unpack_extracts(self, tmp_path: Path) -> None:
        project_dir = _make_project(tmp_path)
        archive_path = pack_project(project_dir)
        output_dir = tmp_path / "unpacked"
        extracted = unpack_archive(archive_path, output_dir)
        assert extracted.exists()
        assert (extracted / "manifest.toml").exists()
        manifest = load_manifest(extracted)
        assert manifest.title == "CLI Import Game"


class TestRoundtrip:
    def test_roundtrip(self, tmp_path: Path) -> None:
        project_dir = _make_project(tmp_path)
        archive_path = pack_project(project_dir)
        output_dir = tmp_path / "roundtrip"
        extracted = unpack_archive(archive_path, output_dir)
        manifest = load_manifest(extracted)
        assert manifest.title == "CLI Import Game"
        assert manifest.source_files == [
            "game.zorkscript",
            "rooms.zorkscript",
            "commands.zorkscript",
        ]
        # Verify source files round-tripped
        for f in manifest.source_files:
            original = (project_dir / f).read_text(encoding="utf-8")
            extracted_content = (extracted / f).read_text(encoding="utf-8")
            assert original == extracted_content


class TestIsZorkArchive:
    def test_valid_archive(self, tmp_path: Path) -> None:
        project_dir = _make_project(tmp_path)
        archive_path = pack_project(project_dir)
        assert is_zork_archive(archive_path) is True

    def test_not_archive(self, tmp_path: Path) -> None:
        f = tmp_path / "not_archive.txt"
        f.write_text("hello", encoding="utf-8")
        assert is_zork_archive(f) is False

    def test_nonexistent(self, tmp_path: Path) -> None:
        f = tmp_path / "does_not_exist.zork"
        assert is_zork_archive(f) is False


class TestLoadProjectFromArchive:
    def test_load_project_from_archive(self, tmp_path: Path) -> None:
        project_dir = _make_project(tmp_path)
        archive_path = pack_project(project_dir)
        project = load_project_from_archive(archive_path)
        assert "game {" in project.text
        assert "room foyer {" in project.text
        assert project.manifest.title == "CLI Import Game"


# ==========================================================================
# CLI tests
# ==========================================================================



class TestCliImportArchive:
    def test_import_archive(self, tmp_path: Path) -> None:
        project_dir = _make_project(tmp_path)
        archive_path = pack_project(project_dir)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["import", str(archive_path), "-o", str(tmp_path / "from_archive.zork")]
        )
        assert result.exit_code == 0
        assert "Done" in result.output



class TestCliDoctorArchive:
    def test_doctor_archive(self, tmp_path: Path) -> None:
        project_dir = _make_project(tmp_path)
        archive_path = pack_project(project_dir)
        runner = CliRunner()
        result = runner.invoke(cli, ["doctor", str(archive_path)])
        assert result.exit_code == 0
        assert "should import cleanly" in result.output
