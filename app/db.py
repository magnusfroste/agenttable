"""SQLite helpers — connection, schema bootstrap, migrations.

Same pattern as agentanbud: connect() with WAL + Row factory,
init_db() runs schema.sql idempotently, _migrate() adds columns
via guarded ALTER TABLE. Dataset/row helpers land in Sprint 1 (#5).
"""
from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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
