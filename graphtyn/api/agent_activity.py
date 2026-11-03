"""Recent agent queries for the dashboard, read from the project's history database."""
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ..core.history import HistoryTracker
from ..core.query_log import recent_queries, usage_summary

router = APIRouter()
SUMMARY_DAYS = 7
SUMMARY_LIMIT = 2000


@router.get("/api/agent-activity")
def agent_activity(path: str = Query(..., min_length=1), limit: int = Query(30, ge=1, le=100)):
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        return JSONResponse({"ok": False, "error": "El proyecto no existe"}, status_code=404)
    queries = recent_queries(HistoryTracker(root), SUMMARY_LIMIT, SUMMARY_DAYS)
    return {"ok": True, "queries": queries[:limit], "usage": usage_summary(queries, SUMMARY_DAYS)}
