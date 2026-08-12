import json
import os
import time

import httpx

BASE_URL = os.environ["BASE_URL"].rstrip("/")
TOKEN = os.environ["BEARER_TOKEN"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
DIFF = """--- a/src/smoke.ts
+++ b/src/smoke.ts
@@ -0,0 +1,2 @@
+console.log("smoke");
+// TODO remove
"""


def wait_for_done(client: httpx.Client, job_id: str) -> dict:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get(f"/v1/reviews/{job_id}", headers=HEADERS)
        response.raise_for_status()
        payload = response.json()
        if payload["status"] == "done":
            return payload
        if payload["status"] == "failed":
            raise RuntimeError(payload)
        time.sleep(0.1)
    raise TimeoutError("Review did not finish within 30 seconds")


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=35) as client:
        health = client.get("/health")
        health.raise_for_status()
        assert health.json()["status"] == "ok"
        spec = client.get("/spec")
        spec.raise_for_status()
        assert spec.json()["specVersion"] == "1.0"

        unauthorized = client.get("/v1/reviews/unknown")
        assert unauthorized.status_code == 401
        assert unauthorized.json()["error"]["code"] == "unauthorized"

        body = json.dumps({"diff": DIFF}, separators=(",", ":")).encode()
        idem_headers = {
            **HEADERS,
            "Content-Type": "application/json",
            "Idempotency-Key": "remote-smoke-v1",
        }
        first = client.post("/v1/reviews", headers=idem_headers, content=body)
        first.raise_for_status()
        replay = client.post("/v1/reviews", headers=idem_headers, content=body)
        replay.raise_for_status()
        assert replay.json()["jobId"] == first.json()["jobId"]

        result = wait_for_done(client, first.json()["jobId"])
        assert [item["ruleId"] for item in result["findings"]] == ["MOCK-007", "MOCK-008"]

        stream_path = f"/v1/reviews/{first.json()['jobId']}/stream"
        stream_one = client.get(stream_path, headers=HEADERS)
        stream_two = client.get(stream_path, headers=HEADERS)
        assert stream_one.content == stream_two.content
        assert b"event: done" in stream_one.content

        cached = client.post(
            "/v1/reviews",
            headers={**HEADERS, "Content-Type": "application/json"},
            content=body,
        )
        cached.raise_for_status()
        cached_result = wait_for_done(client, cached.json()["jobId"])
        assert cached_result["usage"]["cacheHit"] is True
        assert cached_result["findings"] == result["findings"]

    print("Remote contract smoke test passed.")


if __name__ == "__main__":
    main()
