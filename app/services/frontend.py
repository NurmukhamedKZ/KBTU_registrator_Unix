from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"


def mount_frontend_assets(app: FastAPI):
    if FRONTEND_ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS_DIR), name="frontend-assets")


def frontend_index_path() -> Path:
    return FRONTEND_DIST_DIR / "index.html"


def serve_frontend_index() -> FileResponse:
    """Serve SPA entrypoint with no-cache headers to avoid stale asset hashes."""
    return FileResponse(
        frontend_index_path(),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


def ensure_frontend_built_or_503():
    index_path = frontend_index_path()
    if not index_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend build not found. Run: cd frontend && npm install && npm run build",
        )
