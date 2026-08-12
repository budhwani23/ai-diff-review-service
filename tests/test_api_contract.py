import json
import time

from fastapi.testclient import TestClient


def wait_for_terminal(client: TestClient, job_id: str, auth: dict[str, str]) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/v1/reviews/{job_id}", headers=auth)
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"done", "failed"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("job did not complete")


def test_public_contract(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["version"] == "1.0.0"
    assert isinstance(health.json()["uptimeSeconds"], (int, float))

    spec = client.get("/spec")
    assert spec.status_code == 200
    assert spec.json() == {
        "specVersion": "1.0",
        "providers": ["mock", "llm"],
        "limits": {
            "maxPayloadBytes": 1_048_576,
            "chunkBytes": 65_536,
            "maxConcurrentJobs": 4,
            "rateLimitPerMinute": 30,
        },
    }


def test_authentication_protects_all_v1_paths(client: TestClient) -> None:
    for method, path in [
        ("post", "/v1/reviews"),
        ("get", "/v1/reviews/missing"),
        ("get", "/v1/reviews/missing/stream"),
        ("get", "/v1/not-a-route"),
    ]:
        response = getattr(client, method)(path)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


def test_submit_poll_order_and_usage(
    client: TestClient,
    auth: dict[str, str],
    simple_diff: str,
) -> None:
    response = client.post("/v1/reviews", headers=auth, json={"diff": simple_diff})
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    result = wait_for_terminal(client, response.json()["jobId"], auth)
    assert result["status"] == "done"
    assert [finding["ruleId"] for finding in result["findings"]] == ["MOCK-007", "MOCK-008"]
    assert result["usage"] == {
        "inputBytes": len(simple_diff.encode("utf-8")),
        "chunks": 1,
        "cacheHit": False,
    }


def test_error_taxonomy(client: TestClient, auth: dict[str, str]) -> None:
    invalid_json = client.post(
        "/v1/reviews",
        headers={**auth, "Content-Type": "application/json"},
        content=b"{",
    )
    assert invalid_json.status_code == 400
    assert invalid_json.json()["error"]["code"] == "invalid_json"

    invalid_diff = client.post("/v1/reviews", headers=auth, json={"diff": "hello"})
    assert invalid_diff.status_code == 422
    assert invalid_diff.json()["error"]["code"] == "invalid_diff"

    not_found = client.get("/v1/reviews/unknown", headers=auth)
    assert not_found.status_code == 404
    assert not_found.json()["error"]["code"] == "not_found"

    oversized = client.post(
        "/v1/reviews",
        headers={**auth, "Content-Type": "application/json"},
        content=json.dumps({"diff": "x" * 1_048_576}),
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "payload_too_large"


def test_idempotency_and_cache(
    client: TestClient,
    auth: dict[str, str],
    simple_diff: str,
) -> None:
    body = json.dumps({"diff": simple_diff}, separators=(",", ":")).encode()
    headers = {**auth, "Content-Type": "application/json", "Idempotency-Key": "same-key"}
    first = client.post("/v1/reviews", headers=headers, content=body)
    second = client.post("/v1/reviews", headers=headers, content=body)
    assert first.status_code == second.status_code == 202
    assert first.json()["jobId"] == second.json()["jobId"]

    conflict = client.post(
        "/v1/reviews",
        headers=headers,
        json={"diff": simple_diff, "options": {"maxFindings": 1}},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"

    original = wait_for_terminal(client, first.json()["jobId"], auth)
    cached_submission = client.post("/v1/reviews", headers=auth, content=body)
    cached = wait_for_terminal(client, cached_submission.json()["jobId"], auth)
    assert cached["usage"]["cacheHit"] is True
    assert cached["findings"] == original["findings"]


def test_finished_sse_replays_identically(
    client: TestClient,
    auth: dict[str, str],
    simple_diff: str,
) -> None:
    submit = client.post("/v1/reviews", headers=auth, json={"diff": simple_diff})
    job_id = submit.json()["jobId"]
    wait_for_terminal(client, job_id, auth)
    first = client.get(f"/v1/reviews/{job_id}/stream", headers=auth)
    second = client.get(f"/v1/reviews/{job_id}/stream", headers=auth)
    assert first.status_code == second.status_code == 200
    assert first.headers["content-type"].startswith("text/event-stream")
    assert first.content == second.content
    text = first.text
    assert "event: status" in text
    assert text.count("event: finding") == 2
    assert "event: done" in text


def test_unconfigured_llm_fails_gracefully(
    client: TestClient,
    auth: dict[str, str],
    simple_diff: str,
) -> None:
    submit = client.post(
        "/v1/reviews",
        headers=auth,
        json={"diff": simple_diff, "options": {"provider": "llm"}},
    )
    assert submit.status_code == 202
    result = wait_for_terminal(client, submit.json()["jobId"], auth)
    assert result["status"] == "failed"
    assert result["error"]["code"] == "internal"
    assert "Cerebras is not configured" in result["error"]["message"]
