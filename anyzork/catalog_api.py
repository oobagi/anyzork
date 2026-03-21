"""FastAPI app for public AnyZork uploads and browsing."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from anyzork.catalog_store import CatalogStore
from anyzork.config import Config
from anyzork.sharing import SharePackageError

_UPLOAD_FILENAME = "submission.anyzorkpkg"


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

    @app.get("/")
    def index() -> dict[str, object]:
        return {
            "name": "AnyZork Catalog API",
            "catalog_url": "/catalog.json",
            "upload_url": "/api/games",
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
            "games": [game.to_api_dict() for game in store.list_games(published_only=True)],
        }

    @app.get("/api/games/{slug}")
    def get_game(slug: str) -> dict[str, object]:
        game = store.get_game(slug)
        if game is None or not game.published:
            raise HTTPException(status_code=404, detail="Game not found.")
        return game.to_api_dict()

    @app.get("/api/games/{slug}/package")
    def download_game(slug: str) -> FileResponse:
        game = store.get_game(slug)
        if game is None or not game.published:
            raise HTTPException(status_code=404, detail="Game not found.")
        return FileResponse(
            game.package_path,
            media_type="application/octet-stream",
            filename=f"{slug}.anyzorkpkg",
        )

    @app.post("/api/games")
    async def upload_game(
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
            raise HTTPException(status_code=400, detail="Upload is missing a filename.")

        genre_values = None
        if genres:
            genre_values = [value.strip() for value in genres.split(",") if value.strip()]

        with tempfile.TemporaryDirectory(prefix="anyzork-upload-") as tmp:
            temp_path = Path(tmp) / f"{uuid4().hex}-{_UPLOAD_FILENAME}"
            with temp_path.open("wb") as handle:
                shutil.copyfileobj(package.file, handle)

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
                )
            except SharePackageError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        return JSONResponse(
            status_code=201,
            content={
                "game": saved.to_api_dict(),
                "catalog": store.build_catalog(),
            },
        )

    def _require_admin_token(x_admin_token: str | None) -> None:
        expected = os.environ.get("ANYZORK_ADMIN_TOKEN", "")
        if not expected or x_admin_token != expected:
            raise HTTPException(status_code=403, detail="Invalid or missing admin token.")

    @app.get("/api/admin/games")
    def admin_list_games(
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        return {
            "games": [game.to_api_dict() for game in store.list_games(published_only=False)],
        }

    @app.post("/api/admin/games/{slug}/publish")
    def admin_publish_game(
        slug: str,
        x_admin_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _require_admin_token(x_admin_token)
        game = store.get_game(slug)
        if game is None:
            raise HTTPException(status_code=404, detail="Game not found.")
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
            raise HTTPException(status_code=404, detail="Game not found.")
        store.set_published(slug, published=False)
        return {"game": store.get_game(slug).to_api_dict()}

    return app
