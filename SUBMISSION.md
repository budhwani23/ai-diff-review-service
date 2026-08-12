# Submission

## Architecture

The service is one FastAPI process backed by PostgreSQL. A POST validates and parses the raw request, persists a queued job and its first SSE event, and returns `202`. Four internal asynchronous workers claim jobs with `FOR UPDATE SKIP LOCKED`. Each job passes through unified-diff parsing, file-boundary chunking, one provider, global deduplication and ordering, result persistence, and durable SSE event creation. PostgreSQL stores jobs, cache entries, idempotency records, and event history; all service-owned tables are prefixed `xsolla_`. On startup, abandoned running jobs are returned to the queue. One API process is deliberate: it gives the declared four-worker queue and rate limiter a single authority while PostgreSQL provides restart durability.

## Provider design

`ReviewProvider` is the shared asynchronous boundary. `MockProvider` is pure deterministic Python and scans added lines only. It implements every published rule without involving a model, including multiline empty catch detection and inert prompt-injection reporting. `CerebrasProvider` is a bounded LangGraph `StateGraph`: it fans parsed chunks out to `ChatCerebras`, requests strict Pydantic structured output, and rejects any proposed path or line not present among the chunk's actual added lines. The graph has no tools or recursive agent loop. Cerebras credentials live only in `CEREBRAS_API_KEY`; a missing key, timeout, provider outage, or invalid response makes the accepted job fail clearly without crashing the server.

## Cross-cutting behavior and verification

The local suite currently contains 18 passing tests, plus clean Ruff and ty checks.

- Chunking: unit and API tests verify file-only boundaries, oversized single files, multi-chunk usage, no finding loss, and global ordering independent of input file order.
- Caching: the first canonical `{diff, options}` hash owns a cache entry; later jobs wait for or copy the full ordered scan and report `cacheHit: true`. Truncation is applied per job after the full cached scan.
- Idempotency: the raw request bytes are hashed independently of the cache key. A repeated key and identical bytes return the original job ID; different bytes return `409`.
- SSE replay: every event has a persisted per-job sequence. Tests connect twice to a completed job and compare the response bytes, including ordered findings and the terminal `done` event.
- Concurrency: an intentional processing delay proves four jobs can be `running` while a fifth remains `queued` and later completes.
- Rate limiting: 30 immediate POST submissions succeed; the next returns the required `429`, `Retry-After`, and error envelope. GET routes are outside the limiter.
- Failure behavior: the LLM route is tested without credentials and reaches a clear `failed` job instead of producing a server error.
- Production path: the Docker image, Alembic migration, PostgreSQL JSONB persistence, and remote-style HTTP smoke suite pass together against PostgreSQL 17. The resulting schema contains only `xsolla_`-prefixed service tables.

Commands used:

```text
uv run ruff check .
uv run ty check
uv run pytest -q
```

After deployment, `scripts/remote_smoke.py` repeats health, spec, authentication, idempotency, polling, exact mock findings, cache-hit, and byte-identical SSE replay checks against the public base URL.

## AI tools used

I used OpenAI Codex to interpret the contract, challenge architecture choices, scaffold the FastAPI implementation, create test cases, and iterate on lint/type/test failures. I reviewed the generated behavior against the published contract and kept deterministic scoring logic directly testable rather than hidden behind generated prompts.

## AI suggestion rejected

An early suggestion was to use LangGraph as the orchestration layer for both providers. I rejected that for the mock path: the scored provider must be deterministic, transparent, and independent of model/framework behavior. LangGraph is therefore restricted to the optional Cerebras provider, while the shared application pipeline owns parsing, chunking, caching, ordering, and streaming.

I also rejected using an in-memory queue and SQLite for deployment. They simplify a demo but lose jobs, cache entries, idempotency records, and SSE replay on restart. PostgreSQL makes those guarantees durable and makes row-lock-based worker claiming explicit.

## What I would do next

- Move rate-limit state into Redis or PostgreSQL before horizontally scaling the API.
- Add retention policies for old jobs, raw diffs, and SSE events.
- Encrypt submitted diffs at rest and add structured audit logging and metrics.
- Add a transactional outbox/notification mechanism to replace short database polling.
- Run fault-injection tests against worker termination and Supabase connectivity.
- Add model-quality evaluation fixtures and provider cost/token telemetry for the LLM path.

## Deployment verification

To be completed immediately before submission:

- Public base URL: `PENDING`
- Repository URL: `PENDING`
- Remote mock smoke test: `PENDING`
- Remote Cerebras success test: `PENDING`
- Monitoring confirmed for the full 96-hour window: `PENDING`
