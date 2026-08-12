# Manual notes

## Bearer token

The Koyeb environment intentionally contains a placeholder. Paste the deployment's `BEARER_TOKEN` into Bruno locally.

## SSE

If you want to double-check SSE outside Bruno:

```bash
curl -N -H "Authorization: Bearer YOUR_TOKEN" \
  "https://notable-lu-bnb-b26373f0.koyeb.app/v1/reviews/JOB_ID/stream"
```

## Important rate-limit warning

The 31-request burst is meaningful only when the server's POST rate-limit bucket starts full. Run it after a quiet period, and do not immediately rerun the main POST test set afterward.
