# Xsolla Cloud Test Setup

This package runs the Bruno assessment suite from a GitHub-hosted runner against:

`https://notable-lu-bnb-b26373f0.koyeb.app`

The bearer token is **not stored in the repository**. GitHub injects it at runtime from a repository secret.

## 1. Copy these folders into the root of your repository

```text
.github/
tests/
```

After copying, your repository should contain:

```text
.github/workflows/xsolla-cloud-tests.yml
tests/bruno/bruno.json
tests/bruno/environments/Koyeb.bru
...
```

## 2. Add your bearer token as a GitHub Actions secret

In GitHub:

1. Open the repository.
2. Go to **Settings**.
3. Open **Secrets and variables** -> **Actions**.
4. Click **New repository secret**.
5. Name it exactly `BEARER_TOKEN`.
6. Paste the same bearer token configured on your deployed Koyeb service.
7. Save it.

Do not add `Bearer ` to the secret value. Store only the token itself. Bruno adds the `Bearer` scheme in the Authorization header.

## 3. Commit and push

Commit `.github/` and `tests/` to your repository.

Do **not** commit your local `.env` file or any model/API credentials.

## 4. Run the cloud test

1. Open the repository's **Actions** tab.
2. Select **Xsolla Cloud API Tests**.
3. Click **Run workflow**.
4. Leave **Run the real LLM provider test** enabled if you want to verify the LLM path.
5. Leave **Run concurrency and rate-limit tests** enabled for the full assessment-style run.
6. Click **Run workflow**.

The workflow intentionally waits 70 seconds before the rate-limit probe. This avoids earlier POST tests consuming the 30-requests/minute allowance.

## 5. Read the result

At the bottom of the workflow run, GitHub shows a summary table for:

- Deterministic contract tests
- LLM provider
- Five-job concurrency
- 31-request rate limiting

A green workflow means every enabled suite passed. A red workflow means at least one enabled suite failed.

The workflow also uploads an artifact named similar to:

`bruno-cloud-test-reports-123456789`

Download it to inspect `core.html`, `llm.html`, `concurrency.html`, and `rate-limit.html`, plus JSON and JUnit reports.

## Security notes

- `BEARER_TOKEN` lives in GitHub Secrets and is injected with Bruno's `--env-var` option.
- The workflow strips the `Authorization` header from generated Bruno reports.
- Never commit `.env`.
- If a token/API key has ever been pushed to GitHub, rotate it instead of merely deleting the file in a later commit.
