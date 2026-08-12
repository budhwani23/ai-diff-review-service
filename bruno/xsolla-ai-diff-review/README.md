# Bruno collection

Open this directory as a collection in Bruno, select either the `Local` or
`Koyeb` environment, and replace `replace-with-your-bearer-token` in Bruno's
environment editor. Do not commit the real token.

Run the numbered folders in order. `Submit mock review` and `Submit LLM
review` save their returned job IDs as runtime variables. Wait briefly before
running the corresponding poll or stream request because processing is
asynchronous.

The idempotency pair uses the same key and byte-identical body. Run request 1
and then request 2; both responses should contain the same job ID. The cache
pair uses the same canonical request without an idempotency key. Wait for the
first job to finish before submitting the second, then poll the second job and
confirm `usage.cacheHit` is `true`.

The collection never stores database or Cerebras credentials. Only the API
bearer token is needed by the client.
