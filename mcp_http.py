"""
MCP server — HTTP transport (Streamable HTTP).

Copied from agentanbud's proven mcp_http.py: JSON-RPC 2.0 over
POST /mcp, per-session ids via mcp-session-id header, CORS open,
key-gated write tools via X-Admin-Key (hmac.compare_digest).

Tool definitions and handlers live in mcp_server.py (the registry);
this module is transport only.

Mounted from app/main.py via:
    from mcp_http import mcp_router
    app.include_router(mcp_router)
"""
from __future__ import annotations

import hmac
import logging
import os
import time
import uuid

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.db import connect
import mcp_server

SERVER_NAME = "agenttable"
SERVER_VERSION = "0.1.0"

# Admin key gates the write tools (import_csv/upsert_rows/delete_dataset).
# When unset (local dev), everything is open — matching REST _require_admin.
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")

# Company data (KICKOFF/#15): set MCP_REQUIRE_KEY=true to gate READS too —
# tools/list and every tools/call then require X-Admin-Key. Use this when
# /mcp is excluded from Cloudflare Access so the agent can reach it.
# (CF Access Service Token validation is the alternative, decided in the
# CF dashboard; the app-side JWT check is future Sprint 4 work.)
MCP_REQUIRE_KEY = os.environ.get("MCP_REQUIRE_KEY", "").lower() in ("1", "true", "yes")


def _is_authed(request: Request) -> bool:
    if not ADMIN_API_KEY:
        return True
    return hmac.compare_digest(request.headers.get("x-admin-key", ""), ADMIN_API_KEY)


LOG = logging.getLogger(__name__)

# Per-process session store, keyed on the client-supplied mcp-session-id
# header (MCP spec for Streamable HTTP). Short-lived and stateless beyond TTL.
SESSIONS: dict[str, dict] = {}
SESSION_TTL_SECONDS = 3600


def _evict_expired_sessions() -> None:
    """Drop sessions older than SESSION_TTL_SECONDS. Cheap to call per request."""
    now = time.time()
    expired = [sid for sid, s in SESSIONS.items() if now - s["last_seen"] > SESSION_TTL_SECONDS]
    for sid in expired:
        SESSIONS.pop(sid, None)


def _tool_list(include_write: bool = False) -> list[dict]:
    """Read tools always; write tools only for authenticated callers."""
    tools = list(mcp_server.TOOLS)
    if include_write:
        tools += mcp_server.WRITE_TOOLS_DEF
    return tools


async def _dispatch_tool(name: str, arguments: dict, session_id: str | None = None) -> list:
    """Look up the handler in the registry and run it against a fresh conn."""
    handler = mcp_server.HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")
    conn = connect(mcp_server.DB_PATH)
    try:
        return await handler(conn, arguments or {})
    finally:
        conn.close()


# ----- FastAPI router -------------------------------------------------------

mcp_router = APIRouter()


def _cors_headers() -> dict:
    """CORS for browser-based MCP clients."""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, GET, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Accept, mcp-session-id, x-admin-key",
        "Access-Control-Max-Age": "86400",
    }


@mcp_router.options("/mcp")
async def mcp_options():
    """CORS preflight."""
    return Response(status_code=204, headers=_cors_headers())


@mcp_router.get("/mcp")
async def mcp_get(request: Request):
    """MCP server info — clients call this to discover capabilities."""
    _evict_expired_sessions()
    return JSONResponse({
        "name": SERVER_NAME,
        "version": SERVER_VERSION,
        "description": "AgentTable — CSV in, SQLite storage, MCP out. Minimal Airtable-like store for agents.",
        "transport": "streamable-http",
        "endpoint": "/mcp",
        "mcp_version": "2024-11-05",
        "tools_count": len(_tool_list()),
        "instructions": "POST JSON-RPC 2.0 to /mcp. Method 'tools/list' lists tools. Method 'tools/call' invokes one.",
    }, headers=_cors_headers())


@mcp_router.post("/mcp")
async def mcp_post(request: Request):
    """Handle JSON-RPC 2.0 MCP requests.

    Per MCP spec, the request body is a single JSON-RPC object (not batched).
    Responses follow JSON-RPC 2.0:
      - Success: { jsonrpc, id, result }
      - Error:   { jsonrpc, id, error: { code, message, data? } }
    """
    _evict_expired_sessions()

    # Get / create session
    session_id = request.headers.get("mcp-session-id")
    if not session_id:
        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = {"created": time.time(), "last_seen": time.time()}
    else:
        if session_id not in SESSIONS:
            SESSIONS[session_id] = {"created": time.time(), "last_seen": time.time()}
        SESSIONS[session_id]["last_seen"] = time.time()

    # Parse body
    try:
        body = await request.json()
    except Exception as exc:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {exc}"}},
            status_code=400,
            headers={**_cors_headers(), "mcp-session-id": session_id},
        )

    method = body.get("method")
    rpc_id = body.get("id")
    params = body.get("params") or {}

    # Route
    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "capabilities": {"tools": {"listChanged": False}},
            }
        elif method == "notifications/initialized":
            # Client→server notification, no response needed (ack with 204)
            return Response(status_code=204, headers={**_cors_headers(), "mcp-session-id": session_id})
        elif method == "ping":
            result = {}  # MCP keepalive
        elif method in ("tools/list", "tools/call") and MCP_REQUIRE_KEY and not _is_authed(request):
            return JSONResponse(
                {"jsonrpc": "2.0", "id": rpc_id,
                 "error": {"code": -32001,
                           "message": "This MCP server requires the X-Admin-Key header."}},
                status_code=401,
                headers={**_cors_headers(), "mcp-session-id": session_id},
            )
        elif method == "tools/list":
            result = {"tools": _tool_list(_is_authed(request))}
        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not name:
                raise ValueError("Missing 'name' in tools/call params")
            if name in mcp_server.WRITE_TOOLS and not _is_authed(request):
                return JSONResponse(
                    {"jsonrpc": "2.0", "id": rpc_id,
                     "error": {"code": -32001,
                               "message": f"Tool '{name}' requires the X-Admin-Key header."}},
                    status_code=401,
                    headers={**_cors_headers(), "mcp-session-id": session_id},
                )
            try:
                content = await _dispatch_tool(name, arguments, session_id)
                result = {"content": content}
            except ValueError as exc:
                # Validation errors (unknown dataset/column/id) go back as
                # tool results per MCP spec, so the agent can read and retry.
                result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        else:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": rpc_id,
                 "error": {"code": -32601, "message": f"Method not found: {method}"}},
                status_code=404,
                headers={**_cors_headers(), "mcp-session-id": session_id},
            )
    except Exception as exc:
        LOG.exception("MCP error")
        return JSONResponse(
            {"jsonrpc": "2.0", "id": rpc_id,
             "error": {"code": -32603, "message": f"Internal error: {type(exc).__name__}: {exc}"}},
            status_code=500,
            headers={**_cors_headers(), "mcp-session-id": session_id},
        )

    return JSONResponse(
        {"jsonrpc": "2.0", "id": rpc_id, "result": result},
        headers={**_cors_headers(), "mcp-session-id": session_id},
    )


@mcp_router.delete("/mcp")
async def mcp_delete(request: Request):
    """End a session (MCP Streamable HTTP)."""
    session_id = request.headers.get("mcp-session-id")
    if session_id and session_id in SESSIONS:
        SESSIONS.pop(session_id, None)
    return Response(status_code=204, headers=_cors_headers())
