"""FastAPI app — web UI + JSON API over the SQLite store.

Structure copied from agentanbud: create_app() factory, render(),
_require_admin(), asset_ver cache-busting, env.globals(abs/min/max).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
from pathlib import Path
from typing import Optional

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
LOG = logging.getLogger(__name__)

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from .csv_import import CsvError, parse_csv
from .db import (
    connect, init_db,
    create_dataset, delete_dataset, get_dataset, insert_rows, list_datasets,
    search_rows, set_exposed_columns,
)

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


def _require_admin(request: Request, form_key: Optional[str] = None) -> None:
    """Gate mutating endpoints. Accepts the key from the X-Admin-Key header
    or (for browser forms) a form field, so the upload page works without JS
    header tricks."""
    if not ADMIN_API_KEY:
        return
    supplied = request.headers.get("x-admin-key", "") or (form_key or "")
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

    def _import_csv(name: str, data: bytes) -> dict:
        """Parse CSV bytes and store as a new dataset. Raises CsvError."""
        columns, rows = parse_csv(data)
        conn = connect(db)
        try:
            ds = create_dataset(conn, name, columns)
            count = insert_rows(conn, ds["id"], rows)
        finally:
            conn.close()
        return {"slug": ds["slug"], "name": name, "rows": count, "columns": columns}

    # ---- Pages ----

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        conn = connect(db)
        try:
            datasets = list_datasets(conn)
        finally:
            conn.close()
        return render("index.html", request=request, datasets=datasets,
                      admin_required=bool(ADMIN_API_KEY))

    @app.get("/upload", response_class=HTMLResponse)
    def upload_page(request: Request):
        return render("upload.html", request=request,
                      admin_required=bool(ADMIN_API_KEY))

    @app.post("/upload", response_class=HTMLResponse)
    async def upload_submit(
        request: Request,
        file: UploadFile = File(...),
        name: str = Form(""),
        admin_key: str = Form(""),
    ):
        """HTMX form target — returns a partial (success card or error)."""
        try:
            _require_admin(request, form_key=admin_key)
        except HTTPException:
            return render("_upload_result.html", error="Fel admin-nyckel.")
        try:
            data = await file.read()
            ds_name = name.strip() or Path(file.filename or "dataset").stem
            result = _import_csv(ds_name, data)
        except CsvError as exc:
            return render("_upload_result.html", error=str(exc))
        except Exception:
            LOG.exception("CSV import failed")
            return render("_upload_result.html",
                          error="Kunde inte läsa filen — är det verkligen en CSV?")
        return render("_upload_result.html", result=result)

    @app.get("/d/{slug}", response_class=HTMLResponse)
    def dataset_page(slug: str, request: Request):
        conn = connect(db)
        try:
            ds = get_dataset(conn, slug)
        finally:
            conn.close()
        if not ds:
            raise HTTPException(status_code=404, detail="dataset not found")
        return render("dataset.html", request=request, ds=ds,
                      admin_required=bool(ADMIN_API_KEY))

    # ---- API ----

    @app.get("/api/health")
    def health():
        return JSONResponse({"ok": True})

    @app.get("/api/datasets/{slug}/rows")
    def api_rows(
        slug: str,
        page: int = 1,
        size: int = DEFAULT_PAGE_SIZE,
        q: str = "",
        filters: str = "",
    ):
        """Server-side pagination + free text (q) + per-column filters
        (filters = JSON object {column: substring})."""
        size = max(1, min(size, MAX_PAGE_SIZE))
        page = max(1, page)
        try:
            filter_dict = json.loads(filters) if filters else {}
            if not isinstance(filter_dict, dict):
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="filters must be a JSON object")
        conn = connect(db)
        try:
            ds = get_dataset(conn, slug)
            if not ds:
                raise HTTPException(status_code=404, detail="dataset not found")
            total, rows = search_rows(
                conn, ds["id"], query=q.strip() or None,
                filters=filter_dict, limit=size, offset=(page - 1) * size,
            )
        finally:
            conn.close()
        return JSONResponse({
            "page": page, "size": size, "total": total,
            "last_page": max(1, math.ceil(total / size)),
            "rows": rows,
        })

    @app.get("/api/datasets")
    def api_list_datasets():
        conn = connect(db)
        try:
            return JSONResponse({"datasets": list_datasets(conn)})
        finally:
            conn.close()

    @app.post("/api/datasets")
    async def api_create_dataset(
        request: Request,
        file: UploadFile = File(...),
        name: str = Form(""),
    ):
        """Keyed CSV upload (multipart). Returns slug + row count."""
        _require_admin(request)
        data = await file.read()
        ds_name = name.strip() or Path(file.filename or "dataset").stem
        try:
            result = _import_csv(ds_name, data)
        except CsvError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return JSONResponse(result, status_code=201)

    @app.post("/api/datasets/{slug}/exposed")
    async def api_set_exposed(slug: str, request: Request):
        """Keyed: set which columns MCP may show. Body: {"columns": [...] | null}."""
        _require_admin(request)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="invalid JSON body")
        columns = body.get("columns")
        if columns is not None and not isinstance(columns, list):
            raise HTTPException(status_code=400, detail="columns must be a list or null")
        conn = connect(db)
        try:
            if not set_exposed_columns(conn, slug, columns):
                raise HTTPException(status_code=404, detail="dataset not found")
            ds = get_dataset(conn, slug)
        finally:
            conn.close()
        return JSONResponse({"slug": slug, "exposed_columns": ds["exposed_columns"]})

    @app.delete("/api/datasets/{slug}")
    def api_delete_dataset(slug: str, request: Request):
        """Keyed delete — removes the dataset and all its rows."""
        _require_admin(request)
        conn = connect(db)
        try:
            if not delete_dataset(conn, slug):
                raise HTTPException(status_code=404, detail="dataset not found")
        finally:
            conn.close()
        return JSONResponse({"deleted": slug})

    return app


def get_app() -> FastAPI:
    """uvicorn factory entrypoint: uvicorn app.main:get_app --factory"""
    return create_app()
