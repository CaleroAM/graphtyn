"""Recent agent queries for the dashboard, read from the project's history database."""
from pathlib import Path

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import JSONResponse

from ..core.history import HistoryTracker
from ..core.query_log import RETENTION_DAYS, logging_enabled, prune_queries, recent_queries, set_logging, usage_summary

router = APIRouter()
SUMMARY_DAYS = 7
SUMMARY_LIMIT = 2000


def _project(path: str) -> Path | None:
    root = Path(path).expanduser().resolve()
    return root if root.is_dir() else None


def _missing_project() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "El proyecto no existe"}, status_code=404)


@router.get("/api/agent-activity")
def agent_activity(path: str = Query(..., min_length=1), limit: int = Query(30, ge=1, le=100)):
    root = _project(path)
    if root is None:
        return _missing_project()
    tracker = HistoryTracker(root)
    prune_queries(tracker)
    queries = recent_queries(tracker, SUMMARY_LIMIT)
    return {"ok": True, "queries": queries[:limit], "usage": usage_summary(queries, SUMMARY_DAYS),
            "logging": logging_enabled(tracker), "retention_days": RETENTION_DAYS}


@router.post("/api/agent-activity/settings")
def agent_activity_settings(payload: dict = Body(...), authorization: str | None = Header(default=None)):
    from .main import _memory_auth

    path = str(payload.get("path") or "")
    root = _project(path) if path else None
    if root is None:
        return _missing_project()
    denied = _memory_auth(authorization, str(root), "writer")
    if denied:
        return denied
    if not isinstance(payload.get("logging"), bool):
        return JSONResponse({"ok": False, "error": "logging debe ser verdadero o falso"}, status_code=422)
    tracker = HistoryTracker(root)
    set_logging(tracker, payload["logging"])
    return {"ok": True, "logging": logging_enabled(tracker)}
