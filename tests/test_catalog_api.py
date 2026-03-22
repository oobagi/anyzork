from __future__ import annotations

import importlib
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from anyzork.catalog_store import CatalogStore
from anyzork.sharing import create_share_package

fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")
create_catalog_app = importlib.import_module("anyzork.catalog_api").create_catalog_app


def test_catalog_store_builds_public_catalog(
    tmp_path: Path,
    zork_archive_path: Path,
) -> None:
    package_path = tmp_path / "fixture_game.zork"
    create_share_package(
        zork_archive_path,
        package_path,
        author="AnyZork",
        description="A compact uploaded game.",
        genres=["mystery", "short"],
    )
    store = CatalogStore(tmp_path / "catalog")

    saved = store.upsert_package(package_path, published=True)

    catalog = store.build_catalog()

    assert saved.slug == "fixture_game"
    assert saved.author == "AnyZork"
    assert catalog["format"] == "anyzork-public-catalog/v1"
    assert catalog["games"][0]["slug"] == "fixture_game"
    assert catalog["games"][0]["genres"] == ["mystery", "short"]
    assert catalog["games"][0]["package_url"] == "/api/games/fixture_game/package"


def test_catalog_api_uploads_games_as_unpublished_submissions(
    tmp_path: Path,
    zork_archive_path: Path,
) -> None:
    package_path = tmp_path / "fixture_game.zork"
    create_share_package(
        zork_archive_path,
        package_path,
        author="AnyZork",
        description="Uploaded through the package manifest.",
        genres=["mystery", "short"],
        slug="fixture-custom",
    )
    app = create_catalog_app(root_dir=tmp_path / "catalog")
    client = testclient.TestClient(app)

    root_response = client.get("/")
    assert root_response.status_code == 200
    assert root_response.json()["upload_url"] == "/api/games"

    with package_path.open("rb") as handle:
        response = client.post(
            "/api/games",
            files={
                "package": ("fixture_game.zork", handle, "application/zip"),
            },
        )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["game"]["slug"] == "fixture_custom"
    assert payload["game"]["author"] == "AnyZork"
    assert payload["game"]["genres"] == ["mystery", "short"]
    assert payload["game"]["published"] is False

    list_response = client.get("/api/games")
    assert list_response.status_code == 200
    assert list_response.json()["games"] == []

    catalog_response = client.get("/catalog.json")
    assert catalog_response.status_code == 200
    assert catalog_response.json()["games"] == []

    detail_response = client.get("/api/games/fixture_custom")
    assert detail_response.status_code == 404

    download_response = client.get("/api/games/fixture_custom/package")
    assert download_response.status_code == 404


def test_catalog_api_rejects_duplicate_slug_submissions(
    tmp_path: Path,
    zork_archive_path: Path,
) -> None:
    package_path = tmp_path / "fixture_game.zork"
    create_share_package(
        zork_archive_path,
        package_path,
        slug="fixture-custom",
    )
    app = create_catalog_app(root_dir=tmp_path / "catalog")
    client = testclient.TestClient(app)

    with package_path.open("rb") as handle:
        first = client.post(
            "/api/games",
            files={"package": ("fixture_game.zork", handle, "application/zip")},
        )

    assert first.status_code == 201, first.text

    with package_path.open("rb") as handle:
        second = client.post(
            "/api/games",
            files={"package": ("fixture_game.zork", handle, "application/zip")},
        )

    assert second.status_code == 400, second.text
    assert "already exists for slug 'fixture_custom'" in second.json()["detail"]


def test_catalog_api_ignores_client_filename_paths(
    monkeypatch,
    tmp_path: Path,
    zork_archive_path: Path,
) -> None:
    package_path = tmp_path / "fixture_game.zork"
    create_share_package(zork_archive_path, package_path, slug="fixture-custom")
    app = create_catalog_app(root_dir=tmp_path / "catalog")
    client = testclient.TestClient(app)
    scratch_dir = tmp_path / "scratch"
    scratch_dir.mkdir()

    class StableTemporaryDirectory:
        def __init__(self, *args, **kwargs) -> None:
            self._inner = TemporaryDirectory(dir=scratch_dir, prefix="catalog-test-")

        def __enter__(self) -> str:
            return self._inner.__enter__()

        def __exit__(self, exc_type, exc, tb) -> None:
            return self._inner.__exit__(exc_type, exc, tb)

    monkeypatch.setattr("anyzork.catalog_api.tempfile.TemporaryDirectory", StableTemporaryDirectory)

    outside_target = tmp_path / "escape.zork"

    with package_path.open("rb") as handle:
        response = client.post(
            "/api/games",
            files={"package": ("../../escape.zork", handle, "application/zip")},
        )

    assert response.status_code == 201, response.text
    assert not outside_target.exists()
