# AI Diff Review Service

A FastAPI service that accepts unified diffs, reviews them asynchronously, and exposes ordered findings through polling and Server-Sent Events (SSE).

The service implements a deterministic `mock` provider for contract verification and a bounded LangGraph workflow backed by Cerebras for the optional `llm` provider.

## Architecture

The service runs as a single FastAPI application process backed by PostgreSQL.

`POST /v1/reviews` validates the request, persists a queued job and its initial SSE event, and returns `202 Accepted`. Four internal asynchronous workers claim queued jobs using PostgreSQL row locking with `FOR UPDATE SKIP LOCKED`.

Both providers run behind the same processing pipeline:

```text
Request
  ↓
Validation
  ↓
Persist queued job
  ↓
Worker claim
  ↓
Unified-diff parsing
  ↓
File-boundary chunking
  ↓
Provider
  ↓
Normalization
  ↓
Global deduplication
  ↓
Deterministic ordering
  ↓
Cache / result persistence
  ↓
Durable SSE events
```

PostgreSQL stores jobs, cache entries, idempotency records, and SSE event history. Every SSE event has a per-job sequence number, allowing a completed stream to be replayed byte-identically after reconnecting or restarting the service.

On startup, abandoned `running` jobs are returned to the queue.

All service-owned database tables use the `xsolla_` prefix.

## Providers

### Mock provider

`MockProvider` is deterministic Python and scans added diff lines only.

It implements the published mock rules directly without involving an LLM. Prompt-injection text is treated as inert input and reported as a finding rather than interpreted as an instruction.

### LLM provider

`CerebrasProvider` uses a bounded LangGraph `StateGraph` with `ChatCerebras`.

Parsed chunks are sent through the provider using strict Pydantic structured output. Proposed findings are validated against the actual added paths and line numbers present in each chunk before entering the shared normalization pipeline.

The graph has no tools and no recursive agent loop.

If Cerebras credentials are missing, the provider times out, the upstream service is unavailable, or the model produces an invalid response, the accepted job transitions cleanly to `failed` without crashing the API process.

## Local setup

Prerequisites:

- Python 3.12
- `uv`
- Docker
- PostgreSQL or a Supabase PostgreSQL connection

Create the local environment:

```powershell
Copy-Item .env.example .env
uv sync
uv run fastapi dev
```

Never commit `.env`.

Generate a long random `BEARER_TOKEN`.

If a database password contains reserved URL characters, URL-encode it before placing it in `DATABASE_URL`.

For Supabase's transaction pooler, use an async Psycopg URL similar to:

```text
postgresql+psycopg://USER:URL_ENCODED_PASSWORD@POOLER_HOST:6543/postgres?sslmode=require
```

Prepared statements are disabled with `prepare_threshold=None` when using the Supabase transaction pooler.

The application uses SQLAlchemy connection pooling for efficient connection reuse.

For Alembic migrations, prefer a session/direct PostgreSQL connection through `MIGRATION_DATABASE_URL`. Use the exact connection strings provided by the Supabase project's Connect panel.

## Configuration

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy async PostgreSQL URL |
| `MIGRATION_DATABASE_URL` | Optional session/direct PostgreSQL URL used by Alembic |
| `BEARER_TOKEN` | Token required by every `/v1/*` request |
| `CEREBRAS_API_KEY` | Server-side Cerebras credential; required only for `llm` |
| `CEREBRAS_MODEL` | Cerebras model, default `gpt-oss-120b` |
| `CEREBRAS_TIMEOUT_SECONDS` | Per-call timeout, default 20 seconds |
| `CEREBRAS_MAX_RETRIES` | Provider retries, default 1 |

If Cerebras is missing or unreachable, the accepted job transitions to `failed` with a clear error while the API process remains healthy.

## API

### Public endpoints

```text
GET /health
GET /spec
```

### Bearer-protected endpoints

```text
POST /v1/reviews
GET  /v1/reviews/{jobId}
GET  /v1/reviews/{jobId}/stream
```

Example submission:

