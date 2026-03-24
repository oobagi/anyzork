from __future__ import annotations

import json
import zipfile
from pathlib import Path

from click.testing import CliRunner

from anyzork import cli as cli_module
from anyzork.cli import cli
from anyzork.config import DEFAULT_CATALOG_URL, DEFAULT_UPLOAD_URL
from anyzork.importer import compile_import_spec
from anyzork.services import library as library_service
from anyzork.sharing import PUBLIC_CATALOG_FORMAT, create_share_package


def test_generate_outputs_prompt_for_freeform_concept(tmp_path: Path) -> None:
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            ["generate", "A haunted lighthouse on a foggy coast", "-o", "prompts.txt"],
        )

        assert result.exit_code == 0, result.output
        content = Path("prompts.txt").read_text()
        assert "A haunted lighthouse on a foggy coast" in content
        assert (
            "You are authoring a complete, playable text adventure"
            " in ZorkScript format" in content
        )


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
            self.catalog_url = DEFAULT_CATALOG_URL
            self.upload_url = DEFAULT_UPLOAD_URL
            self.session_token = None
            self.publisher_email = None

    def fake_start(self) -> None:
        started_paths.append(self.db.path)

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr("anyzork.engine.game.GameEngine.start", fake_start)

    first = runner.invoke(cli, ["play", "fixture_game", "--save", "alpha"])
    assert first.exit_code == 0, first.output
    assert len(started_paths) == 1
    save_path = started_paths[-1]
    assert save_path.exists()
    assert save_path.parent.name

    second = runner.invoke(cli, ["play", "fixture_game", "--save", "alpha", "--new"])
    assert second.exit_code == 0, second.output
    assert len(started_paths) == 2
    assert started_paths[-1] == save_path


