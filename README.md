# AgentTable

Minimal Airtable-lik MCP-lagring: **CSV in → SQLite → MCP ut.**

Ladda upp en CSV (t.ex. ~8000 felkoder), den lagras i SQLite med flexibelt
schema (godtyckliga kolumner som JSON per rad), och exponeras via en
MCP-yta så att agenter kan lista, beskriva och söka i datan.

Byggd på agentanbuds beprövade mönster: FastAPI + Jinja (ingen build),
SQLite i en Docker-volym, MCP-over-HTTP med nyckel-skyddade skrivverktyg.
Se [KICKOFF.md](KICKOFF.md) för arkitektur och [ISSUES.md](ISSUES.md) för backlog.

## Kör lokalt

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
DB_PATH=./data/application.db .venv/bin/uvicorn app.main:get_app --factory --reload --port 8081
```

→ http://localhost:8081 (web), `/api/health`, `/mcp` (MCP-serverinfo).

Eller med Docker:

```bash
cp .env.example .env   # sätt ADMIN_API_KEY
docker compose up --build
```

## Miljövariabler

| Variabel | Default | Beskrivning |
|---|---|---|
| `DB_PATH` | `/data/application.db` | SQLite-fil (volym i Docker) |
| `ADMIN_API_KEY` | *(tom = öppet)* | `X-Admin-Key` för skrivning. Sätt alltid i produktion. |
| `APP_PORT` | `8081` | Host-port för docker compose |
| `LOG_LEVEL` | `INFO` | Python-loggnivå |

## Status

Sprint 0 (skelett) klar — appen bootar, healthcheck + tomt MCP-endpoint.
Nästa: CSV-upload + tabellvy (Sprint 1–2), MCP-läsverktyg (Sprint 3).
