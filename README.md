# AI Diff Review Service

A FastAPI service that accepts unified diffs, reviews them asynchronously, and exposes ordered findings through polling and Server-Sent Events. It implements a deterministic `mock` provider for contract verification and a bounded LangGraph workflow backed by Cerebras for the optional `llm` provider.

## Architecture

The HTTP process validates and persists submissions in PostgreSQL, then four internal workers claim queued jobs with database row locking. Both providers run behind the same parse, file-boundary chunk, normalize, deduplicate, sort, cache, and event-persistence pipeline. Every SSE event is stored with a sequence number, so a completed stream can be replayed identically after reconnecting or restarting the service.

All application tables use the `xsolla_` prefix.

## Local setup

Prerequisites: Python 3.12, `uv`, Docker, and PostgreSQL (or a Supabase connection URL).

```powershell
Copy-Item .env.example .env
uv sync
uv run fastapi dev
```

Never commit `.env`. Generate a long random `BEARER_TOKEN`. If a database password contains reserved URL characters, URL-encode it before putting it in `DATABASE_URL`.

For Supabase's transaction pooler, use an async Psycopg URL similar to:

```text
postgresql+psycopg://USER:URL_ENCODED_PASSWORD@POOLER_HOST:6543/postgres?sslmode=require
```

The engine uses `NullPool` and `prepare_threshold=None` because Supabase transaction mode does
not support prepared statements. For a persistent IPv4 backend, Supabase session mode on port
5432 is also suitable. Prefer the session-mode URL for `MIGRATION_DATABASE_URL`; use the exact
connection strings shown by the project's Connect panel.

## Configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy async PostgreSQL URL |
| `MIGRATION_DATABASE_URL` | Optional session/direct URL used only by Alembic |
| `BEARER_TOKEN` | Token required by every `/v1/*` request |
| `CEREBRAS_API_KEY` | Server-side Cerebras credential; required only for `llm` |
| `CEREBRAS_MODEL` | Defaults to `gpt-oss-120b` |
| `CEREBRAS_TIMEOUT_SECONDS` | Per-call timeout, default 20 seconds |
| `CEREBRAS_MAX_RETRIES` | Provider retries, default 1 |

If Cerebras is missing or unreachable, the accepted job transitions to `failed` with a clear error. The API process remains healthy.

## API

Public:

- `GET /health`
- `GET /spec`

Bearer protected:

- `POST /v1/reviews`
- `GET /v1/reviews/{jobId}`
- `GET /v1/reviews/{jobId}/stream`

Example:

```powershell
$headers = @{ Authorization = "Bearer $env:BEARER_TOKEN" }
$body = @{ diff = (Get-Content -Raw example.diff) } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/v1/reviews -Headers $headers -ContentType application/json -Body $body
```

## Verification

```powershell
uv run ruff check .
uv run ty check
uv run pytest -q
```

The tests cover parsing and new-file line tracking, all deterministic rules, file-boundary chunking, authentication, error taxonomy, idempotency, caching, ordered findings, SSE replay, and graceful LLM failure.

## Production process

Run one application process so the declared four-worker queue and token-bucket rate limit have one authority:

```powershell
fastapi run --host 0.0.0.0 --port 8000
```

PostgreSQL makes jobs, cache entries, idempotency records, and SSE events durable across application restarts.