def test_playing_a_zork_file_path_creates_a_managed_save(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    runner = CliRunner()
    saves_dir = tmp_path / "saves"
    source_game = tmp_path / "local_game.zork"
    source_game.write_bytes(compiled_game_path.read_bytes())
    started_paths: list[Path] = []

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = tmp_path / "library"
            self.saves_dir = saves_dir
            self.catalog_url = DEFAULT_CATALOG_URL
            self.upload_url = DEFAULT_UPLOAD_URL
            self.session_token = None
            self.publisher_email = None

    def fake_start(self) -> None:
        started_paths.append(self.db.path)

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr("anyzork.engine.game.GameEngine.start", fake_start)

    result = runner.invoke(cli, ["play", str(source_game)])

    assert result.exit_code == 0, result.output
    assert len(started_paths) == 1
    assert started_paths[0] != source_game
    assert started_paths[0].exists()
    assert saves_dir in started_paths[0].parents


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
            self.catalog_url = DEFAULT_CATALOG_URL
            self.upload_url = DEFAULT_UPLOAD_URL
            self.session_token = None
            self.publisher_email = None

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
            self.catalog_url = DEFAULT_CATALOG_URL
            self.upload_url = DEFAULT_UPLOAD_URL
            self.session_token = None
            self.publisher_email = None

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
            self.catalog_url = DEFAULT_CATALOG_URL
            self.upload_url = DEFAULT_UPLOAD_URL
            self.session_token = None
            self.publisher_email = None

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


def test_list_saves_flag_shows_saves_table(
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
            self.catalog_url = DEFAULT_CATALOG_URL
            self.upload_url = DEFAULT_UPLOAD_URL
            self.session_token = None
            self.publisher_email = None

    library_service.prepare_managed_save(target_game, "alpha", False, FakeConfig())
    library_service.prepare_managed_save(second_game, "omega", False, FakeConfig())

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    all_saves = runner.invoke(cli, ["list", "--saves"])
    assert all_saves.exit_code == 0, all_saves.output
    assert "Game Library" not in all_saves.output
    assert "Managed Saves" in all_saves.output
    assert "fixture_game" in all_saves.output
    assert "second_fixture" in all_saves.output
    assert "alpha" in all_saves.output
    assert "omega" in all_saves.output

    # Without --saves flag, only the library table is shown
    no_saves = runner.invoke(cli, ["list"])
    assert no_saves.exit_code == 0, no_saves.output
    assert "Game Library" in no_saves.output
    assert "Managed Saves" not in no_saves.output


def test_publish_creates_share_package(
    monkeypatch, tmp_path: Path, zork_archive_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    library_dir.mkdir()
    target_game = library_dir / "fixture_game.zork"
    target_game.write_bytes(zork_archive_path.read_bytes())
    uploaded: dict[str, object] = {}

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir
            self.catalog_url = DEFAULT_CATALOG_URL
            self.upload_url = DEFAULT_UPLOAD_URL
            self.session_token = None
            self.publisher_email = None

    def fake_upload_share_package(
        package_path: Path,
        upload_url: str,
        **metadata: object,
    ) -> dict[str, object]:
        uploaded["package_path"] = str(package_path)
        with zipfile.ZipFile(package_path) as archive:
            uploaded["manifest"] = json.loads(archive.read("manifest.json").decode("utf-8"))
            uploaded["payload_names"] = archive.namelist()
        return {"game": {"slug": "fixture_game", "title": "Fixture Game"}}

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr("anyzork.sharing.upload_share_package", fake_upload_share_package)

    # Wizard prompts: title, author, description, tagline, genres, slug,
    # homepage url, cover image url, then "Ready to publish?" confirm.
    # Press enter to accept all defaults.
    result = runner.invoke(
        cli,
        ["publish", "fixture_game"],
        input="\n\n\n\n\n\n\n\ny\n",
    )

    assert result.exit_code == 0, result.output
    assert "Published!" in result.output

    manifest = uploaded["manifest"]
    assert manifest["format"] == "anyzork-share-package/v1"
    assert manifest["game"]["title"] == "Fixture Game"
    assert manifest["listing"]["title"] == "Fixture Game"
    assert "manifest.toml" in uploaded["payload_names"]


def test_publish_accepts_public_listing_metadata(
    monkeypatch, tmp_path: Path, zork_archive_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    library_dir.mkdir()
    target_game = library_dir / "fixture_game.zork"
    target_game.write_bytes(zork_archive_path.read_bytes())
    uploaded: dict[str, object] = {}

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir
            self.catalog_url = DEFAULT_CATALOG_URL
            self.upload_url = DEFAULT_UPLOAD_URL
            self.session_token = None
            self.publisher_email = None

    def fake_upload_share_package(
        package_path: Path,
        upload_url: str,
        **metadata: object,
    ) -> dict[str, object]:
        with zipfile.ZipFile(package_path) as archive:
            uploaded["manifest"] = json.loads(archive.read("manifest.json").decode("utf-8"))
        return {"game": {"slug": "fixture-game", "title": "Fixture Game"}}

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr("anyzork.sharing.upload_share_package", fake_upload_share_package)

    # Wizard prompts: title, author, description, tagline, genres, slug,
    # homepage url, cover image url, then "Ready to publish?" confirm.
    result = runner.invoke(
        cli,
        ["publish", "fixture_game"],
        input=(
            "\n"                         # title — accept default
            "AnyZork\n"                  # author
            "Uploaded from the CLI.\n"   # description
            "A tiny mystery.\n"          # tagline
            "mystery, short\n"           # genres
            "fixture-game\n"             # slug
            "\n"                         # homepage url — skip
            "\n"                         # cover image url — skip
            "y\n"                        # confirm
        ),
    )

    assert result.exit_code == 0, result.output

    manifest = uploaded["manifest"]
    assert manifest["listing"]["author"] == "AnyZork"
    assert manifest["listing"]["slug"] == "fixture-game"
    assert manifest["listing"]["description"] == "Uploaded from the CLI."
    assert manifest["listing"]["tagline"] == "A tiny mystery."
    assert manifest["listing"]["genres"] == ["mystery", "short"]


def test_publish_wizard_prompts_for_listing_metadata(
    monkeypatch, tmp_path: Path, zork_archive_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    library_dir.mkdir()
    target_game = library_dir / "fixture_game.zork"
    target_game.write_bytes(zork_archive_path.read_bytes())
    uploaded: dict[str, object] = {}

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir
            self.catalog_url = DEFAULT_CATALOG_URL
            self.upload_url = DEFAULT_UPLOAD_URL
            self.session_token = None
            self.publisher_email = None

    def fake_upload_share_package(
        package_path: Path,
        upload_url: str,
        **metadata: object,
    ) -> dict[str, object]:
        with zipfile.ZipFile(package_path) as archive:
            uploaded["manifest"] = json.loads(archive.read("manifest.json").decode("utf-8"))
        return {"game": {"slug": "fixture-game", "title": "Fixture Game"}}

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr("anyzork.sharing.upload_share_package", fake_upload_share_package)

    # Wizard prompts: title, author, description, tagline, genres, slug,
    # then "Ready to publish?" confirm.
    result = runner.invoke(
        cli,
        ["publish", "fixture_game"],
        input=(
            "\n"                             # title — accept default "Fixture Game"
            "Jaden\n"                        # author
            "A foggy lighthouse mystery.\n"  # description
            "A tiny mystery.\n"              # tagline
            "mystery, short\n"               # genres
            "fixture-game\n"                 # slug
            "y\n"                            # confirm
        ),
    )

    assert result.exit_code == 0, result.output
    assert "Publish Listing" in result.output

    manifest = uploaded["manifest"]
    assert manifest["listing"]["title"] == "Fixture Game"
    assert manifest["listing"]["author"] == "Jaden"
    assert manifest["listing"]["description"] == "A foggy lighthouse mystery."
    assert manifest["listing"]["tagline"] == "A tiny mystery."
    assert manifest["listing"]["genres"] == ["mystery", "short"]
    assert manifest["listing"]["slug"] == "fixture-game"


def test_install_adds_shared_package_to_library(
    monkeypatch, tmp_path: Path, zork_archive_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    package_path = tmp_path / "shared_fixture_game.zork"
    create_share_package(zork_archive_path, package_path)

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir
            self.catalog_url = DEFAULT_CATALOG_URL
            self.upload_url = DEFAULT_UPLOAD_URL
            self.session_token = None
            self.publisher_email = None

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(cli, ["install", str(package_path)])

    assert result.exit_code == 0, result.output
    installed_path = library_dir / "fixture_game.zork"
    assert installed_path.exists()
    # Verify the installed archive contains manifest.toml
    import zipfile as zf
    assert zf.is_zipfile(installed_path)
    with zf.ZipFile(installed_path) as archive:
        assert "manifest.toml" in archive.namelist()


def test_install_uses_catalog_ref_and_relative_package_path(
    monkeypatch, tmp_path: Path, zork_archive_path: Path
) -> None:
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    share_dir = tmp_path / "published"
    share_dir.mkdir()
    package_path = share_dir / "fixture_game.zork"
    create_share_package(zork_archive_path, package_path)

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir
            self.catalog_url = DEFAULT_CATALOG_URL
            self.upload_url = DEFAULT_UPLOAD_URL
            self.session_token = None
            self.publisher_email = None

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr(
        "anyzork.sharing.resolve_catalog_game_source",
        lambda catalog_url, ref: (
            str(package_path),
            {
                "slug": ref,
                "title": "Fixture Game",
                "package_url": "published/fixture_game.zork",
            },
        ),
    )

    result = runner.invoke(cli, ["install", "fixture_game"])

    assert result.exit_code == 0, result.output
    installed_path = library_dir / "fixture_game.zork"
    assert installed_path.exists()


def test_install_rejects_non_archive_zork_files(
    monkeypatch, tmp_path: Path, compiled_game_path: Path
) -> None:
    """A .zork file that is not a valid zip archive should be rejected."""
    runner = CliRunner()
    library_dir = tmp_path / "library"
    saves_dir = tmp_path / "saves"
    local_game = tmp_path / "fixture_game.zork"
    # compiled_game_path is a SQLite file, not a zip archive
    local_game.write_bytes(compiled_game_path.read_bytes())

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = library_dir
            self.saves_dir = saves_dir
            self.catalog_url = DEFAULT_CATALOG_URL
            self.upload_url = DEFAULT_UPLOAD_URL
            self.session_token = None
            self.publisher_email = None

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(cli, ["install", str(local_game)])

    assert result.exit_code != 0
    assert "Install failed" in result.output


def test_install_rejects_remote_urls(
    monkeypatch, tmp_path: Path
) -> None:
    runner = CliRunner()

    class FakeConfig:
        def __init__(self, **_kwargs) -> None:
            self.narrator_enabled = False
            self.games_dir = tmp_path / "library"
            self.saves_dir = tmp_path / "saves"
            self.catalog_url = DEFAULT_CATALOG_URL
            self.upload_url = DEFAULT_UPLOAD_URL
            self.session_token = None
            self.publisher_email = None

    monkeypatch.setattr(cli_module, "Config", FakeConfig)

    result = runner.invoke(cli, ["install", "https://example.com/fixture_game.zork"])

    assert result.exit_code != 0
    assert "official catalog ref or a local .zork package" in result.output


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
                    "package_url": "https://example.com/fixture_game.zork",
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


# -- _looks_like_path --------------------------------------------------------


def test_looks_like_path_with_slash() -> None:
    from anyzork.cli import _looks_like_path

    assert _looks_like_path("./game.zork") is True
    assert _looks_like_path("/tmp/game.zork") is True


def test_looks_like_path_with_extension() -> None:
    from anyzork.cli import _looks_like_path

    assert _looks_like_path("game.zork") is True
    assert _looks_like_path("game.zorkscript") is True


def test_looks_like_path_bare_name() -> None:
    from anyzork.cli import _looks_like_path

    assert _looks_like_path("my_game") is False
    assert _looks_like_path("-") is False


# -- bail-out on missing path -------------------------------------------------


def test_import_bails_on_missing_file() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["import", "/nonexistent/path/game.zork"])
    assert result.exit_code == 1
    assert "File not found" in result.output


def test_repair_bails_on_missing_file() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["repair", "/nonexistent/path/game.zork"])
    assert result.exit_code == 1
    assert "File not found" in result.output


# -- play: ValueError -> BadParameter ----------------------------------------


def test_play_nonexistent_game_ref(monkeypatch) -> None:
    runner = CliRunner()

    def fake_resolve(game_ref, cfg):
        raise ValueError("No game matching 'zzz_no_such_game'")

    monkeypatch.setattr(library_service, "resolve_game_reference", fake_resolve)
    result = runner.invoke(cli, ["play", "zzz_no_such_game"])
    assert result.exit_code != 0
    assert "No game matching" in result.output

