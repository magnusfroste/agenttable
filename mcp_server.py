"""
MCP tool framework — tool definitions + handlers.

Same role as agentanbud's mcp_server.py, but as an explicit registry
instead of an if-chain: mcp_http.py reads TOOLS/WRITE_TOOLS/HANDLERS
and dispatches. The read tools (list_datasets, describe_dataset,
search_rows, get_row) land in Sprint 3; keyed write tools (import_csv,
upsert_rows, delete_dataset) in Sprint 4.

A handler is:  async def _my_tool(conn, arguments: dict) -> list[dict]
and returns MCP content items, e.g. [{"type": "text", "text": "..."}].
"""
from __future__ import annotations

import json
import os

DB_PATH = os.environ.get("DB_PATH", "/data/application.db")


def _text(payload) -> list[dict]:
    """Wrap a JSON-serialisable payload as MCP text content."""
    return [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}]


# ---- Tool metadata (JSON Schema, shown by tools/list) -----------------------
# Read tools are always listed; write tools only for authenticated callers.
# Example shape:
# {
#     "name": "list_datasets",
#     "description": "List available datasets with name, slug and row count.",
#     "inputSchema": {"type": "object", "properties": {}},
# }

TOOLS: list[dict] = []           # open read tools (Sprint 3)
WRITE_TOOLS_DEF: list[dict] = [] # keyed write tools (Sprint 4)

# name -> async handler(conn, arguments)
HANDLERS: dict = {}

# Names that require the admin key (mirrors agentanbud's WRITE_TOOLS pattern)
WRITE_TOOLS: set[str] = {t["name"] for t in WRITE_TOOLS_DEF}
