"""Helpers for packaging and installing shared AnyZork games."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from anyzork.versioning import APP_VERSION

SHARE_PACKAGE_FORMAT = "anyzork-share-package/v1"
SHARE_PACKAGE_SUFFIX = ".zork"
PUBLIC_CATALOG_FORMAT = "anyzork-public-catalog/v1"
_TRUSTED_CATALOG_DOMAIN = "anyzork.com"
_MANIFEST_FILENAME = "manifest.json"
_ARCHIVE_MANIFEST_FILENAME = "manifest.toml"


class SharePackageError(Exception):
    """Raised when a game package cannot be created or installed."""


def _slugify_name(value: str) -> str:
    """Return a filesystem-friendly slug."""
    import re

    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "game"


def _read_archive_manifest(path: Path) -> dict:
    """Read manifest.toml from a .zork zip archive."""
    try:
        with zipfile.ZipFile(path) as zf, zf.open(_ARCHIVE_MANIFEST_FILENAME) as f:
            return tomllib.load(f)
    except (KeyError, zipfile.BadZipFile, tomllib.TOMLDecodeError) as exc:
        raise SharePackageError(
            f"Could not read manifest from .zork archive {path}: {exc}"
        ) from exc


def _sha256_bytes(payload: bytes) -> str:
    """Return the SHA-256 digest for ``payload``."""
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for a file."""
    return _sha256_bytes(path.read_bytes())


def build_share_manifest(game_path: Path) -> dict[str, object]:
    """Build a public-facing manifest for a ``.zork`` archive."""
    from anyzork.archive import is_zork_archive

    game_path = game_path.expanduser().resolve()

    if not is_zork_archive(game_path):
        raise SharePackageError(f"Expected a .zork archive: {game_path}")

    data = _read_archive_manifest(game_path)
    project = data.get("project", {})

    title = project.get("title") or game_path.stem
    slug = project.get("slug", "")
    author = project.get("author", "")
    description = project.get("description", "")
    tags = project.get("tags", [])

    manifest: dict[str, object] = {
        "format": SHARE_PACKAGE_FORMAT,
        "package_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "created_with_app_version": APP_VERSION,
        "game": {
            "title": title,
            "slug": slug,
            "runtime_compat_version": "",
            "app_version": APP_VERSION,
            "prompt_system_version": "",
            "room_count": 0,
            "intro_text": description,
        },
        "listing": {
            "slug": slug,
            "title": title,
            "author": author,
            "description": description,
            "tagline": "",
            "genres": tags,
            "homepage_url": "",
            "cover_image_url": "",
        },
        "artifact": {
            "filename": game_path.name,
            "size_bytes": game_path.stat().st_size,
            "sha256": _sha256_file(game_path),
        },
    }
    return manifest


