# AgentTable — kickoff-brief

> Skrevs i agentanbud-sessionen 2026-07-12 för att bära över alla beslut till
> det nya projektet. Läs detta först, scaffolda sedan steg för steg.

## Vad det är

En **minimal Airtable-lik MCP-lagring**. En användare laddar upp en CSV (t.ex.
~8000 felkoder från verksamheten), den lagras i SQLite, och exponeras via en
**MCP-yta** så att en agent (Hermes m.fl.) kan hämta datan. Syftet: återanvända
agentanbuds beprövade "en SQLite + egen data + MCP + Easypanel self-host"-mönster,
men generellt — CSV in → SQLite → MCP ut. Medvetet minimalt (FlowWink/flowtable
blev för stort; det här ska vara litet).

## Lyft rakt av från agentanbud (`../agentanbud`)

Kopiera och anpassa — detta är beprövad infrastruktur, bygg inte om:

- **`mcp_http.py`** — MCP-over-HTTP: transport, sessioner, nyckel-skyddade
  skrivverktyg, CORS. Kärnan. (Behåll `_is_authed`/`WRITE_TOOLS`-mönstret.)
- **`mcp_server.py`** — verktygs-ramverket (list_tools/call_tool + handlers).
- **`app/db.py`** — `connect()`/`init_db()`/`_migrate()`-mönstret.
- **`app/main.py`** — struktur: `create_app()`, `render()`, `_require_admin()`,
  cache-busting (`asset_ver`), `env.globals.update(abs=abs, min=min, max=max)`.
- **Deploy:** `docker-compose.yml`, `Dockerfile`, `.env.example` (ADMIN_API_KEY,
  DB_PATH), Easypanel-deploy-webhook-mönstret.
- **UI-skal:** `web/templates/base.html`, `web/static/style.css`.

## Designa nytt (den enda riktiga skillnaden: flexibelt schema)

agentanbud har ETT fast schema (`tenders`). Här behövs godtyckliga CSV-kolumner:

```sql
CREATE TABLE datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    columns_json TEXT NOT NULL,          -- alla kolumnnamn från CSV-headern
    exposed_columns_json TEXT,           -- vilka kolumner MCP får visa (null = alla)
    row_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL,
    data_json TEXT NOT NULL,             -- en CSV-rad som JSON-objekt
    FOREIGN KEY (dataset_id) REFERENCES datasets(id)
);
CREATE INDEX idx_rows_dataset ON rows(dataset_id);
```

8000 rader som JSON i SQLite är blixtsnabbt; filtrera med `json_extract`.

- **CSV-upload** (keyed): parsa header → `columns_json`, varje rad → `rows`.
  Endpoint `POST /api/datasets` (multipart CSV) + en enkel upload-sida.
- **`exposed_columns`** styr vad agenten får se — "exponera det de väljer att ladda".

## MCP-verktyg (generiska)

Öppna läs (eller keyed, se säkerhet nedan):
- `list_datasets` — vilka dataset finns
- `describe_dataset(slug)` — kolumner, antal rader, exempel
- `search_rows(dataset, query, filters?, limit?)` — fritext + kolumnfilter
- `get_row(dataset, id)` — en rad

Keyed skriv (samma mönster som agentanbuds create_post):
- `import_csv` / `upsert_rows` / `delete_dataset` — om agenten ska kunna ladda data

## Frontend: server-renderat, INGEN build

Jinja + **HTMX** (sök/filtrera/paginera via partials) + **Tabulator** (via CDN,
`<script>`-tag) för en sorterbar/filtrerbar (ev. inline-redigerbar) tabell.
INGEN React/Vue-SPA — det var det som gjorde FlowWink för stort.

## Infrastruktur (Easypanel + Cloudflare Tunnel)

Kör som en Docker-instans i Easypanel bakom den **befintliga Cloudflare-tunneln**
(samma som AnythingLLM). Ny hostname i tunneln → appens interna port. Datan bakom
brandväggen; Cloudflare Access = identitetsstyrt "sugrör". **Ingen LAN-direktväg**
(172.17.x.y är host-intern Docker-brygga, ej LAN-nåbar ändå).

- **Människor** → webb-UI via Cloudflare Access-login.
- **Agent (Hermes)** kan inte göra interaktiv Access-login. Välj:
  - (a) Cloudflare **Access Service Token** (`CF-Access-Client-Id/Secret`-headers), eller
  - (b) exkludera `/mcp` från Access och skydda med appens egna `X-Admin-Key`.
  - **Rekommendation:** stöd BÅDA i appen så valet kan göras i CF-dashboarden.

## Säkerhet

Företagsdata → default: läsning kan vara keyed (till skillnad från agentanbud där
läsning är öppen). Skrivning (CSV-upload, dataset-radering) alltid bakom
`ADMIN_API_KEY`. Sätt alltid nyckeln i produktion.

## Föreslagen ordning

1. Skelett: kopiera infra-filerna, riv scrapers/tenders, få en tom app att boota.
2. Schema + CSV-upload + tabellvy (Tabulator) — kan ladda och visa data.
3. MCP-verktygen (list/describe/search/get) — agent kan läsa.
4. Keyed skriv + `exposed_columns`.
5. docker-compose/.env för Easypanel, deploy bakom tunneln.

## Släng (finns i agentanbud, hör inte hemma här)

`scraper/`, `orchestrator`, cron, `tenders`-schemat, providers/kunskap/blogg,
och den upphandlings-specifika analytics/SEO (behåll ev. en mini-usage_log om
du vill mäta agent-sessioner — samma _sid-hash-mönster).
