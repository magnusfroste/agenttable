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
| `MCP_REQUIRE_KEY` | `false` (lokalt) / `true` (compose) | Kräv nyckel även för MCP-läsning (företagsdata) |
| `LOG_LEVEL` | `INFO` | Python-loggnivå |

## MCP

Endpoint: `POST /mcp` (JSON-RPC 2.0, Streamable HTTP). Läsverktyg:
`list_datasets`, `describe_dataset`, `search_rows`, `get_row` — alla svar
begränsas till kolumnerna som exponerats per dataset (väljs i webbvyn).

Klient-konfig (t.ex. Claude Code / Hermes):

```json
{
  "mcpServers": {
    "agenttable": {
      "url": "https://<din-hostname>/mcp",
      "transport": "streamable-http",
      "headers": { "X-Admin-Key": "<nyckel>" }
    }
  }
}
```

## Deploy (Easypanel bakom Cloudflare-tunnel)

1. Skapa en App-service i Easypanel från detta GitHub-repo (Dockerfile-build).
2. Sätt env: `ADMIN_API_KEY` (obligatorisk!), `MCP_REQUIRE_KEY=true`,
   `DB_PATH=/data/application.db`; montera en volym på `/data`.
3. Lägg till en hostname i den befintliga Cloudflare-tunneln → appens
   interna port 8080.
4. Cloudflare Access-policy för människor (webb-UI). Agenten når `/mcp`
   med `X-Admin-Key` — antingen via Access Service Token eller genom att
   exkludera `/mcp` från Access (nyckeln skyddar ändå).

## Status

Sprint 0–3 klara: CSV-upload, tabellvy (Tabulator, server-side sök),
MCP-läsverktyg med exposed_columns. Kvar: keyed skriv-verktyg på MCP
(#16) och app-sidig CF Access Service Token-validering (#15, valfri).
