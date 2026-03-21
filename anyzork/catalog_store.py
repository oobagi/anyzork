"""Persistent storage for uploaded public AnyZork game packages."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from anyzork.sharing import (
    PUBLIC_CATALOG_FORMAT,
    SharePackageError,
    _extract_share_package,
    _sha256_file,
    _slugify_name,
)


@dataclass(slots=True)
class UploadedGame:
    """Normalized public catalog entry plus local package path."""

    slug: str
    title: str
    author: str
    description: str
    tagline: str
    genres: list[str]
    package_path: str
    package_url: str
    download_url: str
    checksum_sha256: str
    runtime_compat_version: str
    prompt_system_version: str
    room_count: int
    region_count: int
    homepage_url: str
    cover_image_url: str
    created_at: str
    updated_at: str
    published: bool

    def to_api_dict(self) -> dict[str, object]:
        """Return the API representation."""
        return {
            "slug": self.slug,
            "title": self.title,
            "author": self.author,
            "description": self.description,
            "tagline": self.tagline,
            "genres": self.genres,
            "package_url": self.package_url,
            "download_url": self.download_url,
            "runtime_compat_version": self.runtime_compat_version,
            "prompt_system_version": self.prompt_system_version,
            "room_count": self.room_count,
            "region_count": self.region_count,
            "homepage_url": self.homepage_url,
            "cover_image_url": self.cover_image_url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "published": self.published,
        }


class CatalogStore:
    """SQLite + filesystem persistence for uploaded public games."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.expanduser().resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root_dir / "catalog.db"
        self.packages_dir = self.root_dir / "packages"
        self.packages_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def upsert_package(
        self,
        package_path: Path,
        *,
        title: str | None = None,
        author: str | None = None,
        description: str | None = None,
        tagline: str | None = None,
        genres: Iterable[str] | None = None,
        slug: str | None = None,
        homepage_url: str | None = None,
        cover_image_url: str | None = None,
        published: bool = False,
        allow_replace: bool = False,
    ) -> UploadedGame:
        """Validate and store an uploaded ``.anyzorkpkg``."""
        package_path = package_path.expanduser().resolve()
        manifest = _read_manifest_from_package(package_path)
        game_meta = dict(manifest.get("game", {}))
        listing_meta = dict(manifest.get("listing", {}))
        normalized_title = (
            title
            or str(listing_meta.get("title") or "")
            or str(game_meta.get("title") or package_path.stem)
        ).strip()
        normalized_slug = _slugify_name(
            slug or str(listing_meta.get("slug") or "").strip() or normalized_title
        )
        existing = self.get_game(normalized_slug)
        if existing is not None and not allow_replace:
            raise SharePackageError(
                f"A catalog entry already exists for slug '{normalized_slug}'. "
                "Choose a different slug."
            )

        package_target = self.packages_dir / f"{normalized_slug}.anyzorkpkg"
        package_target.write_bytes(package_path.read_bytes())

        now = datetime.now(UTC).isoformat()
        created_at = existing.created_at if existing else now
        if genres is None:
            cleaned_genres = [
                str(genre).strip()
                for genre in listing_meta.get("genres", [])
                if str(genre).strip()
            ]
        else:
            cleaned_genres = [genre.strip() for genre in genres if genre.strip()]

        row = UploadedGame(
            slug=normalized_slug,
            title=normalized_title,
            author=(author or str(listing_meta.get("author") or "")).strip(),
            description=(
                description
                or str(listing_meta.get("description") or "")
                or str(game_meta.get("intro_text") or "")
            ).strip(),
            tagline=(tagline or str(listing_meta.get("tagline") or "")).strip(),
            genres=cleaned_genres,
            package_path=str(package_target),
            package_url=f"/api/games/{normalized_slug}/package",
            download_url=f"/api/games/{normalized_slug}/package",
            checksum_sha256=_sha256_file(package_target),
            runtime_compat_version=str(game_meta.get("runtime_compat_version") or ""),
            prompt_system_version=str(game_meta.get("prompt_system_version") or ""),
            room_count=int(game_meta.get("room_count") or 0),
            region_count=int(game_meta.get("region_count") or 0),
            homepage_url=(homepage_url or str(listing_meta.get("homepage_url") or "")).strip(),
            cover_image_url=(
                cover_image_url or str(listing_meta.get("cover_image_url") or "")
            ).strip(),
            created_at=created_at,
            updated_at=now,
            published=published,
        )
        self._write_game(row)
        return row

    def list_games(self, *, published_only: bool = True) -> list[UploadedGame]:
        """Return uploaded games ordered by newest first."""
        sql = "SELECT * FROM games"
        params: tuple[object, ...] = ()
        if published_only:
            sql += " WHERE published = 1"
        sql += " ORDER BY updated_at DESC, slug ASC"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_game(row) for row in rows]

    def get_game(self, slug: str) -> UploadedGame | None:
        """Return one uploaded game by slug."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM games WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            return None
        return self._row_to_game(row)

    def build_catalog(self) -> dict[str, object]:
        """Return the public catalog JSON contract."""
        published_games = self.list_games(published_only=True)
        games = []
        for game in published_games:
            games.append(
                {
                    "slug": game.slug,
                    "title": game.title,
                    "author": game.author,
                    "description": game.description,
                    "tagline": game.tagline,
                    "genres": game.genres,
                    "featured": False,
                    "cover_image_url": game.cover_image_url,
                    "homepage_url": game.homepage_url,
                    "package_url": game.package_url,
                    "runtime_compat_version": game.runtime_compat_version,
                    "prompt_system_version": game.prompt_system_version,
                    "room_count": game.room_count,
                    "region_count": game.region_count,
                }
            )

        latest_update = max((game.updated_at for game in published_games), default="")
        return {
            "format": PUBLIC_CATALOG_FORMAT,
            "title": "Published AnyZork Games",
            "updated_at": latest_update,
            "games": games,
        }

    def set_published(self, slug: str, *, published: bool) -> None:
        """Set the published flag for a game."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE games SET published = ?, updated_at = ? WHERE slug = ?",
                (1 if published else 0, datetime.now(UTC).isoformat(), slug),
            )
            conn.commit()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS games (
                    slug TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    author TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    tagline TEXT NOT NULL DEFAULT '',
                    genres_json TEXT NOT NULL DEFAULT '[]',
                    package_path TEXT NOT NULL,
                    package_url TEXT NOT NULL,
                    download_url TEXT NOT NULL,
                    checksum_sha256 TEXT NOT NULL,
                    runtime_compat_version TEXT NOT NULL DEFAULT '',
                    prompt_system_version TEXT NOT NULL DEFAULT '',
                    room_count INTEGER NOT NULL DEFAULT 0,
                    region_count INTEGER NOT NULL DEFAULT 0,
                    homepage_url TEXT NOT NULL DEFAULT '',
                    cover_image_url TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    published INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()

    def _write_game(self, game: UploadedGame) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO games (
                    slug, title, author, description, tagline, genres_json, package_path,
                    package_url, download_url, checksum_sha256,
                    runtime_compat_version, prompt_system_version,
                    room_count, region_count, homepage_url, cover_image_url,
                    created_at, updated_at, published
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                    title = excluded.title,
                    author = excluded.author,
                    description = excluded.description,
                    tagline = excluded.tagline,
                    genres_json = excluded.genres_json,
                    package_path = excluded.package_path,
                    package_url = excluded.package_url,
                    download_url = excluded.download_url,
                    checksum_sha256 = excluded.checksum_sha256,
                    runtime_compat_version = excluded.runtime_compat_version,
                    prompt_system_version = excluded.prompt_system_version,
                    room_count = excluded.room_count,
                    region_count = excluded.region_count,
                    homepage_url = excluded.homepage_url,
                    cover_image_url = excluded.cover_image_url,
                    updated_at = excluded.updated_at,
                    published = games.published
                """,
                (
                    game.slug,
                    game.title,
                    game.author,
                    game.description,
                    game.tagline,
                    json.dumps(game.genres),
                    game.package_path,
                    game.package_url,
                    game.download_url,
                    game.checksum_sha256,
                    game.runtime_compat_version,
                    game.prompt_system_version,
                    game.room_count,
                    game.region_count,
                    game.homepage_url,
                    game.cover_image_url,
                    game.created_at,
                    game.updated_at,
                    1 if game.published else 0,
                ),
            )
            conn.commit()

    def _row_to_game(self, row: sqlite3.Row) -> UploadedGame:
        return UploadedGame(
            slug=str(row["slug"]),
            title=str(row["title"]),
            author=str(row["author"]),
            description=str(row["description"]),
            tagline=str(row["tagline"]),
            genres=[str(genre) for genre in json.loads(row["genres_json"])],
            package_path=str(row["package_path"]),
            package_url=str(row["package_url"]),
            download_url=str(row["download_url"]),
            checksum_sha256=str(row["checksum_sha256"]),
            runtime_compat_version=str(row["runtime_compat_version"]),
            prompt_system_version=str(row["prompt_system_version"]),
            room_count=int(row["room_count"]),
            region_count=int(row["region_count"]),
            homepage_url=str(row["homepage_url"]),
            cover_image_url=str(row["cover_image_url"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            published=bool(row["published"]),
        )


def _read_manifest_from_package(package_path: Path) -> dict[str, object]:
    """Read and validate the manifest from a share package."""
    if package_path.suffix != ".anyzorkpkg":
        raise SharePackageError("Uploads must be .anyzorkpkg files.")

    import tempfile

    with tempfile.TemporaryDirectory(prefix="anyzork-catalog-") as tmp:
        manifest, _game_path = _extract_share_package(package_path, Path(tmp))
    return manifest
