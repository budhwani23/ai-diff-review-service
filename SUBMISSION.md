# Submission

## Architecture

The service runs as one FastAPI process backed by PostgreSQL. `POST /v1/reviews` validates and parses the raw request, persists a queued job and its first SSE event, and returns `202`. Four internal asynchronous workers claim queued jobs using `FOR UPDATE SKIP LOCKED`. Each job passes through unified-diff parsing, file-boundary chunking, one review provider, global normalization, deduplication and ordering, result persistence, and durable SSE event creation. PostgreSQL stores jobs, cache entries, idempotency records, and event history; all service-owned tables use the `xsolla_` prefix. On startup, abandoned `running` jobs are returned to the queue. One API process is deliberate: it gives the declared four-worker queue and in-process rate limiter a single authority while PostgreSQL provides restart durability.

## Provider design

`ReviewProvider` is the shared asynchronous provider boundary.

`MockProvider` is deterministic Python and scans added lines only. It implements every published mock rule without involving a model, including multiline empty-catch detection and inert prompt-injection reporting.

`CerebrasProvider` is a bounded LangGraph `StateGraph`. It fans parsed chunks out to `ChatCerebras`, requests strict Pydantic structured output, and validates proposed findings against the paths and added line numbers actually present in each chunk.

The graph has no tools and no recursive agent loop.

Cerebras credentials live only in `CEREBRAS_API_KEY`. A missing key, timeout, provider outage, or invalid model response causes the already-accepted job to transition clearly to `failed` without crashing the API process.

The deterministic mock path intentionally does not use LangGraph or an LLM.

## Cross-cutting behavior and verification

The implementation is verified locally and through black-box tests against the deployed Koyeb service.

### Chunking

Unit and API tests verify file-only chunk boundaries, oversized single-file chunks, multi-chunk usage, no finding loss, and deterministic global ordering independent of input file order.

Diffs over 64 KiB are split only at file boundaries. A single file larger than the chunk limit remains one oversized chunk.

### Caching

The canonical `{diff, options}` content determines cache identity.

The first job for a canonical request owns the cache entry. Later equivalent jobs wait for or reuse the complete globally ordered scan and report `cacheHit: true`.

`maxFindings` truncation is applied per job only after the full cached result has been globally ordered.

### Idempotency

Idempotency is intentionally independent from caching.

Raw request bytes are hashed for each `Idempotency-Key`.

A repeated key with identical raw bytes returns the original job ID. Reusing the same key with different raw bytes returns `409`.

Different idempotency keys can still reuse the same canonical cache entry.

### SSE replay

Every SSE event is persisted with a per-job sequence number.

Tests connect to a completed job multiple times and verify byte-identical replay, including ordered findings and the terminal `done` event.

Because events are stored in PostgreSQL, completed stream history survives application restarts.

### Concurrency

Four internal asynchronous workers process jobs concurrently.

Tests verify that four jobs can be processing while a fifth remains safely queued and subsequently completes rather than failing under load.

### Rate limiting

`POST /v1/reviews` uses an in-process rolling 60-second rate limiter with a limit of 30 submissions.

A black-box concurrent burst against the deployed service verifies that 30 immediate POST submissions are accepted and the excess submission returns the required `429`, positive `Retry-After` header, and error envelope.

Protected GET routes remain available after the POST submission limit is exhausted.

The rate limiter is intentionally process-local because the submitted deployment uses one FastAPI application process. Before horizontal API scaling, I would move this state into Redis or PostgreSQL.

### Failure behavior

The LLM route fails at job level rather than server level.

Missing credentials, provider failures, timeouts, or invalid model responses transition the accepted job to `failed` with a clear error while the FastAPI service remains healthy.

The deployed Cerebras path was also tested successfully with real structured model output.

### Persistence and restart behavior

Jobs, cache entries, idempotency records, and SSE events are persisted in PostgreSQL.

On application startup, abandoned jobs left in `running` state are returned to the queue so work can resume after process termination or deployment.

All service-owned tables use the required `xsolla_` prefix.

## Verification commands

Local verification:

```text
uv run ruff check .
uv run ty check
uv run pytest -q
```

The repository also contains `scripts/remote_smoke.py` for black-box verification against the public deployment.