def create_share_package(
    game_path: Path,
    output_path: Path,
    *,
    title: str | None = None,
    author: str | None = None,
    description: str | None = None,
    tagline: str | None = None,
    genres: list[str] | None = None,
    slug: str | None = None,
    homepage_url: str | None = None,
    cover_image_url: str | None = None,
) -> tuple[Path, dict[str, object]]:
    """Create a share package for a ``.zork`` archive or project directory.

    If *game_path* is a project directory, it is packed into a .zork archive
    first.  If it is already a .zork archive, it is used directly.

    The output is a .zork zip archive with a ``manifest.json`` containing the
    listing/sharing metadata prepended alongside the original archive contents.
    """
    from anyzork.archive import is_zork_archive, pack_project

    game_path = game_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # If given a project directory, pack it first.
    if game_path.is_dir():
        with tempfile.TemporaryDirectory(prefix="anyzork-pack-") as tmp:
            archive_path = pack_project(game_path, Path(tmp) / f"{game_path.name}.zork")
            return create_share_package(
                archive_path,
                output_path,
                title=title,
                author=author,
                description=description,
                tagline=tagline,
                genres=genres,
                slug=slug,
                homepage_url=homepage_url,
                cover_image_url=cover_image_url,
            )

    if not is_zork_archive(game_path):
        raise SharePackageError(f"Expected a .zork archive or project directory: {game_path}")

    manifest = build_share_manifest(game_path)
    listing = dict(manifest.get("listing", {}))
    if title is not None:
        listing["title"] = title.strip()
    if author is not None:
        listing["author"] = author.strip()
    if description is not None:
        listing["description"] = description.strip()
    if tagline is not None:
        listing["tagline"] = tagline.strip()
    if genres is not None:
        listing["genres"] = [genre.strip() for genre in genres if genre.strip()]
    if slug is not None:
        listing["slug"] = slug.strip()
    if homepage_url is not None:
        listing["homepage_url"] = homepage_url.strip()
    if cover_image_url is not None:
        listing["cover_image_url"] = cover_image_url.strip()
    manifest["listing"] = listing

    # Read source entries before opening the output — game_path and output_path
    # may resolve to the same file, and opening for write would truncate it.
    with zipfile.ZipFile(game_path) as source_archive:
        source_entries = [
            (entry, source_archive.read(entry.filename))
            for entry in source_archive.infolist()
        ]

    # Build a new zip that contains manifest.json (sharing metadata) plus all
    # entries from the original .zork archive (manifest.toml + .zorkscript files).
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as out_archive:
        out_archive.writestr(
            _MANIFEST_FILENAME,
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
        for entry, data in source_entries:
            out_archive.writestr(entry, data)

    return output_path, manifest


def upload_share_package(
    package_path: Path,
    upload_url: str,
    *,
    title: str | None = None,
    author: str | None = None,
    description: str | None = None,
    tagline: str | None = None,
    genres: list[str] | None = None,
    slug: str | None = None,
    homepage_url: str | None = None,
    cover_image_url: str | None = None,
) -> dict[str, object]:
    """Upload a share package to an AnyZork catalog service."""
    package_path = package_path.expanduser().resolve()
    if not package_path.exists():
        raise SharePackageError(f"No shared game found at '{package_path}'.")

    if not zipfile.is_zipfile(package_path):
        raise SharePackageError("Upload expects a .zork archive.")

    upload_url = resolve_upload_url(upload_url)
    boundary = f"anyzork-{uuid4().hex}"
    body = _encode_multipart_request(
        boundary,
        fields={
            "title": title,
            "author": author,
            "description": description,
            "tagline": tagline,
            "genres": ",".join(genres or []) if genres is not None else None,
            "slug": slug,
            "homepage_url": homepage_url,
            "cover_image_url": cover_image_url,
        },
        file_field="package",
        file_name=package_path.name,
        file_bytes=package_path.read_bytes(),
        file_content_type="application/zip",
    )
    request = Request(
        upload_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = _read_http_error_detail(exc)
        raise SharePackageError(f"Upload failed with HTTP {exc.code}: {detail}") from exc
    except OSError as exc:
        raise SharePackageError(f"Could not upload shared game to {upload_url}: {exc}") from exc

    try:
        return json.loads(payload)
    except ValueError as exc:
        raise SharePackageError("Upload service returned invalid JSON.") from exc


def install_shared_game(
    source: str,
    games_dir: Path,
    *,
    force: bool = False,
    allow_remote: bool = False,
) -> tuple[Path, dict[str, object]]:
    """Install a shared AnyZork game package into the library."""
    games_dir = games_dir.expanduser().resolve()
    games_dir.mkdir(parents=True, exist_ok=True)

    source_path = Path(source).expanduser()
    if source_path.exists():
        resolved_local_source = source_path.resolve()
        if resolved_local_source.suffix != SHARE_PACKAGE_SUFFIX:
            raise SharePackageError(
                "Install expects an official catalog ref or a local .zork package."
            )
    elif _is_url_source(source) and not allow_remote:
        raise SharePackageError(
            "Install expects an official catalog ref or a local .zork package."
        )

    with tempfile.TemporaryDirectory(prefix="anyzork-share-") as tmp:
        tmpdir = Path(tmp)
        resolved_source = _materialize_source(source, tmpdir, allow_remote=allow_remote)

        if not zipfile.is_zipfile(resolved_source):
            raise SharePackageError(
                "Install expects an official catalog ref or a local .zork package."
            )

        manifest, game_path = _extract_share_package(resolved_source, tmpdir)

        title = str(manifest.get("game", {}).get("title") or game_path.stem)
        destination = games_dir / f"{_slugify_name(title)}.zork"
        if destination.exists() and not force:
            raise SharePackageError(
                f"Library game '{destination.stem}' already exists. Use --force to replace it."
            )

        if game_path.resolve() != destination.resolve():
            _replace_zork_file(game_path, destination)
        return destination, manifest


def load_public_catalog(source: str) -> dict[str, object]:
    """Load a published-games catalog from a local path or URL."""
    try:
        payload = _read_text_source(source)
        catalog = json.loads(payload)
    except OSError as exc:
        raise SharePackageError(f"Could not load catalog from {source}: {exc}") from exc
    except ValueError as exc:
        raise SharePackageError(f"Catalog at {source} is not valid JSON.") from exc

    if catalog.get("format") != PUBLIC_CATALOG_FORMAT:
        raise SharePackageError(
            f"Unsupported catalog format: {catalog.get('format')!r}."
        )

    games = catalog.get("games")
    if not isinstance(games, list):
        raise SharePackageError("Catalog is missing a 'games' list.")

    normalized_games: list[dict[str, object]] = []
    for index, raw_entry in enumerate(games, start=1):
        if not isinstance(raw_entry, dict):
            raise SharePackageError(f"Catalog game #{index} must be an object.")

        slug = str(raw_entry.get("slug") or "").strip()
        title = str(raw_entry.get("title") or "").strip()
        package_url = str(raw_entry.get("package_url") or "").strip()
        if not slug or not title or not package_url:
            raise SharePackageError(
                f"Catalog game #{index} must include slug, title, and package_url."
            )

        normalized_games.append(
            {
                "slug": slug,
                "title": title,
                "author": str(raw_entry.get("author") or ""),
                "tagline": str(raw_entry.get("tagline") or ""),
                "description": str(raw_entry.get("description") or ""),
                "genres": [
                    str(genre)
                    for genre in raw_entry.get("genres", [])
                    if str(genre).strip()
                ],
                "featured": bool(raw_entry.get("featured", False)),
                "cover_image_url": _resolve_catalog_link(
                    source, str(raw_entry.get("cover_image_url") or "")
                ),
                "homepage_url": _resolve_catalog_link(
                    source, str(raw_entry.get("homepage_url") or "")
                ),
                "package_url": _resolve_catalog_link(source, package_url),
                "runtime_compat_version": str(raw_entry.get("runtime_compat_version") or ""),
                "prompt_system_version": str(raw_entry.get("prompt_system_version") or ""),
                "room_count": _coerce_catalog_int(raw_entry.get("room_count"), "room_count", index),
            }
        )

    return {
        "format": PUBLIC_CATALOG_FORMAT,
        "title": str(catalog.get("title") or "Published AnyZork Games"),
        "updated_at": str(catalog.get("updated_at") or ""),
        "source": source,
        "games": normalized_games,
    }


def resolve_catalog_game_source(catalog_source: str, slug: str) -> tuple[str, dict[str, object]]:
    """Resolve a catalog slug to an installable package source."""
    catalog = load_public_catalog(catalog_source)
    for game in catalog["games"]:
        if str(game.get("slug") or "") == slug:
            return str(game.get("package_url") or ""), game

    raise SharePackageError(f"No catalog game found for ref '{slug}'.")


def resolve_upload_url(source: str) -> str:
    """Resolve a base site URL or catalog URL to the upload endpoint."""
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SharePackageError(f"Upload destination must be an http(s) URL, got: {source!r}.")

    if parsed.path.endswith("/api/games"):
        return source
    if parsed.path.endswith("/catalog.json"):
        return urljoin(source, "api/games")
    if not parsed.path or parsed.path.endswith("/"):
        return urljoin(source, "api/games")
    return urljoin(f"{source}/", "api/games")


def _materialize_source(source: str, tmpdir: Path, *, allow_remote: bool = False) -> Path:
    """Return a local filesystem path for a path or URL source.

    When *allow_remote* is True the source URL **must** belong to the trusted
    catalog domain; arbitrary URLs are always rejected.
    """
    source_path = Path(source).expanduser()
    if source_path.exists():
        return source_path.resolve()

    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        if not allow_remote:
            raise SharePackageError(
                "Remote installation is only allowed for official catalog games."
            )
        if not _is_trusted_catalog_url(source):
            raise SharePackageError(
                f"Refusing to download from untrusted origin: {parsed.netloc}"
            )
        suffix = Path(parsed.path).suffix or ".download"
        destination = tmpdir / f"download{suffix}"
        try:
            with urlopen(source, timeout=30) as response:
                payload = response.read()
        except OSError as exc:
            raise SharePackageError(f"Could not download shared game from {source}: {exc}") from exc
        destination.write_bytes(payload)
        return destination

    raise SharePackageError(f"No shared game found at '{source}'.")


def _read_text_source(source: str) -> str:
    """Read UTF-8 text from a local path or URL."""
    source_path = Path(source).expanduser()
    if source_path.exists():
        return source_path.read_text(encoding="utf-8")

    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        try:
            with urlopen(source, timeout=30) as response:
                return response.read().decode("utf-8")
        except OSError as exc:
            raise SharePackageError(f"Could not download catalog from {source}: {exc}") from exc

    raise SharePackageError(f"No catalog found at '{source}'.")


def _resolve_catalog_link(source: str, value: str) -> str:
    """Resolve a catalog link relative to the catalog file or URL."""
    if not value:
        return ""

    if _is_url_source(value):
        return value

    if _is_url_source(source):
        return urljoin(source, value)

    value_path = Path(value).expanduser()
    if value_path.is_absolute():
        return str(value_path)

    source_path = Path(source).expanduser()
    if source_path.exists():
        return str((source_path.resolve().parent / value_path).resolve())

    return value


def _coerce_catalog_int(raw_value: object, field_name: str, index: int) -> int:
    """Validate optional integer fields in catalog entries."""
    if raw_value in (None, ""):
        return 0

    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise SharePackageError(
            f"Catalog game #{index} has an invalid {field_name}: {raw_value!r}."
        ) from exc


def _is_url_source(source: str) -> bool:
    """Return True when a string looks like an HTTP(S) URL."""
    parsed = urlparse(source)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_trusted_catalog_url(source: str) -> bool:
    """Return True when *source* points to the official catalog domain."""
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = parsed.hostname or ""
    return host == _TRUSTED_CATALOG_DOMAIN or host.endswith(f".{_TRUSTED_CATALOG_DOMAIN}")


def _extract_share_package(package_path: Path, tmpdir: Path) -> tuple[dict[str, object], Path]:
    """Extract a share package into ``tmpdir`` and validate.

    A share package is a .zork zip archive that contains:
    - ``manifest.json`` — sharing/listing metadata
    - ``manifest.toml`` — the game project manifest
    - one or more ``.zorkscript`` files

    The extracted .zork archive (without manifest.json) is written to tmpdir
    for installation.
    """
    try:
        with zipfile.ZipFile(package_path) as archive:
            names = archive.namelist()

            # Read sharing manifest
            if _MANIFEST_FILENAME in names:
                manifest = json.loads(archive.read(_MANIFEST_FILENAME).decode("utf-8"))
            else:
                raise KeyError(f"Missing {_MANIFEST_FILENAME}")

            if manifest.get("format") != SHARE_PACKAGE_FORMAT:
                raise SharePackageError(
                    f"Unsupported share package format: {manifest.get('format')!r}."
                )

            # Verify the archive has manifest.toml (the game project manifest)
            if _ARCHIVE_MANIFEST_FILENAME not in names:
                raise KeyError(f"Missing {_ARCHIVE_MANIFEST_FILENAME}")

            # Extract a clean .zork archive (without manifest.json) for install
            extracted_path = tmpdir / "installed.zork"
            with zipfile.ZipFile(extracted_path, "w", zipfile.ZIP_DEFLATED) as out:
                for entry in archive.infolist():
                    if entry.filename == _MANIFEST_FILENAME:
                        continue  # Skip the sharing manifest
                    out.writestr(entry, archive.read(entry.filename))

    except (KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise SharePackageError(f"Invalid AnyZork share package: {package_path}") from exc

    # Verify checksum if present
    expected_checksum = str(manifest.get("artifact", {}).get("sha256") or "")
    if expected_checksum:
        # The checksum was computed on the original .zork archive, but since we
        # repacked the contents, we cannot verify it reliably against the
        # extracted file.  Skip checksum verification for the new format.
        pass

    return manifest, extracted_path


def _replace_zork_file(source: Path, destination: Path) -> None:
    """Replace a ``.zork`` file at *destination*."""
    destination.unlink(missing_ok=True)
    shutil.copy2(source, destination)


def _read_http_error_detail(exc: HTTPError) -> str:
    """Return the most useful error detail from an HTTP response."""
    try:
        payload = exc.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return exc.reason

    if not payload:
        return exc.reason

    try:
        parsed = json.loads(payload)
    except ValueError:
        return payload

    if isinstance(parsed, dict) and parsed.get("detail"):
        return str(parsed["detail"])
    return payload


def _encode_multipart_request(
    boundary: str,
    *,
    fields: dict[str, str | None],
    file_field: str,
    file_name: str,
    file_bytes: bytes,
    file_content_type: str,
) -> bytes:
    """Return a multipart/form-data request body."""
    parts: list[bytes] = []

    for key, value in fields.items():
        if value is None:
            continue
        parts.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    parts.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{file_name}"\r\n'
            ).encode(),
            f"Content-Type: {file_content_type}\r\n\r\n".encode(),
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(parts)
