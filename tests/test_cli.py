from __future__ import annotations

import json
import zipfile
from pathlib import Path

from click.testing import CliRunner

from anyzork import cli as cli_module
from anyzork.cli import cli
from anyzork.importer import compile_import_spec
from anyzork.services import library as library_service
from anyzork.sharing import PUBLIC_CATALOG_FORMAT, create_share_package


def test_generate_outputs_prompt_for_freeform_concept() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["generate", "A haunted lighthouse on a foggy coast"])

    assert result.exit_code == 0, result.output
    assert "A haunted lighthouse on a foggy coast" in result.output
    assert "You are authoring a complete, playable text adventure in ZorkScript" in result.output


def test_import_reads_zorkscript_from_stdin(tmp_path: Path, minimal_zorkscript: str) -> None:
    runner = CliRunner()
    output_path = tmp_path / "cli_imported.zork"

    result = runner.invoke(
        cli,
        ["import", "-o", str(output_path)],
        input=minimal_zorkscript,
    )

    assert result.exit_code == 0, result.output
    assert output_path.exists()
    assert "Imported game saved to" in result.output

def test_play_creates_and_restarts_managed_save_slot(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    library_dir.mkdir()
    target_game = library_dir / "fixture_game.zork"
    target_game.write_bytes(compiled_game_path.read_bytes())
    started_paths: list[Path] = []

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir

    def fake_start(self) -> None:
        started_paths.append(self.db.path)

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr("anyzork.engine.game.GameEngine.start", fake_start)

    first = runner.invoke(cli, ["play", "fixture_game", "--slot", "alpha"])
    assert first.exit_code == 0, first.output
    assert len(started_paths) == 1
    save_path = started_paths[-1]
    assert save_path.exists()
    assert save_path.parent.name

    second = runner.invoke(cli, ["play", "fixture_game", "--slot", "alpha", "--new"])
    assert second.exit_code == 0, second.output
    assert len(started_paths) == 2
    assert started_paths[-1] == save_path


def test_play_without_game_ref_shows_games_even_when_saves_exist(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    library_dir.mkdir()
    target_game = library_dir / "fixture_game.zork"
    target_game.write_bytes(compiled_game_path.read_bytes())
    started_paths: list[Path] = []

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir

    library_service.prepare_managed_save(
        target_game,
        "alpha",
        False,
        FakeConfig(),
    )

    def fake_start(self) -> None:
        started_paths.append(self.db.path)

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr("anyzork.engine.game.GameEngine.start", fake_start)

    result = runner.invoke(cli, ["play"], input="1\n")

    assert result.exit_code == 0, result.output
    assert "Choose A Game" in result.output
    assert "fixture_game" in result.output
    assert "alpha" not in result.output
    assert "Latest Run" not in result.output
    assert len(started_paths) == 1
    assert started_paths[0].name == "default.zork"


def test_play_without_game_ref_can_select_library_game(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    library_dir.mkdir()
    target_game = library_dir / "fixture_game.zork"
    target_game.write_bytes(compiled_game_path.read_bytes())
    started_paths: list[Path] = []

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir

    def fake_start(self) -> None:
        started_paths.append(self.db.path)

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr("anyzork.engine.game.GameEngine.start", fake_start)

    result = runner.invoke(cli, ["play"], input="1\n")

    assert result.exit_code == 0, result.output
    assert "Choose A Game" in result.output
    assert "Title" in result.output
    assert "Active Saves" in result.output
    assert "fixture_game" in result.output
    assert len(started_paths) == 1
    assert started_paths[0].name == "default.zork"
    assert started_paths[0].exists()


def test_list_shows_library_table_with_active_save_count_only(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    from anyzork.db.schema import GameDB

    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    library_dir.mkdir()
    target_game = library_dir / "fixture_game.zork"
    target_game.write_bytes(compiled_game_path.read_bytes())

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir

    _alpha_path, _ = library_service.prepare_managed_save(target_game, "alpha", False, FakeConfig())
    beta_path, _ = library_service.prepare_managed_save(target_game, "beta", False, FakeConfig())
    with GameDB(beta_path) as db:
        db.update_player(game_state="won")

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(cli, ["list"])

    assert result.exit_code == 0, result.output
    assert "Game Library" in result.output
    assert "Active Saves" in result.output
    assert "Managed Saves" not in result.output
    assert "Fixture Game" in result.output
    assert "beta (won)" in result.output


def test_saves_lists_all_saves_and_can_filter_by_game(
    monkeypatch,
    tmp_path: Path,
    compiled_game_path: Path,
    minimal_import_spec: dict,
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    library_dir.mkdir()
    target_game = library_dir / "fixture_game.zork"
    target_game.write_bytes(compiled_game_path.read_bytes())

    second_spec = {
        **minimal_import_spec,
        "game": {
            **minimal_import_spec["game"],
            "title": "Second Fixture",
            "author_prompt": "Another compact fixture world.",
        },
    }
    second_game = library_dir / "second_fixture.zork"
    compile_import_spec(second_spec, second_game)

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir

    library_service.prepare_managed_save(target_game, "alpha", False, FakeConfig())
    library_service.prepare_managed_save(second_game, "omega", False, FakeConfig())

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    all_saves = runner.invoke(cli, ["saves"])
    assert all_saves.exit_code == 0, all_saves.output
    assert "Managed Saves" in all_saves.output
    assert "Ref" in all_saves.output
    assert "Title" in all_saves.output
    assert "fixture_game" in all_saves.output
    assert "second_fixture" in all_saves.output
    assert "alpha" in all_saves.output
    assert "omega" in all_saves.output

    fixture_only = runner.invoke(cli, ["saves", "fixture_game"])
    assert fixture_only.exit_code == 0, fixture_only.output
    assert "Managed Saves for Fixture Game" in fixture_only.output
    assert "Ref" in fixture_only.output
    assert "Title" in fixture_only.output
    assert "fixture_game" in fixture_only.output
    assert "alpha" in fixture_only.output
    assert "second_fixture" not in fixture_only.output
    assert "omega" not in fixture_only.output


def test_publish_creates_share_package(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    library_dir.mkdir()
    target_game = library_dir / "fixture_game.zork"
    target_game.write_bytes(compiled_game_path.read_bytes())
    package_path = tmp_path / "fixture_game.anyzorkpkg"

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(cli, ["publish", "fixture_game", "-o", str(package_path)])

    assert result.exit_code == 0, result.output
    assert package_path.exists()

    with zipfile.ZipFile(package_path) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        payload_names = archive.namelist()

    assert manifest["format"] == "anyzork-share-package/v1"
    assert manifest["game"]["title"] == "Fixture Game"
    assert manifest["listing"]["title"] == "Fixture Game"
    assert "game.zork" in payload_names


def test_publish_accepts_public_listing_metadata(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    library_dir.mkdir()
    target_game = library_dir / "fixture_game.zork"
    target_game.write_bytes(compiled_game_path.read_bytes())
    package_path = tmp_path / "fixture_game.anyzorkpkg"

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(
        cli,
        [
            "publish",
            "fixture_game",
            "-o",
            str(package_path),
            "--slug",
            "fixture-game",
            "--author",
            "AnyZork",
            "--description",
            "Uploaded from the CLI.",
            "--tagline",
            "A tiny mystery.",
            "--genre",
            "mystery",
            "--genre",
            "short",
        ],
    )

    assert result.exit_code == 0, result.output

    with zipfile.ZipFile(package_path) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    assert manifest["listing"]["author"] == "AnyZork"
    assert manifest["listing"]["slug"] == "fixture-game"
    assert manifest["listing"]["description"] == "Uploaded from the CLI."
    assert manifest["listing"]["tagline"] == "A tiny mystery."
    assert manifest["listing"]["genres"] == ["mystery", "short"]


def test_publish_guided_prompts_for_listing_metadata(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    library_dir.mkdir()
    target_game = library_dir / "fixture_game.zork"
    target_game.write_bytes(compiled_game_path.read_bytes())
    package_path = tmp_path / "fixture_game.anyzorkpkg"

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(
        cli,
        ["publish", "fixture_game", "--guided", "-o", str(package_path)],
        input=(
            "\n"
            "Jaden\n"
            "A foggy lighthouse mystery.\n"
            "A tiny mystery.\n"
            "mystery, short\n"
            "fixture-game\n"
            "https://example.com/game\n"
            "https://example.com/cover.png\n"
        ),
    )

    assert result.exit_code == 0, result.output
    assert "Publish Listing" in result.output

    with zipfile.ZipFile(package_path) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    assert manifest["listing"]["title"] == "Fixture Game"
    assert manifest["listing"]["author"] == "Jaden"
    assert manifest["listing"]["description"] == "A foggy lighthouse mystery."
    assert manifest["listing"]["tagline"] == "A tiny mystery."
    assert manifest["listing"]["genres"] == ["mystery", "short"]
    assert manifest["listing"]["slug"] == "fixture-game"
    assert manifest["listing"]["homepage_url"] == "https://example.com/game"
    assert manifest["listing"]["cover_image_url"] == "https://example.com/cover.png"


def test_install_adds_shared_package_to_library(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    package_path = tmp_path / "fixture_game.anyzorkpkg"
    create_share_package(compiled_game_path, package_path)

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(cli, ["install", str(package_path)])

    assert result.exit_code == 0, result.output
    installed_path = library_dir / "fixture_game.zork"
    assert installed_path.exists()
    metadata = cli_module._read_zork_metadata(installed_path)
    assert metadata is not None
    assert metadata["title"] == "Fixture Game"


def test_install_uses_catalog_ref_and_relative_package_path(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    share_dir = tmp_path / "published"
    share_dir.mkdir()
    package_path = share_dir / "fixture_game.anyzorkpkg"
    create_share_package(compiled_game_path, package_path)

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr(
        "anyzork.sharing.resolve_catalog_game_source",
        lambda catalog_url, ref: (
            str(package_path),
            {
                "slug": ref,
                "title": "Fixture Game",
                "package_url": "published/fixture_game.anyzorkpkg",
            },
        ),
    )

    result = runner.invoke(cli, ["install", "fixture_game"])

    assert result.exit_code == 0, result.output
    installed_path = library_dir / "fixture_game.zork"
    assert installed_path.exists()


def test_install_rejects_local_raw_zork_files(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    local_game = tmp_path / "fixture_game.zork"
    local_game.write_bytes(compiled_game_path.read_bytes())

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(cli, ["install", str(local_game)])

    assert result.exit_code != 0
    assert "official catalog ref or a local .anyzorkpkg package" in result.output


def test_install_rejects_remote_urls(
    monkeypatch, tmp_path: Path
) -> None:
    runner = CliRunner()

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = tmp_path / "library"
            self.saves_dir = tmp_path / "saves"

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(cli, ["install", "https://example.com/fixture_game.anyzorkpkg"])

    assert result.exit_code != 0
    assert "official catalog ref or a local .anyzorkpkg package" in result.output


def test_browse_lists_games_from_catalog(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        "anyzork.sharing.load_public_catalog",
        lambda catalog_url: {
            "format": PUBLIC_CATALOG_FORMAT,
            "title": "Featured AnyZork Games",
            "updated_at": "2026-03-20T12:00:00Z",
            "games": [
                {
                    "slug": "fixture_game",
                    "title": "Fixture Game",
                    "author": "AnyZork",
                    "tagline": "A tiny deterministic mystery.",
                    "genres": ["mystery", "short"],
                    "featured": True,
                    "package_url": "https://example.com/fixture_game.anyzorkpkg",
                    "runtime_compat_version": "r1",
                    "room_count": 2,
                }
            ],
        },
    )

    result = runner.invoke(cli, ["browse"])

    assert result.exit_code == 0, result.output
    assert "Featured AnyZork Games" in result.output
    assert "fixture_game" in result.output
    assert "Updated:" in result.output
    assert "anyzork install <ref>" in result.output


def test_browse_reports_invalid_catalog_counts(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        "anyzork.sharing.load_public_catalog",
        lambda catalog_url: (_ for _ in ()).throw(
            cli_module.SharePackageError("invalid room_count for game 'broken_game': two")
        ),
    )

    result = runner.invoke(cli, ["browse"])

    assert result.exit_code == 1, result.output
    assert "invalid room_count" in result.output


def test_upload_sends_package_to_catalog_service(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    runner = CliRunner()
    package_path = tmp_path / "fixture_game.anyzorkpkg"
    create_share_package(compiled_game_path, package_path)
    uploaded: dict[str, object] = {}

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = tmp_path / "library"
            self.saves_dir = tmp_path / "saves"

    def fake_upload_share_package(
        package_path: Path,
        upload_url: str,
        **metadata: object,
    ) -> dict[str, object]:
        uploaded["package_path"] = str(package_path)
        uploaded["upload_url"] = upload_url
        uploaded["metadata"] = metadata
        return {"game": {"slug": "fixture_game", "title": "Fixture Game"}}

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr("anyzork.sharing.upload_share_package", fake_upload_share_package)

    result = runner.invoke(
        cli,
        [
            "upload",
            str(package_path),
            "--author",
            "AnyZork",
            "--genre",
            "mystery",
            "--genre",
            "short",
        ],
    )

    assert result.exit_code == 0, result.output
    assert uploaded["package_path"] == str(package_path.resolve())
    assert uploaded["upload_url"] == "https://anyzork.com/api/games"
    assert uploaded["metadata"] == {
        "title": None,
        "author": "AnyZork",
        "description": None,
        "tagline": None,
        "genres": ["mystery", "short"],
        "slug": None,
        "homepage_url": None,
        "cover_image_url": None,
    }
    assert "Uploaded" in result.output


def test_upload_uses_existing_package_without_repackaging(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    runner = CliRunner()
    package_path = tmp_path / "fixture_game.anyzorkpkg"
    create_share_package(
        compiled_game_path,
        package_path,
        author="AnyZork",
        description="Uploaded from a package.",
        genres=["mystery"],
    )
    uploaded: dict[str, object] = {}

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = tmp_path / "library"
            self.saves_dir = tmp_path / "saves"

    def fake_upload_share_package(
        selected_package_path: Path,
        upload_url: str,
        **metadata: object,
    ) -> dict[str, object]:
        uploaded["package_path"] = str(selected_package_path)
        uploaded["upload_url"] = upload_url
        uploaded["metadata"] = metadata
        return {"game": {"slug": "fixture_game", "title": "Fixture Game"}}

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr("anyzork.sharing.upload_share_package", fake_upload_share_package)

    result = runner.invoke(cli, ["upload", str(package_path)])

    assert result.exit_code == 0, result.output
    assert uploaded["package_path"] == str(package_path.resolve())
    assert uploaded["upload_url"] == "https://anyzork.com/api/games"
    assert uploaded["metadata"]["author"] is None


def test_upload_rejects_non_package_sources(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    target_game = library_dir / "fixture_game.zork"
    target_game.write_bytes(compiled_game_path.read_bytes())

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = tmp_path / "saves"

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(cli, ["upload", "fixture_game"])

    assert result.exit_code != 0
    assert "Upload expects a .anyzorkpkg package" in result.output
