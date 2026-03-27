"""FastAPI app for public AnyZork uploads and browsing."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from anyzork.catalog_store import CatalogStore
from anyzork.config import Config
from anyzork.sharing import SharePackageError

logger = logging.getLogger(__name__)

_UPLOAD_FILENAME = "submission.zork"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


class LoginRequest(BaseModel):
    email: str


class VerifyRequest(BaseModel):
    email: str
    code: str


def _send_otp_email(email: str, code: str) -> bool:
    """Send an OTP code via Resend. Falls back to logging if no key.

    Returns True if the email was sent (or logged), False on failure.
    """
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        logger.warning(
            "RESEND_API_KEY not set — OTP code for %s: %s", email, code,
        )
        return True
    import httpx

    try:
        httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": os.environ.get(
                    "ANYZORK_EMAIL_FROM", "AnyZork <noreply@anyzork.com>",
                ),
                "to": [email],
                "subject": "Your AnyZork login code",
                "text": (
                    f"Your login code is: {code}\n\n"
                    "This code expires in 10 minutes."
                ),
            },
        )
    except Exception:
        logger.exception("Failed to send OTP email to %s", email)
        return False
    return True


def _hash(value: str) -> str:
    """Return a SHA-256 hex digest."""
    return hashlib.sha256(value.encode()).hexdigest()


def _get_session_email_hash(
    request: Request, store: CatalogStore,
) -> str:
    """Extract and validate Bearer token. Returns email_hash."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid authorization.",
        )
    token = auth[7:]
    token_hash = _hash(token)
    email_hash = store.validate_session(token_hash)
    if email_hash is None:
        raise HTTPException(
            status_code=401, detail="Invalid or expired session.",
        )
    return email_hash


