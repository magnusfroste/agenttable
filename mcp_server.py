"""
MCP tool framework — tool definitions + handlers.

Same role as agentanbud's mcp_server.py, but as an explicit registry
instead of an if-chain: mcp_http.py reads TOOLS/WRITE_TOOLS_DEF/HANDLERS
and dispatches. Keyed write tools (import_csv, upsert_rows,
delete_dataset) land in Sprint 4 (#16).

A handler is:  async def _my_tool(conn, arguments: dict) -> list[dict]
and returns MCP content items, e.g. [{"type": "text", "text": "..."}].

Every response respects the dataset's exposed_columns — columns the
admin has not exposed are invisible to agents, including in filters.
"""
from __future__ import annotations

import json
import os

from app import db

DB_PATH = os.environ.get("DB_PATH", "/data/application.db")


def _text(payload) -> list[dict]:
    """Wrap a JSON-serialisable payload as MCP text content."""
    return [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}]


def _exposed(ds: dict) -> list[str]:
    """Columns the agent may see (exposed_columns_json = null → all)."""
    return ds["columns"] if ds["exposed_columns"] is None else ds["exposed_columns"]


def _project(row: dict, exposed: list[str]) -> dict:
    """Strip a row down to id + exposed columns."""
    return {"id": row["id"], **{k: row[k] for k in exposed if k in row}}


def _require_dataset(conn, arguments: dict) -> dict:
    slug = (arguments.get("dataset") or "").strip()
    if not slug:
        raise ValueError("Missing 'dataset' (slug from list_datasets).")
    ds = db.get_dataset(conn, slug)
    if not ds:
        raise ValueError(f"Unknown dataset: '{slug}'. Call list_datasets to see available slugs.")
    return ds


# ---- Handlers ---------------------------------------------------------------


async def _list_datasets(conn, arguments: dict) -> list[dict]:
    payload = [
        {"slug": d["slug"], "name": d["name"], "row_count": d["row_count"],
         "created_at": d["created_at"]}
        for d in db.list_datasets(conn)
    ]
    return _text({"datasets": payload})


async def _describe_dataset(conn, arguments: dict) -> list[dict]:
    ds = _require_dataset(conn, arguments)
    exposed = _exposed(ds)
    _, sample = db.search_rows(conn, ds["id"], limit=3)
    return _text({
        "slug": ds["slug"],
        "name": ds["name"],
        "row_count": ds["row_count"],
        "columns": exposed,
        "examples": [_project(r, exposed) for r in sample],
    })


async def _search_rows(conn, arguments: dict) -> list[dict]:
    ds = _require_dataset(conn, arguments)
    exposed = _exposed(ds)
    query = (arguments.get("query") or "").strip() or None
    limit = max(1, min(int(arguments.get("limit") or 10), 50))
    filters = arguments.get("filters") or {}
    if not isinstance(filters, dict):
        raise ValueError("'filters' must be an object: {column: substring}")
    unknown = [c for c in filters if c not in exposed]
    if unknown:
        raise ValueError(f"Unknown or unexposed column(s) in filters: {unknown}. "
                         f"Available: {exposed}")
    total, rows = db.search_rows(conn, ds["id"], query=query, filters=filters, limit=limit)
    return _text({
        "dataset": ds["slug"],
        "total_matches": total,
        "returned": len(rows),
        "rows": [_project(r, exposed) for r in rows],
    })


async def _get_row(conn, arguments: dict) -> list[dict]:
    ds = _require_dataset(conn, arguments)
    row_id = arguments.get("id")
    if row_id is None:
        raise ValueError("Missing 'id' (row id from search_rows).")
    row = db.get_row(conn, ds["id"], int(row_id))
    if not row:
        raise ValueError(f"No row with id {row_id} in dataset '{ds['slug']}'.")
    return _text(_project(row, _exposed(ds)))


# ---- Tool metadata (JSON Schema, shown by tools/list) -----------------------

TOOLS: list[dict] = [
    {
        "name": "list_datasets",
        "description": "List available datasets with name, slug, row count and creation date. Start here to discover what data exists.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "describe_dataset",
        "description": "Describe one dataset: its columns, row count and a few example rows. Call this before search_rows to learn which columns exist.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset": {"type": "string", "description": "Dataset slug from list_datasets."},
            },
            "required": ["dataset"],
        },
    },
    {
        "name": "search_rows",
        "description": "Search rows in a dataset: free text across all columns and/or per-column substring filters. Returns matching rows with their ids. Example: search_rows(dataset='felkoder', query='E01234') or filters={'Kategori': 'Hydraulik'}.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset": {"type": "string", "description": "Dataset slug from list_datasets."},
                "query": {"type": "string", "description": "Free text matched anywhere in the row."},
                "filters": {
                    "type": "object",
                    "description": "Per-column substring filters, e.g. {\"Kategori\": \"Hydraulik\"}. Column names from describe_dataset.",
                    "additionalProperties": {"type": "string"},
                },
                "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
            },
            "required": ["dataset"],
        },
    },
    {
        "name": "get_row",
        "description": "Get one row by id (from search_rows).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset": {"type": "string", "description": "Dataset slug."},
                "id": {"type": "integer", "description": "Row id from search_rows."},
            },
            "required": ["dataset", "id"],
        },
    },
]

WRITE_TOOLS_DEF: list[dict] = []  # keyed write tools (Sprint 4, #16)

# name -> async handler(conn, arguments)
HANDLERS: dict = {
    "list_datasets": _list_datasets,
    "describe_dataset": _describe_dataset,
    "search_rows": _search_rows,
    "get_row": _get_row,
}

# Names that require the admin key (mirrors agentanbud's WRITE_TOOLS pattern)
WRITE_TOOLS: set[str] = {t["name"] for t in WRITE_TOOLS_DEF}
