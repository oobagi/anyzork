"""Persistent storage for uploaded public AnyZork game packages."""

from __future__ import annotations

import hmac
import json
import logging
import re
import sqlite3
import typing
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from anyzork.sharing import (
    PUBLIC_CATALOG_FORMAT,
    SharePackageError,
    _extract_share_package,
    _sha256_file,
    _slugify_name,
)

logger = logging.getLogger(__name__)


VALID_STATUSES = {"pending", "approved", "rejected", "unpublished"}


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
    homepage_url: str
    cover_image_url: str
    created_at: str
    updated_at: str
    published: bool
    email_hash: str = ""
    status: str = "pending"
    review_notes: str = ""
    featured: bool = False

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
            "homepage_url": self.homepage_url,
            "cover_image_url": self.cover_image_url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "published": self.published,
            "status": self.status,
            "review_notes": self.review_notes,
            "featured": self.featured,
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
        email_hash: str | None = None,
    ) -> UploadedGame:
        """Validate and store an uploaded ``.zork`` share package."""
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

        package_target = self.packages_dir / f"{normalized_slug}.zork"
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
            homepage_url=(homepage_url or str(listing_meta.get("homepage_url") or "")).strip(),
            cover_image_url=(
                cover_image_url or str(listing_meta.get("cover_image_url") or "")
            ).strip(),
            created_at=created_at,
            updated_at=now,
            published=published,
            email_hash=email_hash or (existing.email_hash if existing else ""),
            status="approved" if published else "pending",
        )
        self._write_game(row)
        return row

    def list_games(
        self,
        *,
        published_only: bool = True,
        status: str | None = None,
    ) -> list[UploadedGame]:
        """Return uploaded games ordered by newest first.

        When *status* is given, filter by that moderation status instead
        of the published flag.
        """
        sql = "SELECT * FROM games"
        params: list[object] = []
        conditions: list[str] = []
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        elif published_only:
            conditions.append("status = 'approved'")
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY updated_at DESC, slug ASC"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, tuple(params)).fetchall()
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
                    "featured": game.featured,
                    "cover_image_url": game.cover_image_url,
                    "homepage_url": game.homepage_url,
                    "package_url": game.package_url,
                    "runtime_compat_version": game.runtime_compat_version,
                    "prompt_system_version": game.prompt_system_version,
                    "room_count": game.room_count,
                }
            )

        latest_update = max((game.updated_at for game in published_games), default="")
        return {
            "format": PUBLIC_CATALOG_FORMAT,
            "title": "Published AnyZork Games",
            "updated_at": latest_update,
            "games": games,
        }

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def create_auth_code(
        self, email_hash: str, code_hash: str, expires_at: str,
    ) -> None:
        """Insert a new OTP auth code.

        Deletes expired codes for this email first to prevent
        accumulation while preserving recent codes needed for rate
        limiting.
        """
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM auth_codes "
                "WHERE email_hash = ? AND expires_at < ?",
                (email_hash, now),
            )
            conn.execute(
                "INSERT INTO auth_codes "
                "(email_hash, code_hash, expires_at, attempts, created_at) "
                "VALUES (?, ?, ?, 0, ?)",
                (email_hash, code_hash, expires_at, now),
            )
            conn.commit()

    def verify_auth_code(self, email_hash: str, code_hash: str) -> bool:
        """Validate an OTP code. Returns True on success.

        Increments attempts on each call. Deletes the code on success.
        Returns False when expired, wrong code, or attempts >= 5.
        """
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT rowid, * FROM auth_codes "
                "WHERE email_hash = ? ORDER BY created_at DESC LIMIT 1",
                (email_hash,),
            ).fetchone()
            if row is None:
                return False
            if row["attempts"] >= 5:
                conn.execute(
                    "DELETE FROM auth_codes WHERE rowid = ?",
                    (row["rowid"],),
                )
                conn.commit()
                return False
            if row["expires_at"] < now:
                conn.execute(
                    "DELETE FROM auth_codes WHERE rowid = ?",
                    (row["rowid"],),
                )
                conn.commit()
                return False
            conn.execute(
                "UPDATE auth_codes SET attempts = attempts + 1 "
                "WHERE rowid = ?",
                (row["rowid"],),
            )
            conn.commit()
            if not hmac.compare_digest(row["code_hash"], code_hash):
                # Check if we just hit the limit.
                if row["attempts"] + 1 >= 5:
                    conn.execute(
                        "DELETE FROM auth_codes WHERE rowid = ?",
                        (row["rowid"],),
                    )
                    conn.commit()
                return False
            # Success — delete the code.
            conn.execute(
                "DELETE FROM auth_codes WHERE rowid = ?",
                (row["rowid"],),
            )
            conn.commit()
            return True

    def count_recent_codes(self, email_hash: str, since: str) -> int:
        """Count OTP codes created for this email since a timestamp."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM auth_codes "
                "WHERE email_hash = ? AND created_at >= ?",
                (email_hash, since),
            ).fetchone()
            return int(row[0]) if row else 0

    def create_session(
        self, token_hash: str, email_hash: str,
    ) -> None:
        """Insert a new session."""
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO sessions "
                "(token_hash, email_hash, created_at, last_used_at) "
                "VALUES (?, ?, ?, ?)",
                (token_hash, email_hash, now, now),
            )
            conn.commit()

    def validate_session(self, token_hash: str) -> str | None:
        """Return email_hash if session is valid, else None.

        Sessions unused for more than 30 days or older than 90 days
        are treated as expired and deleted.  Updates last_used_at on
        success.
        """
        now = datetime.now(UTC)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM sessions WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None

            last_used = datetime.fromisoformat(row["last_used_at"])
            created = datetime.fromisoformat(row["created_at"])

            if now - last_used > timedelta(days=30) or now - created > timedelta(days=90):
                conn.execute(
                    "DELETE FROM sessions WHERE token_hash = ?",
                    (token_hash,),
                )
                conn.commit()
                return None

            conn.execute(
                "UPDATE sessions SET last_used_at = ? "
                "WHERE token_hash = ?",
                (now.isoformat(), token_hash),
            )
            conn.commit()
            return str(row["email_hash"])

    def delete_session(self, token_hash: str) -> None:
        """Delete a session (logout)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM sessions WHERE token_hash = ?",
                (token_hash,),
            )
            conn.commit()

    def list_games_by_email(
        self, email_hash: str,
    ) -> list[UploadedGame]:
        """Return all games owned by the given email_hash."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM games WHERE email_hash = ? "
                "ORDER BY updated_at DESC, slug ASC",
                (email_hash,),
            ).fetchall()
        return [self._row_to_game(row) for row in rows]

    def delete_game(self, slug: str) -> None:
        """Delete a game record and its package file."""
        game = self.get_game(slug)
        if game is not None:
            package = Path(game.package_path)
            if package.exists():
                package.unlink(missing_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM games WHERE slug = ?", (slug,))
            conn.commit()

    # ------------------------------------------------------------------
    # Game file operations (read/list/write inside .zork packages)
    # ------------------------------------------------------------------

    _SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    _EDITABLE_EXTENSIONS: typing.ClassVar[set[str]] = {".toml", ".zorkscript"}

    @classmethod
    def _validate_filename(cls, filename: str) -> None:
        """Raise ValueError for unsafe filenames."""
        if not cls._SAFE_FILENAME_RE.match(filename):
            raise ValueError(
                f"Invalid filename: {filename!r}. "
                "Only alphanumeric, dots, hyphens, and underscores are allowed."
            )
        # Extra guard against path traversal.
        if ".." in filename or "/" in filename or "\\" in filename:
            raise ValueError(f"Path traversal detected in filename: {filename!r}")

    def list_game_files(self, slug: str) -> list[dict[str, object]]:
        """Return a list of files inside a game's .zork package."""
        game = self.get_game(slug)
        if game is None:
            return []
        package_path = Path(game.package_path)
        if not package_path.exists() or not zipfile.is_zipfile(package_path):
            return []
        files: list[dict[str, object]] = []
        with zipfile.ZipFile(package_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                try:
                    self._validate_filename(info.filename)
                except ValueError:
                    continue  # skip entries with paths/unusual names
                ext = Path(info.filename).suffix
                files.append({
                    "filename": info.filename,
                    "size": info.file_size,
                    "editable": ext in self._EDITABLE_EXTENSIONS,
                })
        return files

    def read_game_file(self, slug: str, filename: str) -> str | None:
        """Read a text file from a game's .zork package. Returns None if not found."""
        self._validate_filename(filename)
        game = self.get_game(slug)
        if game is None:
            return None
        package_path = Path(game.package_path)
        if not package_path.exists() or not zipfile.is_zipfile(package_path):
            return None
        try:
            with zipfile.ZipFile(package_path) as zf:
                return zf.read(filename).decode("utf-8")
        except (KeyError, UnicodeDecodeError):
            return None

    def write_game_file(self, slug: str, filename: str, content: str) -> bool:
        """Write a text file into a game's .zork package. Returns True on success."""
        self._validate_filename(filename)
        ext = Path(filename).suffix
        if ext not in self._EDITABLE_EXTENSIONS:
            raise ValueError(
                f"Cannot edit files with extension {ext!r}. "
                f"Allowed: {', '.join(sorted(self._EDITABLE_EXTENSIONS))}"
            )
        game = self.get_game(slug)
        if game is None:
            return False
        package_path = Path(game.package_path)
        if not package_path.exists() or not zipfile.is_zipfile(package_path):
            return False

        # Read all existing entries, then rewrite the archive.
        entries: list[tuple[zipfile.ZipInfo, bytes]] = []
        found = False
        with zipfile.ZipFile(package_path) as zf:
            for info in zf.infolist():
                if info.filename == filename:
                    entries.append((info, content.encode("utf-8")))
                    found = True
                else:
                    entries.append((info, zf.read(info.filename)))

        if not found:
            # Add as new entry.
            new_info = zipfile.ZipInfo(filename)
            entries.append((new_info, content.encode("utf-8")))

        tmp_path = package_path.with_suffix(".zork.tmp")
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for info, data in entries:
                zf.writestr(info, data)
        tmp_path.replace(package_path)  # atomic on POSIX

        # Update checksum and timestamp.
        now = datetime.now(UTC).isoformat()
        new_checksum = _sha256_file(package_path)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE games SET checksum_sha256 = ?, updated_at = ? WHERE slug = ?",
                (new_checksum, now, slug),
            )
            conn.commit()
        return True

    def update_game_metadata(
        self, slug: str, *, admin: bool = False, **fields: object,
    ) -> None:
        """Update allowed metadata fields, set updated_at, unpublish.

        Resets moderation status to ``pending`` so the game must be
        re-approved after edits.  When *admin* is True the current
        status is preserved (no reset to pending).
        """
        allowed = {
            "title", "author", "description", "tagline",
            "genres_json", "homepage_url", "cover_image_url",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        now = datetime.now(UTC).isoformat()
        updates["updated_at"] = now
        if not admin:
            updates["published"] = 0
            updates["status"] = "pending"
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = [*updates.values(), slug]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE games SET {set_clause} WHERE slug = ?",
                values,
            )
            conn.commit()

    def set_published(self, slug: str, *, published: bool) -> None:
        """Set the published flag for a game.

        Also syncs the moderation status: publishing sets status to
        ``approved``, unpublishing sets it to ``unpublished``.
        """
        status = "approved" if published else "unpublished"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE games SET published = ?, status = ?, updated_at = ? "
                "WHERE slug = ?",
                (
                    1 if published else 0,
                    status,
                    datetime.now(UTC).isoformat(),
                    slug,
                ),
            )
            conn.commit()

    def set_status(
        self, slug: str, *, status: str, review_notes: str = "",
    ) -> None:
        """Set the moderation status for a game.

        Automatically syncs the ``published`` boolean: only ``approved``
        games are considered published.
        """
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status {status!r}. "
                f"Must be one of: {', '.join(sorted(VALID_STATUSES))}"
            )
        published = 1 if status == "approved" else 0
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE games SET status = ?, review_notes = ?, "
                "published = ?, updated_at = ? WHERE slug = ?",
                (
                    status,
                    review_notes,
                    published,
                    datetime.now(UTC).isoformat(),
                    slug,
                ),
            )
            conn.commit()

    def set_featured(self, slug: str, *, featured: bool) -> None:
        """Toggle the featured flag for a game."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE games SET featured = ?, updated_at = ? WHERE slug = ?",
                (1 if featured else 0, datetime.now(UTC).isoformat(), slug),
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
                    homepage_url TEXT NOT NULL DEFAULT '',
                    cover_image_url TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    published INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            # Migrate: add columns if missing.
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(games)").fetchall()
            }
            if "email_hash" not in columns:
                conn.execute(
                    "ALTER TABLE games ADD COLUMN email_hash TEXT NOT NULL DEFAULT ''"
                )
            if "status" not in columns:
                conn.execute(
                    "ALTER TABLE games ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'"
                )
                # Backfill: published games become 'approved'.
                conn.execute(
                    "UPDATE games SET status = 'approved' WHERE published = 1"
                )
            if "review_notes" not in columns:
                conn.execute(
                    "ALTER TABLE games ADD COLUMN review_notes TEXT NOT NULL DEFAULT ''"
                )
            if "featured" not in columns:
                conn.execute(
                    "ALTER TABLE games ADD COLUMN featured INTEGER NOT NULL DEFAULT 0"
                )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_codes (
                    email_hash TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    email_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _write_game(self, game: UploadedGame) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO games (
                    slug, title, author, description, tagline,
                    genres_json, package_path, package_url,
                    download_url, checksum_sha256,
                    runtime_compat_version, prompt_system_version,
                    room_count, homepage_url, cover_image_url,
                    created_at, updated_at, published, email_hash,
                    status, review_notes, featured
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?
                )
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
                    homepage_url = excluded.homepage_url,
                    cover_image_url = excluded.cover_image_url,
                    updated_at = excluded.updated_at,
                    published = games.published,
                    status = games.status,
                    email_hash = CASE WHEN excluded.email_hash != ''
                        THEN excluded.email_hash ELSE games.email_hash END
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
                    game.homepage_url,
                    game.cover_image_url,
                    game.created_at,
                    game.updated_at,
                    1 if game.published else 0,
                    game.email_hash,
                    game.status,
                    game.review_notes,
                    1 if game.featured else 0,
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
            homepage_url=str(row["homepage_url"]),
            cover_image_url=str(row["cover_image_url"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            published=bool(row["published"]),
            email_hash=str(row["email_hash"]),
            status=str(row["status"]),
            review_notes=str(row["review_notes"]),
            featured=bool(row["featured"]),
        )


def _read_manifest_from_package(package_path: Path) -> dict[str, object]:
    """Read and validate the manifest from a share package (.zork archive)."""
    import tempfile
    import zipfile

    if not zipfile.is_zipfile(package_path):
        raise SharePackageError("Uploads must be .zork archive files.")

    with tempfile.TemporaryDirectory(prefix="anyzork-catalog-") as tmp:
        manifest, _game_path = _extract_share_package(package_path, Path(tmp))
    return manifest