```powershell
$headers = @{
    Authorization = "Bearer $env:BEARER_TOKEN"
}

$body = @{
    diff = (Get-Content -Raw example.diff)
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri http://localhost:8000/v1/reviews `
    -Headers $headers `
    -ContentType application/json `
    -Body $body
```

## Asynchronous processing

A successful submission returns `202` with a queued job.

Review processing happens asynchronously through four internal workers.

Jobs transition through:

```text
queued
  ↓
running
  ↓
done
```

or:

```text
queued
  ↓
running
  ↓
failed
```

Clients can observe the job through polling or the SSE stream.

## Chunking and ordering

Diffs larger than 64 KiB are split only on file boundaries.

A file's diff is never split across multiple chunks. A single file larger than 64 KiB is processed as its own oversized chunk.

Provider findings are normalized globally and then:

1. deduplicated by finding ID;
2. sorted lexicographically by path;
3. sorted by ascending line within each path;
4. sorted by `ruleId` for findings sharing the same path and line.

`maxFindings` is applied only after the full result has been globally ordered.

## Caching and idempotency

Caching and idempotency intentionally use different identities.

The canonical `{diff, options}` content determines cache reuse.

The raw request bytes determine idempotency behavior.

For an `Idempotency-Key`:

- the same key with identical raw request bytes returns the original job;
- the same key with different raw request bytes returns `409`;
- different keys may still reuse the same canonical cached review.

Cache entries contain the complete ordered scan. Per-job `maxFindings` truncation is applied afterward.

## SSE durability and replay

SSE events are persisted in PostgreSQL rather than existing only in process memory.

Each event receives a per-job sequence number.

This allows completed streams to be replayed deterministically and preserves event history across application restarts.

## Rate limiting

Rate limiting applies only to:

```text
POST /v1/reviews
```

The service uses an in-process rolling 60-second window with a limit of 30 submissions.

An excess submission receives:

```text
HTTP 429 Too Many Requests
```

with:

- the required error envelope; and
- a positive `Retry-After` header.

Protected GET routes are not rate limited.

The deployment intentionally uses one FastAPI application process so the four-worker queue and in-process rate limiter have a single authority.

Before horizontally scaling the API, the rate-limit state would need to move to shared infrastructure such as Redis or PostgreSQL.

## Verification

Local quality and test checks:

```powershell
uv run ruff check .
uv run ty check
uv run pytest -q
```

The local suite covers:

- unified-diff parsing and new-file line tracking;
- all deterministic mock rules;
- prompt-injection inertness;
- file-boundary chunking;
- authentication;
- validation and error taxonomy;
- raw-byte idempotency;
- canonical cache reuse;
- global finding ordering;
- `maxFindings`;
- SSE persistence and replay;
- concurrency behavior; and
- graceful LLM failure.

### Bruno black-box tests

A ready-to-run Bruno collection is available under:

```text
tests/bruno
```

The same collection is executed against the deployed Koyeb service through GitHub Actions.

Environment files contain placeholders only. The production bearer token is injected through GitHub Actions secrets and is never committed to the repository.

The cloud suite verifies:

- public discovery endpoints;
- bearer authentication;
- asynchronous submission and polling;
- all deterministic mock findings;
- validation and error envelopes;
- idempotency;
- caching;
- SSE streaming and completed-stream replay;
- file-boundary chunking;
- the real Cerebras LLM path;
- five-job concurrency; and
- a concurrent 31-request rate-limit burst.

The rate-limit probe verifies that 30 immediate POST submissions are accepted, the excess submission receives `429` with `Retry-After`, and protected GET routes remain available.

## Production

Run one application process:

```powershell
fastapi run --host 0.0.0.0 --port 8000
```

The production deployment runs on Koyeb with Supabase PostgreSQL.

Public Docker image:

```text
kill3rstabs/ai-diff-review-service:latest
```

PostgreSQL provides durable storage for jobs, cache entries, idempotency records, and SSE events across application restarts.

Deployment credentials, database credentials, the Cerebras API key, and the bearer token are supplied through deployment secrets and are not stored in the repository or Docker image.