The GitHub Actions Bruno suite independently tests the deployed service and covers the deterministic contract, Cerebras LLM provider path, five-job concurrency, and concurrent 31-request rate-limit probe.

The full enabled cloud assessment suite passes against the deployed Koyeb service.

## AI tools used

I used OpenAI Codex to interpret the contract, challenge architecture choices, scaffold parts of the FastAPI implementation, create test cases, and iterate on lint, type-checking, and test failures.

I reviewed generated behavior against the published contract rather than treating generated code as authoritative. Deterministic scoring behavior remains directly implemented and testable instead of being hidden behind model prompts.

AI assistance was also used to challenge cross-cutting behavior such as caching, idempotency, rate limiting, concurrency, and deployment verification. Suggestions were accepted only when they preserved or improved the externally observable contract.

## AI suggestions rejected

An early suggestion was to use LangGraph as the orchestration layer for both providers.

I rejected that for the mock path. The scored mock provider needs to be deterministic, transparent, directly testable, and independent of model or orchestration-framework behavior.

LangGraph is therefore restricted to the optional Cerebras provider. The shared application pipeline owns parsing, chunking, caching, normalization, ordering, persistence, and streaming.

I also rejected using an in-memory queue and SQLite for the deployed implementation.

Those choices simplify a demo but would lose queued jobs, cache entries, idempotency records, and persisted SSE replay state when the application process restarts.

PostgreSQL makes those guarantees durable and enables explicit row-lock-based worker claiming with `FOR UPDATE SKIP LOCKED`.

## What I would do next

With more time, I would:

- move rate-limit state into Redis or PostgreSQL before horizontally scaling the API;
- add retention policies for old jobs, raw diffs, cache entries, and SSE events;
- encrypt submitted diffs at rest and add structured audit logging;
- add production metrics for queue depth, job latency, cache-hit rate, provider latency, failures, and rate-limit events;
- replace short database polling with a transactional outbox or notification mechanism;
- run additional fault-injection tests against worker termination, process restart, and PostgreSQL/Supabase connectivity;
- add model-quality evaluation fixtures for the LLM provider; and
- add provider token, latency, and cost telemetry.

## Deployment and remote verification

Public base URL:

```text
https://notable-lu-bnb-b26373f0.koyeb.app
```

Public health endpoint:

```text
https://notable-lu-bnb-b26373f0.koyeb.app/health
```

Repository:

```text
https://github.com/budhwani23/ai-diff-review-service
```

Public Docker image:

```text
kill3rstabs/ai-diff-review-service:latest
```

Runtime:

```text
One Koyeb FastAPI replica backed by Supabase PostgreSQL
```

Deployment credentials, database credentials, the Cerebras API key, and the bearer token are injected as deployment secrets and are not stored in the repository or Docker image.

The bearer token is intentionally supplied separately in the submission email.

### Remote verification

The repository's `scripts/remote_smoke.py` suite passed against the public deployment. It verifies:

- public health and specification responses;
- bearer authentication;
- asynchronous submission and polling;
- exact deterministic mock findings;
- raw-byte idempotency;
- cross-key cache reuse; and
- byte-identical replay of a completed SSE stream.

The GitHub Actions Bruno black-box suite also passes against the deployed Koyeb service. It independently exercises:

- the deterministic API contract;
- authentication and validation;
- deterministic mock-provider behavior;
- caching and idempotency;
- SSE behavior;
- the configured Cerebras LLM path;
- five-job concurrency; and
- a concurrent 31-request rate-limit burst.

Additional black-box verification against the public deployment confirmed:

- malformed JSON returns the required `400 invalid_json` envelope;
- an unknown job returns `404 not_found`;
- a 150 KB three-file diff is split into three file-boundary chunks while preserving all expected findings;
- the configured Cerebras `llm` provider completes successfully with structured findings;
- unauthenticated `/v1` access returns `401 unauthorized`;
- `/health` remains publicly accessible over HTTPS; and
- the rate-limit probe accepts 30 immediate POST submissions and rejects the excess submission with `429` and `Retry-After`.

The service is live before submission and exposes a public `/health` endpoint. The bearer token is intentionally supplied only through the submission communication and is not committed to the repository.