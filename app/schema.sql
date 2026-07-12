-- AgentTable schema — flexible datasets: CSV in → SQLite → MCP ut.
-- Arbitrary CSV columns are stored as JSON per row; filter with json_extract.

CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    columns_json TEXT NOT NULL,          -- alla kolumnnamn från CSV-headern
    exposed_columns_json TEXT,           -- vilka kolumner MCP får visa (null = alla)
    row_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL,
    data_json TEXT NOT NULL,             -- en CSV-rad som JSON-objekt
    FOREIGN KEY (dataset_id) REFERENCES datasets(id)
);

CREATE INDEX IF NOT EXISTS idx_rows_dataset ON rows(dataset_id);
