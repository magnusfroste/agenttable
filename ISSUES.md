# AgentTable — sprintar & issues

Backlog för MVP:n. Se [`KICKOFF.md`](KICKOFF.md) för arkitektur och beslut.
Storlek: **S** ≈ <½ dag, **M** ≈ ½–1 dag, **L** ≈ 1–2 dagar.
När GitHub-repot finns kan varje issue klistras in som ett `gh issue create`.

---

## Sprint 0 — Skelett & infra
**Mål:** en tom men körbar app som bootar i Docker, med agentanbuds beprövade skelett.

### #1 Initiera repo + kopiera infra-skelett  · infra · M
Kopiera från `../agentanbud`: `app/db.py`, `app/main.py` (struktur), `mcp_http.py`,
`mcp_server.py`, `Dockerfile`, `docker-compose.yml`, `.env.example`,
`web/templates/base.html`, `web/static/style.css`.
- [ ] `git init`, `.gitignore` (data/, .env, __pycache__)
- [ ] Filerna kopierade och importerar utan fel
- [ ] `ADMIN_API_KEY` + `DB_PATH` i `.env.example`

### #2 Riv upphandlings-specifikt  · chore · S
- [ ] Bort: `scraper/`, `orchestrator`, cron, `tenders`-schema, providers/kunskap/blogg
- [ ] Bort: upphandlings-specifika MCP-verktyg och routes
- [ ] Appen bootar utan död kod

### #3 Tom app bootar + healthcheck  · feature · S
- [ ] `GET /api/health` → `{"ok": true}`
- [ ] `GET /` renderar base.html-skalet (namn: AgentTable)
- [ ] `docker compose up` → nåbar på localhost
- [ ] Cache-busting (`asset_ver`) + `env.globals` (abs/min/max) kvar

### #4 Rebranding + config  · chore · S
- [ ] Titel/nav/footer → AgentTable
- [ ] README (kort): vad appen gör, kör lokalt, env-vars

---

## Sprint 1 — Datamodell & CSV-import
**Mål:** ladda upp en CSV och få in den i SQLite.

### #5 Schema: datasets + rows  · feature · M
- [ ] `datasets` (slug, name, columns_json, exposed_columns_json, row_count)
- [ ] `rows` (dataset_id, data_json) + index
- [ ] `init_db` + idempotent `_migrate`
- [ ] db-hjälpare: `create_dataset`, `insert_rows`, `get_dataset`, `list_datasets`

### #6 CSV-upload endpoint (keyed)  · feature · M
- [ ] `POST /api/datasets` (multipart CSV) bakom `X-Admin-Key`
- [ ] Parsa header → `columns_json`; varje rad → `rows.data_json`
- [ ] Robust: BOM, avgränsare (`,`/`;`), tomma rader, dubbla kolumnnamn
- [ ] Returnerar slug + antal rader; testat med ~8000 rader

### #7 Upload-sida  · feature · S
- [ ] `/upload` (Jinja) — filväljare, namn, submit via HTMX
- [ ] Fel visas tydligt (fel format, tom fil)
- [ ] Vid klart: länk till dataset-vyn

### #8 Dataset-lista + radering  · feature · S
- [ ] `/` listar dataset (namn, antal rader, datum)
- [ ] Radera dataset (keyed) — tar bort rows också

---

## Sprint 2 — Tabellvy (Airtable-lite)
**Mål:** visa och söka i datan i webben.

### #9 Dataset-detaljsida med Tabulator  · feature · M
- [ ] `/d/{slug}` renderar Tabulator (CDN, ingen build) över datan
- [ ] Sortera/filtrera/paginera i klienten för mindre dataset
- [ ] Data via `GET /api/datasets/{slug}/rows?page=&q=`

### #10 Server-side sök/filter (stora dataset)  · feature · M
- [ ] `search_rows`-query i db: fritext över alla kolumner + per-kolumn-filter (`json_extract`)
- [ ] HTMX-partial för sökresultat (för 8000+ rader utan att skicka allt)
- [ ] Paginering server-side

### #11 exposed_columns-UI  · feature · S
- [ ] Välj vilka kolumner som exponeras via MCP (checkboxar, keyed)
- [ ] Sparas i `exposed_columns_json` (null = alla)

---

## Sprint 3 — MCP-yta (läs)
**Mål:** en agent kan lista, beskriva och söka i datan.

### #12 MCP HTTP-transport bootar  · infra · S
- [ ] `mcp_http.py` monterad; `GET /mcp` visar serverinfo + tools_count
- [ ] `initialize` / `tools/list` / `tools/call` fungerar (kopierat mönster)

### #13 Verktyg: list_datasets + describe_dataset  · feature · M
- [ ] `list_datasets` → namn, slug, antal rader
- [ ] `describe_dataset(slug)` → exponerade kolumner, antal, 2–3 exempelrader

### #14 Verktyg: search_rows + get_row  · feature · M
- [ ] `search_rows(dataset, query, filters?, limit?)` → matchande rader (bara exposed_columns)
- [ ] `get_row(dataset, id)` → en rad
- [ ] Alla svar respekterar `exposed_columns`
- [ ] Verifierat live: en riktig MCP-session hämtar felkoder

---

## Sprint 4 — Auth, agent-åtkomst & deploy
**Mål:** säker drift bakom Cloudflare-tunneln, agent kan nå MCP.

### #15 Auth-modell  · infra · M
- [ ] Skriv alltid bakom `X-Admin-Key`
- [ ] Beslut: är läsning öppen eller keyed? (företagsdata → troligen keyed)
- [ ] `/mcp` accepterar BÅDE `X-Admin-Key` OCH Cloudflare Access Service Token
      (`CF-Access-Client-Id`/`CF-Access-Client-Secret`) → välj i CF-dashboard

### #16 Keyed skriv-verktyg på MCP  · feature · M
- [ ] `import_csv` / `upsert_rows` / `delete_dataset` exponeras bara med nyckel
      (samma mönster som agentanbuds create_post)

### #17 Easypanel-deploy bakom CF-tunnel  · infra · M
- [ ] Docker-instans i Easypanel, intern port
- [ ] Ny hostname i den befintliga tunneln → appens port
- [ ] Cloudflare Access-policy för människor; service token för agenten
- [ ] Verifierat: nås hemifrån via Access, agent via token/nyckel

### #18 (valfritt) Mini-analytics  · feature · S
- [ ] `usage_log` + unika agent-sessioner (`_sid`-hash, samma mönster som agentanbud)
- [ ] Enkel `/analytics` — hur mycket datan används och av vem (människa/agent)

---

## Utanför MVP (icebox)
- Inline cell-redigering i Tabulator (editable cells) → skriv tillbaka till rows
- Flera CSV → append/merge till samma dataset (schema-matchning)
- Versionshantering / audit-logg per dataset
- Export (CSV/JSON) tillbaka ut
- Fler MCP-verktyg: `distinct_values(column)`, `count_by(column)`
