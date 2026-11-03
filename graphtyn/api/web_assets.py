"""Dashboard pages, stylesheets and scripts served from the package's web/ folder."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, Response

WEB = Path(__file__).resolve().parent.parent / "web"
NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
router = APIRouter()


def _script(folder: Path, file: str, suffix: str) -> Path | None:
    if not file.endswith(suffix) or "/" in file or "\\" in file or ".." in file:
        return None
    path = folder / file
    return path if path.is_file() else None


@router.get("/comparison")
def model_comparison():
    return HTMLResponse(content=(WEB / "comparison.html").read_text(encoding="utf-8"))


@router.get("/favicon.svg")
def favicon():
    return Response(content=(WEB / "favicon.svg").read_text(encoding="utf-8"), media_type="image/svg+xml")


@router.get("/")
def index():
    return HTMLResponse(content=(WEB / "dashboard.html").read_text(encoding="utf-8"), headers=NO_CACHE)


@router.get("/dashboard.css")
def dashboard_css():
    return HTMLResponse(content=(WEB / "dashboard.css").read_text(encoding="utf-8"), media_type="text/css",
                        headers=NO_CACHE)


@router.get("/dashboard.js")
def dashboard_js():
    return HTMLResponse(content=(WEB / "dashboard.js").read_text(encoding="utf-8"),
                        media_type="application/javascript", headers=NO_CACHE)


@router.get("/vendor/{file}")
def vendor_script(file: str):
    # Bundled third-party builds carry their version in the name, so they are immutable.
    path = _script(WEB / "vendor", file, ".min.js")
    if path is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return Response(content=path.read_bytes(), media_type="application/javascript",
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


@router.get("/js/{file}")
def js_module(file: str):
    path = _script(WEB / "js", file, ".js")
    if path is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return HTMLResponse(content=path.read_text(encoding="utf-8"), media_type="application/javascript",
                        headers=NO_CACHE)
