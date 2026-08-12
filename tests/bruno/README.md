# Xsolla AI Diff Review — Bruno test collection

This collection targets:

`https://notable-lu-bnb-b26373f0.koyeb.app`

## Before running

1. Open this folder directly in Bruno.
2. Select the **Koyeb** environment.
3. Open the Koyeb environment and replace `replace-with-your-bearer-token` with the actual `BEARER_TOKEN` configured in Koyeb.
4. Never commit the real bearer token.

## Recommended run order

Run folders **01 through 09** in order. They cover the normal contract without intentionally exhausting the rate limiter.

The `10 Manual stress` folder is intentionally separate:

- Run **Concurrency burst** first.
- For **Rate limit 31 POST burst**, avoid sending any other POST `/v1/reviews` requests for about a minute beforehand. The test expects the service's token bucket to be full so the first 30 submissions succeed and the 31st returns 429.
- After the rate-limit test, allow the bucket to refill before running more POST tests.

## Async polling

The polling requests accept `queued` / `running` while used manually. When run through Bruno's collection runner, the polling requests use `bru.runner.setNextRequest(...)` to retry themselves until the job becomes terminal (bounded to avoid an infinite runner loop).

## Coverage

- public `/health` and `/spec`
- bearer auth on protected GET and POST routes
- async mock submission + polling
- all nine deterministic mock rules
- finding schema, line numbers, ordering and prompt-injection inertness
- SSE stream and byte-equivalent replay of a finished job
- raw-byte idempotency and 409 conflict behavior
- canonical cache reuse and `cacheHit: true`
- malformed JSON, invalid/empty/missing diff, unknown job, ignored body fields
- payload > 1 MiB
- `maxFindings` after global ordering
- file-boundary chunking and an oversized single-file chunk
- optional LLM path, accepting either `done` or graceful `failed`
- five-request burst acceptance
- 30/minute token-bucket burst + 429 / `Retry-After`

## Notes

The collection never uploads a `.diff` file as multipart data. `/v1/reviews` is tested exactly as specified: JSON with the unified diff text in the `diff` property.
