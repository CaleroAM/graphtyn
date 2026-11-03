"""Service status for the dashboard and the token settings shared by the API guards."""
import os

from fastapi import APIRouter

from .. import __version__

router = APIRouter()


def scoped_tokens_configured() -> bool:
    return bool(os.environ.get("GRAPHTYN_MEMORY_TOKENS") or os.environ.get("GRAPHTYN_MEMORY_TOKENS_FILE"))


def memory_auth_configured() -> bool:
    return bool(os.environ.get("GRAPHTYN_MEMORY_HTTP_TOKEN")) or scoped_tokens_configured()


def mcp_http_enabled() -> bool:
    return bool(os.environ.get("GRAPHTYN_MCP_TOKEN")) or scoped_tokens_configured()


@router.get("/api/service")
def service_status():
    """What this server can vouch for: it answers, and whether its HTTP /mcp accepts clients.

    Clients that launch `graphtyn mcp` over stdio run in their own process and do not depend on it.
    """
    return {"ok": True, "version": __version__, "mcp_http": mcp_http_enabled()}
