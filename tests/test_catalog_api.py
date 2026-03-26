from __future__ import annotations

import hashlib
import importlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from anyzork.catalog_store import CatalogStore
from anyzork.sharing import create_share_package

fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")
create_catalog_app = importlib.import_module("anyzork.catalog_api").create_catalog_app


def _create_test_session(
    store: CatalogStore, email: str = "test@example.com",
) -> tuple[str, str]:
    """Create a session and return (raw_token, email_hash)."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    email_hash = hashlib.sha256(email.encode()).hexdigest()
    store.create_session(token_hash, email_hash)
    return token, email_hash


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


# -- Auth endpoint tests ---------------------------------------------------


def test_login_creates_code_in_db(tmp_path: Path) -> None:
    app = create_catalog_app(root_dir=tmp_path / "catalog")
    client = testclient.TestClient(app)

    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["message"] == "Code sent."
    assert data["email"] == "test@example.com"


def test_verify_correct_code_returns_session(tmp_path: Path) -> None:
    store = CatalogStore(tmp_path / "catalog")
    app = create_catalog_app(root_dir=tmp_path / "catalog")
    client = testclient.TestClient(app)

    # Manually create a code in the DB.
    email = "test@example.com"
    code = "123456"
    email_hash = hashlib.sha256(email.encode()).hexdigest()
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    store.create_auth_code(email_hash, code_hash, expires_at)

    response = client.post(
        "/api/auth/verify",
        json={"email": email, "code": code},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert "session_token" in data
    assert data["email"] == email


def test_verify_expired_code_rejected(tmp_path: Path) -> None:
    store = CatalogStore(tmp_path / "catalog")
    app = create_catalog_app(root_dir=tmp_path / "catalog")
    client = testclient.TestClient(app)

    email = "test@example.com"
    code = "123456"
    email_hash = hashlib.sha256(email.encode()).hexdigest()
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    # Expired 5 minutes ago.
    expires_at = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    store.create_auth_code(email_hash, code_hash, expires_at)

    response = client.post(
        "/api/auth/verify",
        json={"email": email, "code": code},
    )

    assert response.status_code == 401, response.text


def test_verify_max_attempts_rejected(tmp_path: Path) -> None:
    store = CatalogStore(tmp_path / "catalog")
    app = create_catalog_app(root_dir=tmp_path / "catalog")
    client = testclient.TestClient(app)

    email = "test@example.com"
    code = "123456"
    email_hash = hashlib.sha256(email.encode()).hexdigest()
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    store.create_auth_code(email_hash, code_hash, expires_at)

    # Submit 5 wrong codes.
    for _ in range(5):
        client.post(
            "/api/auth/verify",
            json={"email": email, "code": "000000"},
        )

    # Now even the correct code should fail.
    response = client.post(
        "/api/auth/verify",
        json={"email": email, "code": code},
    )

    assert response.status_code == 401, response.text


def test_rate_limiting_fourth_code_rejected(tmp_path: Path) -> None:
    app = create_catalog_app(root_dir=tmp_path / "catalog")
    client = testclient.TestClient(app)

    # Request 3 codes (allowed).
    for _ in range(3):
        resp = client.post(
            "/api/auth/login",
            json={"email": "test@example.com"},
        )
        assert resp.status_code == 200

    # 4th should be rate-limited.
    resp = client.post(
        "/api/auth/login",
        json={"email": "test@example.com"},
    )
    assert resp.status_code == 429


def test_session_validation(tmp_path: Path) -> None:
    store = CatalogStore(tmp_path / "catalog")
    token, email_hash = _create_test_session(store)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    result = store.validate_session(token_hash)
    assert result == email_hash

    # Invalid token returns None.
    assert store.validate_session("invalid_hash") is None


def test_logout_deletes_session(tmp_path: Path) -> None:
    store = CatalogStore(tmp_path / "catalog")
    app = create_catalog_app(root_dir=tmp_path / "catalog")
    client = testclient.TestClient(app)

    token, _email_hash = _create_test_session(store)

    response = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text

    # Session should now be invalid.
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    assert store.validate_session(token_hash) is None


def test_my_games_requires_auth(tmp_path: Path) -> None:
    app = create_catalog_app(root_dir=tmp_path / "catalog")
    client = testclient.TestClient(app)

    response = client.get("/api/my/games")
    assert response.status_code == 401


def test_my_games_filters_by_owner(
    tmp_path: Path, zork_archive_path: Path,
) -> None:
    store = CatalogStore(tmp_path / "catalog")
    app = create_catalog_app(root_dir=tmp_path / "catalog")
    client = testclient.TestClient(app)

    token, _email_hash = _create_test_session(store)

    # Upload a game with auth.
    package_path = tmp_path / "fixture_game.zork"
    create_share_package(
        zork_archive_path,
        package_path,
        slug="my-game",
    )
    with package_path.open("rb") as handle:
        upload_resp = client.post(
            "/api/games",
            files={
                "package": (
                    "fixture_game.zork", handle, "application/zip",
                ),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert upload_resp.status_code == 201, upload_resp.text

    # Upload another game without auth.
    package_path_2 = tmp_path / "other_game.zork"
    create_share_package(
        zork_archive_path,
        package_path_2,
        slug="other-game",
    )
    with package_path_2.open("rb") as handle:
        client.post(
            "/api/games",
            files={
                "package": (
                    "other_game.zork", handle, "application/zip",
                ),
            },
        )

    # my-games should only return the authed user's game.
    response = client.get(
        "/api/my/games",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    games = response.json()["games"]
    assert len(games) == 1
    assert games[0]["slug"] == "my_game"


def test_upload_with_session_stores_email_hash(
    tmp_path: Path, zork_archive_path: Path,
) -> None:
    store = CatalogStore(tmp_path / "catalog")
    app = create_catalog_app(root_dir=tmp_path / "catalog")
    client = testclient.TestClient(app)

    token, email_hash = _create_test_session(store)

    package_path = tmp_path / "fixture_game.zork"
    create_share_package(
        zork_archive_path, package_path, slug="auth-game",
    )
    with package_path.open("rb") as handle:
        response = client.post(
            "/api/games",
            files={
                "package": (
                    "fixture_game.zork", handle, "application/zip",
                ),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 201, response.text

    game = store.get_game("auth_game")
    assert game is not None
    assert game.email_hash == email_hash


def test_delete_ownership_enforcement(
    tmp_path: Path, zork_archive_path: Path,
) -> None:
    store = CatalogStore(tmp_path / "catalog")
    app = create_catalog_app(root_dir=tmp_path / "catalog")
    client = testclient.TestClient(app)

    token_a, _hash_a = _create_test_session(
        store, email="alice@example.com",
    )
    token_b, _hash_b = _create_test_session(
        store, email="bob@example.com",
    )

    # Alice uploads.
    package_path = tmp_path / "fixture_game.zork"
    create_share_package(
        zork_archive_path, package_path, slug="alice-game",
    )
    with package_path.open("rb") as handle:
        client.post(
            "/api/games",
            files={
                "package": (
                    "fixture_game.zork", handle, "application/zip",
                ),
            },
            headers={"Authorization": f"Bearer {token_a}"},
        )

    # Bob tries to delete Alice's game.
    resp = client.delete(
        "/api/games/alice_game",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403

    # Alice can delete her own game.
    resp = client.delete(
        "/api/games/alice_game",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200


def test_put_ownership_enforcement_and_auto_unpublish(
    tmp_path: Path, zork_archive_path: Path,
) -> None:
    store = CatalogStore(tmp_path / "catalog")
    app = create_catalog_app(root_dir=tmp_path / "catalog")
    client = testclient.TestClient(app)

    token_a, _hash_a = _create_test_session(
        store, email="alice@example.com",
    )
    token_b, _hash_b = _create_test_session(
        store, email="bob@example.com",
    )

    # Alice uploads and gets published.
    package_path = tmp_path / "fixture_game.zork"
    create_share_package(
        zork_archive_path, package_path, slug="alice-pub",
    )
    with package_path.open("rb") as handle:
        client.post(
            "/api/games",
            files={
                "package": (
                    "fixture_game.zork", handle, "application/zip",
                ),
            },
            headers={"Authorization": f"Bearer {token_a}"},
        )
    store.set_published("alice_pub", published=True)

    # Bob cannot update Alice's game.
    resp = client.put(
        "/api/games/alice_pub",
        data={"title": "Hijacked"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403

    # Alice updates her game.
    resp = client.put(
        "/api/games/alice_pub",
        data={"title": "Updated Title"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200
    game = resp.json()["game"]
    assert game["title"] == "Updated Title"
    assert game["published"] is False  # auto-unpublished


# -- Admin file management tests ------------------------------------------


def _upload_game(client, zork_archive_path, tmp_path, slug, admin_token):
    """Helper: upload a game and return its slug."""
    package_path = tmp_path / f"{slug}.zork"
    create_share_package(
        zork_archive_path, package_path, slug=slug,
    )
    with package_path.open("rb") as handle:
        resp = client.post(
            "/api/games",
            files={"package": (f"{slug}.zork", handle, "application/zip")},
        )
    assert resp.status_code == 201, resp.text
    return resp.json()["game"]["slug"]


def test_admin_delete_game(
    tmp_path: Path, zork_archive_path: Path,
) -> None:
    import os
    os.environ["ANYZORK_ADMIN_TOKEN"] = "test-admin-token"
    try:
        app = create_catalog_app(root_dir=tmp_path / "catalog")
        client = testclient.TestClient(app)
        slug = _upload_game(
            client, zork_archive_path, tmp_path, "del-game", "test-admin-token",
        )

        # Delete without token fails.
        resp = client.delete(f"/api/admin/games/{slug}")
        assert resp.status_code == 403

        # Delete with token succeeds.
        resp = client.delete(
            f"/api/admin/games/{slug}",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"]

        # Game is gone.
        resp = client.get(
            "/api/admin/games",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert all(g["slug"] != slug for g in resp.json()["games"])
    finally:
        os.environ.pop("ANYZORK_ADMIN_TOKEN", None)


def test_admin_delete_game_not_found(tmp_path: Path) -> None:
    import os
    os.environ["ANYZORK_ADMIN_TOKEN"] = "test-admin-token"
    try:
        app = create_catalog_app(root_dir=tmp_path / "catalog")
        client = testclient.TestClient(app)

        resp = client.delete(
            "/api/admin/games/nonexistent",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert resp.status_code == 404
    finally:
        os.environ.pop("ANYZORK_ADMIN_TOKEN", None)


def test_admin_list_game_files(
    tmp_path: Path, zork_archive_path: Path,
) -> None:
    import os
    os.environ["ANYZORK_ADMIN_TOKEN"] = "test-admin-token"
    try:
        app = create_catalog_app(root_dir=tmp_path / "catalog")
        client = testclient.TestClient(app)
        slug = _upload_game(
            client, zork_archive_path, tmp_path, "files-game", "test-admin-token",
        )

        resp = client.get(
            f"/api/admin/games/{slug}/files",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert resp.status_code == 200
        files = resp.json()["files"]
        assert len(files) > 0
        filenames = [f["filename"] for f in files]
        # Should contain manifest.toml and .zorkscript files.
        assert "manifest.toml" in filenames
        # All files should have size and editable info.
        for f in files:
            assert "size" in f
            assert "editable" in f
    finally:
        os.environ.pop("ANYZORK_ADMIN_TOKEN", None)


def test_admin_read_game_file(
    tmp_path: Path, zork_archive_path: Path,
) -> None:
    import os
    os.environ["ANYZORK_ADMIN_TOKEN"] = "test-admin-token"
    try:
        app = create_catalog_app(root_dir=tmp_path / "catalog")
        client = testclient.TestClient(app)
        slug = _upload_game(
            client, zork_archive_path, tmp_path, "read-game", "test-admin-token",
        )

        resp = client.get(
            f"/api/admin/games/{slug}/files/manifest.toml",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "manifest.toml"
        assert "content" in data
        assert "[project]" in data["content"]
    finally:
        os.environ.pop("ANYZORK_ADMIN_TOKEN", None)


def test_admin_read_game_file_not_found(
    tmp_path: Path, zork_archive_path: Path,
) -> None:
    import os
    os.environ["ANYZORK_ADMIN_TOKEN"] = "test-admin-token"
    try:
        app = create_catalog_app(root_dir=tmp_path / "catalog")
        client = testclient.TestClient(app)
        slug = _upload_game(
            client, zork_archive_path, tmp_path, "read-nf", "test-admin-token",
        )

        resp = client.get(
            f"/api/admin/games/{slug}/files/nonexistent.toml",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert resp.status_code == 404
    finally:
        os.environ.pop("ANYZORK_ADMIN_TOKEN", None)


def test_admin_read_rejects_invalid_filenames(
    tmp_path: Path, zork_archive_path: Path,
) -> None:
    import os
    os.environ["ANYZORK_ADMIN_TOKEN"] = "test-admin-token"
    try:
        app = create_catalog_app(root_dir=tmp_path / "catalog")
        client = testclient.TestClient(app)
        slug = _upload_game(
            client, zork_archive_path, tmp_path, "traversal-test", "test-admin-token",
        )
        headers = {"X-Admin-Token": "test-admin-token"}

        # Filenames with spaces should be rejected.
        resp = client.get(
            f"/api/admin/games/{slug}/files/bad file.toml",
            headers=headers,
        )
        assert resp.status_code == 400

        # Filenames starting with dots should be rejected.
        resp = client.get(
            f"/api/admin/games/{slug}/files/..secret",
            headers=headers,
        )
        assert resp.status_code == 400

        # Filenames with special chars should be rejected.
        resp = client.get(
            f"/api/admin/games/{slug}/files/$evil.toml",
            headers=headers,
        )
        assert resp.status_code == 400
    finally:
        os.environ.pop("ANYZORK_ADMIN_TOKEN", None)


def test_admin_write_game_file(
    tmp_path: Path, zork_archive_path: Path,
) -> None:
    import os
    os.environ["ANYZORK_ADMIN_TOKEN"] = "test-admin-token"
    try:
        app = create_catalog_app(root_dir=tmp_path / "catalog")
        client = testclient.TestClient(app)
        slug = _upload_game(
            client, zork_archive_path, tmp_path, "write-game", "test-admin-token",
        )

        new_content = '[project]\ntitle = "Updated Game"\n'
        resp = client.put(
            f"/api/admin/games/{slug}/files/manifest.toml",
            json={"content": new_content},
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "File updated."

        # Verify the content was saved.
        resp = client.get(
            f"/api/admin/games/{slug}/files/manifest.toml",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == new_content
    finally:
        os.environ.pop("ANYZORK_ADMIN_TOKEN", None)


def test_admin_write_rejects_non_editable_extension(
    tmp_path: Path, zork_archive_path: Path,
) -> None:
    import os
    os.environ["ANYZORK_ADMIN_TOKEN"] = "test-admin-token"
    try:
        app = create_catalog_app(root_dir=tmp_path / "catalog")
        client = testclient.TestClient(app)
        slug = _upload_game(
            client, zork_archive_path, tmp_path, "ext-test", "test-admin-token",
        )

        resp = client.put(
            f"/api/admin/games/{slug}/files/evil.py",
            json={"content": "import os; os.system('rm -rf /')"},
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert resp.status_code == 400
    finally:
        os.environ.pop("ANYZORK_ADMIN_TOKEN", None)


def test_admin_write_zorkscript_file(
    tmp_path: Path, zork_archive_path: Path,
) -> None:
    import os
    os.environ["ANYZORK_ADMIN_TOKEN"] = "test-admin-token"
    try:
        app = create_catalog_app(root_dir=tmp_path / "catalog")
        client = testclient.TestClient(app)
        slug = _upload_game(
            client, zork_archive_path, tmp_path, "zs-write", "test-admin-token",
        )

        # Find the .zorkscript file.
        files_resp = client.get(
            f"/api/admin/games/{slug}/files",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        zs_files = [
            f for f in files_resp.json()["files"]
            if f["filename"].endswith(".zorkscript")
        ]
        assert len(zs_files) > 0
        zs_name = zs_files[0]["filename"]

        new_content = "room Start { description: 'Updated room' }"
        resp = client.put(
            f"/api/admin/games/{slug}/files/{zs_name}",
            json={"content": new_content},
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert resp.status_code == 200

        # Verify.
        resp = client.get(
            f"/api/admin/games/{slug}/files/{zs_name}",
            headers={"X-Admin-Token": "test-admin-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == new_content
    finally:
        os.environ.pop("ANYZORK_ADMIN_TOKEN", None)