def create_catalog_app(*, root_dir: Path | None = None) -> FastAPI:
    """Create the upload/catalog API app."""
    cfg = Config()
    store = CatalogStore(root_dir or cfg.public_catalog_dir)
    app = FastAPI(title="AnyZork Catalog")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/admin", response_class=HTMLResponse)
    def admin_dashboard() -> HTMLResponse:
        admin_path = Path(__file__).parent / "static" / "admin.html"
        return HTMLResponse(admin_path.read_text())

    @app.get("/", response_class=HTMLResponse)
    def landing_page() -> HTMLResponse:
        index_path = Path(__file__).parent / "static" / "index.html"
        return HTMLResponse(index_path.read_text())

    @app.get("/api")
    def api_index() -> dict[str, object]:
        return {
            "name": "AnyZork Catalog API",
            "catalog_url": "/catalog.json",
            "games_url": "/api/games",
        }

    @app.get("/healthz")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/catalog.json")
    def public_catalog() -> dict[str, object]:
        return store.build_catalog()

    @app.get("/api/games")
    def list_games() -> dict[str, object]:
        return {
            "games": [
                game.to_api_dict()
                for game in store.list_games(published_only=True)
            ],
        }

    @app.get("/api/games/{slug}")
    def get_game(slug: str) -> dict[str, object]:
        game = store.get_game(slug)
        if game is None or game.status != "approved":
            raise HTTPException(
                status_code=404, detail="Game not found.",
            )
        return game.to_api_dict()

    @app.get("/api/games/{slug}/status")
    def game_status(slug: str) -> dict[str, object]:
        game = store.get_game(slug)
        if game is None:
            raise HTTPException(
                status_code=404, detail="Game not found.",
            )
        return {
            "slug": game.slug,
            "title": game.title,
            "published": game.published,
            "status": game.status,
        }

    @app.get("/api/games/{slug}/package")
    def download_game(slug: str) -> FileResponse:
        game = store.get_game(slug)
        if game is None or game.status != "approved":
            raise HTTPException(
                status_code=404, detail="Game not found.",
            )
        return FileResponse(
            game.package_path,
            media_type="application/octet-stream",
            filename=f"{slug}.zork",
        )

    @app.post("/api/games")
    async def upload_game(
        request: Request,
        package: Annotated[UploadFile, File(...)],
        title: Annotated[str | None, Form()] = None,
        author: Annotated[str | None, Form()] = None,
        description: Annotated[str | None, Form()] = None,
        tagline: Annotated[str | None, Form()] = None,
        genres: Annotated[str | None, Form()] = None,
        slug: Annotated[str | None, Form()] = None,
        homepage_url: Annotated[str | None, Form()] = None,
        cover_image_url: Annotated[str | None, Form()] = None,
    ) -> JSONResponse:
        if not package.filename:
            raise HTTPException(
                status_code=400,
                detail="Upload is missing a filename.",
            )

        if package.size is not None and package.size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Upload exceeds 50 MB limit.",
            )

        # Optional auth — store email_hash if session present.
        email_hash: str | None = None
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            token_hash = _hash(token)
            email_hash = store.validate_session(token_hash)

        genre_values = None
        if genres:
            genre_values = [
                value.strip()
                for value in genres.split(",")
                if value.strip()
            ]

        with tempfile.TemporaryDirectory(prefix="anyzork-upload-") as tmp:
            temp_path = (
                Path(tmp) / f"{uuid4().hex}-{_UPLOAD_FILENAME}"
            )
            with temp_path.open("wb") as handle:
                shutil.copyfileobj(package.file, handle)

            if temp_path.stat().st_size > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="Upload exceeds 50 MB limit.",
                )

            try:
                saved = store.upsert_package(
                    temp_path,
                    title=title,
                    author=author,
                    description=description,
                    tagline=tagline,
                    genres=genre_values,
                    slug=slug,
                    homepage_url=homepage_url,
                    cover_image_url=cover_image_url,
                    published=False,
                    email_hash=email_hash,
                )
            except SharePackageError as exc:
                raise HTTPException(
                    status_code=400, detail=str(exc),
                ) from exc

        return JSONResponse(
            status_code=201,
            content={
                "game": saved.to_api_dict(),
                "catalog": store.build_catalog(),
            },
        )

    # ------------------------------------------------------------------
    # Auth endpoints
    # ------------------------------------------------------------------

    @app.post("/api/auth/login")
    def auth_login(body: LoginRequest) -> dict[str, object]:
        email = body.email.strip().lower()
        # Basic email format check.
        if (
            email.count("@") != 1
            or not email.split("@")[0]
            or "." not in email.split("@")[1]
            or not email.split("@")[1].split(".")[0]
        ):
            raise HTTPException(
                status_code=422,
                detail="Invalid email address",
            )
        email_hash = _hash(email)
        since = (
            datetime.now(UTC) - timedelta(hours=1)
        ).isoformat()
        if store.count_recent_codes(email_hash, since) >= 3:
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts. Try again later.",
            )
        code = f"{secrets.randbelow(900000) + 100000}"
        code_hash = _hash(code)
        expires_at = (
            datetime.now(UTC) + timedelta(minutes=10)
        ).isoformat()
        store.create_auth_code(email_hash, code_hash, expires_at)
        if not _send_otp_email(email, code):
            raise HTTPException(
                status_code=502,
                detail="Failed to send verification email",
            )
        return {"message": "Code sent.", "email": email}

    @app.post("/api/auth/verify")
    def auth_verify(body: VerifyRequest) -> dict[str, object]:
        email = body.email.strip().lower()
        email_hash = _hash(email)
        code_hash = _hash(body.code.strip())
        if not store.verify_auth_code(email_hash, code_hash):
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired code.",
            )
        token = secrets.token_urlsafe(32)
        token_hash = _hash(token)
        store.create_session(token_hash, email_hash)
        return {
            "session_token": token,
            "email": email,
        }

    @app.post("/api/auth/logout")
    def auth_logout(request: Request) -> dict[str, object]:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid authorization.",
            )
        token = auth[7:]
        token_hash = _hash(token)
        store.delete_session(token_hash)
        return {"message": "Logged out."}

    # ------------------------------------------------------------------
    # Publisher self-service endpoints
    # ------------------------------------------------------------------

    @app.get("/api/my/games")
    def my_games(request: Request) -> dict[str, object]:
        email_hash = _get_session_email_hash(request, store)
        games = store.list_games_by_email(email_hash)
        return {
            "games": [game.to_api_dict() for game in games],
        }

    @app.put("/api/games/{slug}")
    async def update_game(
        slug: str,
        request: Request,
        package: Annotated[UploadFile | None, File()] = None,
        title: Annotated[str | None, Form()] = None,
        author: Annotated[str | None, Form()] = None,
        description: Annotated[str | None, Form()] = None,
        tagline: Annotated[str | None, Form()] = None,
        genres: Annotated[str | None, Form()] = None,
        homepage_url: Annotated[str | None, Form()] = None,
        cover_image_url: Annotated[str | None, Form()] = None,
    ) -> dict[str, object]:
        email_hash = _get_session_email_hash(request, store)
        game = store.get_game(slug)
        if game is None:
            raise HTTPException(
                status_code=404, detail="Game not found.",
            )
        if game.email_hash != email_hash:
            raise HTTPException(
                status_code=403,
                detail="You do not own this game.",
            )

        # Update metadata fields.
        meta_updates: dict[str, object] = {}
        if title is not None:
            meta_updates["title"] = title.strip()
        if author is not None:
            meta_updates["author"] = author.strip()
        if description is not None:
            meta_updates["description"] = description.strip()
        if tagline is not None:
            meta_updates["tagline"] = tagline.strip()
        if genres is not None:
            meta_updates["genres_json"] = json.dumps(
                [v.strip() for v in genres.split(",") if v.strip()]
            )
        if homepage_url is not None:
            meta_updates["homepage_url"] = homepage_url.strip()
        if cover_image_url is not None:
            meta_updates["cover_image_url"] = cover_image_url.strip()

        # Re-upload package if provided.
        if package is not None and package.filename:
            with tempfile.TemporaryDirectory(
                prefix="anyzork-update-",
            ) as tmp:
                temp_path = (
                    Path(tmp) / f"{uuid4().hex}-{_UPLOAD_FILENAME}"
                )
                with temp_path.open("wb") as handle:
                    shutil.copyfileobj(package.file, handle)
                try:
                    store.upsert_package(
                        temp_path,
                        slug=slug,
                        published=False,
                        allow_replace=True,
                        email_hash=email_hash,
                    )
                except SharePackageError as exc:
                    raise HTTPException(
                        status_code=400, detail=str(exc),
                    ) from exc

        if meta_updates:
            store.update_game_metadata(slug, **meta_updates)

        updated = store.get_game(slug)
        return {"game": updated.to_api_dict()}

    @app.delete("/api/games/{slug}")
    def delete_game_endpoint(
        slug: str, request: Request,
    ) -> dict[str, object]:
        email_hash = _get_session_email_hash(request, store)
        game = store.get_game(slug)
        if game is None:
            raise HTTPException(
                status_code=404, detail="Game not found.",
            )
        if game.email_hash != email_hash:
            raise HTTPException(
                status_code=403,
                detail="You do not own this game.",
            )
        store.delete_game(slug)
        return {"message": f"Game '{slug}' deleted."}

    # ------------------------------------------------------------------
    # Admin endpoints
    # ------------------------------------------------------------------

    def _require_admin_token(x_admin_token: str | None) -> None:
        expected = os.environ.get("ANYZORK_ADMIN_TOKEN", "")
        if not expected or not hmac.compare_digest(
            x_admin_token or "", expected,
        ):
            raise HTTPException(
                status_code=403,
                detail="Invalid or missing admin token.",
            )

    @app.get("/api/admin/games")
    def admin_list_games(
        x_admin_token: Annotated[str | None, Header()] = None,
        status: str | None = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        return {
            "games": [
                game.to_api_dict()
                for game in store.list_games(
                    published_only=False, status=status,
                )
            ],
        }

    @app.post("/api/admin/games/bulk/approve")
    async def admin_bulk_approve(
        request: Request,
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        data = await request.json()
        slugs = data.get("slugs", [])
        review_notes = data.get("review_notes", "")
        results = []
        for slug in slugs:
            try:
                game = store.get_game(slug)
                if not game:
                    results.append(
                        {"slug": slug, "status": "error", "detail": "Not found"},
                    )
                    continue
                store.set_status(slug, status="approved", review_notes=review_notes)
                results.append({"slug": slug, "status": "ok"})
            except Exception as e:
                results.append(
                    {"slug": slug, "status": "error", "detail": str(e)},
                )
        return {"results": results}

    @app.post("/api/admin/games/bulk/reject")
    async def admin_bulk_reject(
        request: Request,
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        data = await request.json()
        slugs = data.get("slugs", [])
        review_notes = data.get("review_notes", "")
        results = []
        for slug in slugs:
            try:
                game = store.get_game(slug)
                if not game:
                    results.append(
                        {"slug": slug, "status": "error", "detail": "Not found"},
                    )
                    continue
                store.set_status(slug, status="rejected", review_notes=review_notes)
                results.append({"slug": slug, "status": "ok"})
            except Exception as e:
                results.append(
                    {"slug": slug, "status": "error", "detail": str(e)},
                )
        return {"results": results}

    @app.post("/api/admin/games/bulk/feature")
    async def admin_bulk_feature(
        request: Request,
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        data = await request.json()
        slugs = data.get("slugs", [])
        featured = bool(data.get("featured", True))
        results = []
        for slug in slugs:
            try:
                game = store.get_game(slug)
                if not game:
                    results.append(
                        {"slug": slug, "status": "error", "detail": "Not found"},
                    )
                    continue
                store.set_featured(slug, featured=featured)
                results.append({"slug": slug, "status": "ok"})
            except Exception as e:
                results.append(
                    {"slug": slug, "status": "error", "detail": str(e)},
                )
        return {"results": results}

    @app.post("/api/admin/games/bulk/delete")
    async def admin_bulk_delete(
        request: Request,
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        data = await request.json()
        slugs = data.get("slugs", [])
        results = []
        for slug in slugs:
            try:
                game = store.get_game(slug)
                if not game:
                    results.append(
                        {"slug": slug, "status": "error", "detail": "Not found"},
                    )
                    continue
                store.delete_game(slug)
                results.append({"slug": slug, "status": "ok"})
            except Exception as e:
                results.append(
                    {"slug": slug, "status": "error", "detail": str(e)},
                )
        return {"results": results}

    @app.post("/api/admin/games/{slug}/publish")
    def admin_publish_game(
        slug: str,
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        game = store.get_game(slug)
        if game is None:
            raise HTTPException(
                status_code=404, detail="Game not found.",
            )
        store.set_published(slug, published=True)
        return {"game": store.get_game(slug).to_api_dict()}

    @app.post("/api/admin/games/{slug}/unpublish")
    def admin_unpublish_game(
        slug: str,
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        game = store.get_game(slug)
        if game is None:
            raise HTTPException(
                status_code=404, detail="Game not found.",
            )
        store.set_published(slug, published=False)
        return {"game": store.get_game(slug).to_api_dict()}

    @app.post("/api/admin/games/{slug}/approve")
    def admin_approve_game(
        slug: str,
        x_admin_token: Annotated[str | None, Header()] = None,
        body: dict[str, str] | None = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        game = store.get_game(slug)
        if game is None:
            raise HTTPException(
                status_code=404, detail="Game not found.",
            )
        notes = (body or {}).get("review_notes", "")
        store.set_status(slug, status="approved", review_notes=notes)
        return {"game": store.get_game(slug).to_api_dict()}

    @app.post("/api/admin/games/{slug}/reject")
    def admin_reject_game(
        slug: str,
        x_admin_token: Annotated[str | None, Header()] = None,
        body: dict[str, str] | None = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        game = store.get_game(slug)
        if game is None:
            raise HTTPException(
                status_code=404, detail="Game not found.",
            )
        notes = (body or {}).get("review_notes", "")
        store.set_status(slug, status="rejected", review_notes=notes)
        return {"game": store.get_game(slug).to_api_dict()}

    @app.post("/api/admin/games/{slug}/feature")
    def admin_feature_game(
        slug: str,
        x_admin_token: Annotated[str | None, Header()] = None,
        body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        game = store.get_game(slug)
        if game is None:
            raise HTTPException(
                status_code=404, detail="Game not found.",
            )
        featured = bool((body or {}).get("featured", True))
        store.set_featured(slug, featured=featured)
        return {"game": store.get_game(slug).to_api_dict()}

    @app.delete("/api/admin/games/{slug}")
    def admin_delete_game(
        slug: str,
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        game = store.get_game(slug)
        if game is None:
            raise HTTPException(
                status_code=404, detail="Game not found.",
            )
        store.delete_game(slug)
        return {"message": f"Game '{slug}' deleted."}

    @app.patch("/api/admin/games/{slug}")
    async def admin_update_game_metadata(
        slug: str,
        request: Request,
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        game = store.get_game(slug)
        if game is None:
            raise HTTPException(
                status_code=404, detail="Game not found.",
            )
        data = await request.json()
        meta_updates: dict[str, object] = {}
        for field in (
            "title", "author", "description", "tagline",
            "homepage_url", "cover_image_url",
        ):
            if field in data:
                value = data[field]
                meta_updates[field] = value.strip() if isinstance(value, str) else value
        if "genres" in data:
            genres = data["genres"]
            if isinstance(genres, list):
                meta_updates["genres_json"] = json.dumps(
                    [g.strip() for g in genres if isinstance(g, str) and g.strip()]
                )
        if meta_updates:
            store.update_game_metadata(slug, admin=True, **meta_updates)
        updated = store.get_game(slug)
        return {"game": updated.to_api_dict()}

    @app.get("/api/admin/games/{slug}/files")
    def admin_list_game_files(
        slug: str,
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        game = store.get_game(slug)
        if game is None:
            raise HTTPException(
                status_code=404, detail="Game not found.",
            )
        return {"files": store.list_game_files(slug)}

    @app.get("/api/admin/games/{slug}/files/{filename}")
    def admin_read_game_file(
        slug: str,
        filename: str,
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        try:
            content = store.read_game_file(slug, filename)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        if content is None:
            raise HTTPException(
                status_code=404, detail="File not found.",
            )
        return {"filename": filename, "content": content}

    @app.put("/api/admin/games/{slug}/files/{filename}")
    def admin_write_game_file(
        slug: str,
        filename: str,
        request_body: dict[str, str],
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        content = request_body.get("content")
        if content is None:
            raise HTTPException(
                status_code=400,
                detail="Request body must include 'content'.",
            )
        try:
            success = store.write_game_file(slug, filename, content)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        if not success:
            raise HTTPException(
                status_code=404, detail="Game not found.",
            )
        return {"filename": filename, "message": "File updated."}

    # Mount static files last to avoid shadowing API routes
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

    return app
