"""FastAPI app — web UI + JSON API over the SQLite store.

Structure copied from agentanbud: create_app() factory, render(),
_require_admin(), asset_ver cache-busting, env.globals(abs/min/max).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from pathlib import Path
from typing import Optional

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
LOG = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from .db import connect, init_db

# MCP-over-HTTP is optional — only loaded if mcp_http module is present.
try:
    from mcp_http import mcp_router
    MCP_HTTP_AVAILABLE = True
except ImportError:
    MCP_HTTP_AVAILABLE = False
    LOG.info("mcp_http not importable, /mcp endpoint disabled")

DB_PATH = os.environ.get("DB_PATH", "/data/application.db")
TEMPLATE_DIR = Path(__file__).parent.parent / "web" / "templates"
STATIC_DIR = Path(__file__).parent.parent / "web" / "static"

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200

# Admin auth — when set, mutating endpoints require the X-Admin-Key header.
# When unset (local dev), mutating endpoints stay open.
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")


def _require_admin(request: Request) -> None:
    if not ADMIN_API_KEY:
        return
    supplied = request.headers.get("x-admin-key", "")
    if not hmac.compare_digest(supplied, ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="missing or invalid X-Admin-Key")


def _num(n) -> str:
    """Format int with thin-space thousands separator (Swedish style)."""
    return f"{int(n):,}".replace(",", " ")


def create_app(db_path: Optional[str] = None) -> FastAPI:
    db = db_path or DB_PATH
    try:
        init_db(db)
    except Exception as exc:
        LOG.warning("init_db failed: %s", exc)

    app = FastAPI(title="AgentTable", version="0.1.0")
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    env.filters["format_num"] = _num
    # Python builtins used in templates (Jinja doesn't expose these by default).
    env.globals.update(abs=abs, min=min, max=max)

    # Cache-busting: a short hash of the static assets, computed once at
    # startup. When style.css / app.js change and are redeployed the hash
    # changes, so browsers (and any CDN) fetch the new file instead of a
    # stale cached copy. Exposed to all templates as {{ asset_ver }}.
    _h = hashlib.md5()
    for _name in ("style.css", "app.js"):
        try:
            _h.update((STATIC_DIR / _name).read_bytes())
        except Exception:
            pass
    env.globals["asset_ver"] = _h.hexdigest()[:10]

    def render(template: str, **ctx) -> str:
        tpl = env.get_template(template)
        return tpl.render(request=ctx.pop("request", None), **ctx)

    # ---- Static ----
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ---- MCP over HTTP (Streamable HTTP transport) ----
    if MCP_HTTP_AVAILABLE:
        app.include_router(mcp_router)
        LOG.info("MCP HTTP endpoint mounted at /mcp")
    else:
        LOG.warning("MCP HTTP endpoint NOT mounted (mcp_http module missing)")

    # ---- Pages ----

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        conn = connect(db)
        try:
            datasets = [dict(r) for r in conn.execute(
                "SELECT slug, name, row_count, created_at FROM datasets ORDER BY created_at DESC"
            )]
        finally:
            conn.close()
        return render("index.html", request=request, datasets=datasets)

    # ---- API ----

    @app.get("/api/health")
    def health():
        return JSONResponse({"ok": True})

    return app


def get_app() -> FastAPI:
    """uvicorn factory entrypoint: uvicorn app.main:get_app --factory"""
    return create_app()
