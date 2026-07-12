"""SQLite helpers — connection, schema bootstrap, migrations, dataset CRUD.

Same pattern as agentanbud: connect() with WAL + Row factory,
init_db() runs schema.sql idempotently, _migrate() adds columns
via guarded ALTER TABLE.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

LOG = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection with Row factory + WAL mode for safe concurrent reads."""
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    # WAL lets web readers run concurrently with a CSV-import writer.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path) -> None:
    """Create schema if missing. Idempotent."""
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply idempotent column migrations.

    CREATE TABLE IF NOT EXISTS never adds columns to a table that already
    exists, so new columns go here via ALTER TABLE guarded by a PRAGMA
    check. Cheap enough to run on every init_db().
    """
    # No migrations yet. Pattern:
    # cols = {row[1] for row in conn.execute("PRAGMA table_info(datasets)")}
    # if "new_col" not in cols:
    #     conn.execute("ALTER TABLE datasets ADD COLUMN new_col TEXT")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(text: str) -> str:
    """Make a URL-safe slug from a name. Swedish å/ä/ö → a/a/o."""
    s = (text or "").strip().lower()
    for a, b in (("å", "a"), ("ä", "a"), ("ö", "o"), ("é", "e"), ("ü", "u")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80] or "dataset"


def unique_slug(conn: sqlite3.Connection, base: str) -> str:
    """Return `base`, or base-2, base-3… if taken by another dataset."""
    slug = base
    n = 1
    while True:
        row = conn.execute("SELECT id FROM datasets WHERE slug = ?", (slug,)).fetchone()
        if not row:
            return slug
        n += 1
        slug = f"{base}-{n}"


# ----- Dataset helpers -------------------------------------------------------


def _dataset_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["columns"] = json.loads(d.pop("columns_json") or "[]")
    exposed = d.pop("exposed_columns_json", None)
    d["exposed_columns"] = json.loads(exposed) if exposed else None  # None = alla
    return d


def create_dataset(conn: sqlite3.Connection, name: str, columns: list[str]) -> dict:
    """Insert a new dataset. Returns {id, slug}."""
    slug = unique_slug(conn, slugify(name))
    cur = conn.execute(
        "INSERT INTO datasets (slug, name, columns_json) VALUES (?, ?, ?)",
        (slug, name, json.dumps(columns, ensure_ascii=False)),
    )
    conn.commit()
    return {"id": cur.lastrowid, "slug": slug}


def insert_rows(conn: sqlite3.Connection, dataset_id: int, rows: Iterable[dict]) -> int:
    """Bulk-insert rows (one JSON object per CSV row) and refresh row_count."""
    conn.executemany(
        "INSERT INTO rows (dataset_id, data_json) VALUES (?, ?)",
        ((dataset_id, json.dumps(r, ensure_ascii=False)) for r in rows),
    )
    conn.execute(
        "UPDATE datasets SET row_count = (SELECT COUNT(*) FROM rows WHERE dataset_id = ?) WHERE id = ?",
        (dataset_id, dataset_id),
    )
    conn.commit()
    row = conn.execute("SELECT row_count FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    return row[0] if row else 0


def get_dataset(conn: sqlite3.Connection, slug: str) -> Optional[dict]:
    row = conn.execute("SELECT * FROM datasets WHERE slug = ?", (slug,)).fetchone()
    return _dataset_dict(row) if row else None


def list_datasets(conn: sqlite3.Connection) -> list[dict]:
    return [
        _dataset_dict(r)
        for r in conn.execute("SELECT * FROM datasets ORDER BY created_at DESC, id DESC")
    ]


def delete_dataset(conn: sqlite3.Connection, slug: str) -> bool:
    """Delete a dataset and all its rows. Returns True if it existed."""
    row = conn.execute("SELECT id FROM datasets WHERE slug = ?", (slug,)).fetchone()
    if not row:
        return False
    conn.execute("DELETE FROM rows WHERE dataset_id = ?", (row[0],))
    conn.execute("DELETE FROM datasets WHERE id = ?", (row[0],))
    conn.commit()
    return True


def _json_path(column: str) -> str:
    """JSON path for a CSV column name. Quotes stripped — they can't be
    escaped inside a SQLite JSON path literal."""
    return '$."' + column.replace('"', "") + '"'


def search_rows(
    conn: sqlite3.Connection,
    dataset_id: int,
    query: Optional[str] = None,
    filters: Optional[dict] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[dict]]:
    """Free text over the whole row (LIKE on data_json) + per-column
    substring filters via json_extract. Returns (total, rows) where each
    row is {id, <column>: <value>, …}. 8000 JSON rows scan in milliseconds."""
    where = ["dataset_id = ?"]
    params: list = [dataset_id]
    if query:
        where.append("data_json LIKE ?")
        params.append(f"%{query}%")
    for col, val in (filters or {}).items():
        if val is None or val == "":
            continue
        where.append("json_extract(data_json, ?) LIKE ?")
        params.extend([_json_path(col), f"%{val}%"])
    cond = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM rows WHERE {cond}", params).fetchone()[0]
    rows = [
        {"id": r["id"], **json.loads(r["data_json"])}
        for r in conn.execute(
            f"SELECT id, data_json FROM rows WHERE {cond} ORDER BY id LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
    ]
    return total, rows


def get_row(conn: sqlite3.Connection, dataset_id: int, row_id: int) -> Optional[dict]:
    r = conn.execute(
        "SELECT id, data_json FROM rows WHERE dataset_id = ? AND id = ?",
        (dataset_id, row_id),
    ).fetchone()
    return {"id": r["id"], **json.loads(r["data_json"])} if r else None


def set_exposed_columns(conn: sqlite3.Connection, slug: str, columns: Optional[list[str]]) -> bool:
    """Set which columns MCP may show (None = all). Returns True if dataset exists."""
    ds = get_dataset(conn, slug)
    if not ds:
        return False
    # Only keep names that actually exist in the dataset
    value = None
    if columns is not None:
        valid = [c for c in columns if c in ds["columns"]]
        value = json.dumps(valid, ensure_ascii=False)
    conn.execute("UPDATE datasets SET exposed_columns_json = ? WHERE slug = ?", (value, slug))
    conn.commit()
    return True
