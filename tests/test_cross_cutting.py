import time
from collections.abc import Iterator
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.test_api_contract import wait_for_terminal


def unique_diff(marker: int) -> str:
    return f"""--- a/src/file-{marker}.ts
+++ b/src/file-{marker}.ts
@@ -0,0 +1,1 @@
+console.log({marker});
"""


def delayed_client(tmp_path: Path, token: str) -> Iterator[TestClient]:
    database_path = (tmp_path / "concurrency.db").as_posix()
    settings = Settings(
        bearer_token=token,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        worker_poll_seconds=0.01,
        mock_processing_delay_ms=300,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def test_rate_limit_allows_declared_burst(
    client: TestClient,
    auth: dict[str, str],
) -> None:
    responses = [
        client.post("/v1/reviews", headers=auth, json={"diff": unique_diff(index)})
        for index in range(31)
    ]
    assert all(response.status_code == 202 for response in responses[:30])
    assert responses[30].status_code == 429
    assert responses[30].json()["error"]["code"] == "rate_limited"
    assert int(responses[30].headers["Retry-After"]) >= 1


def test_four_jobs_run_and_fifth_queues(tmp_path: Path, token: str) -> None:
    auth = {"Authorization": f"Bearer {token}"}
    for client in delayed_client(tmp_path, token):
        job_ids = [
            client.post("/v1/reviews", headers=auth, json={"diff": unique_diff(index)}).json()[
                "jobId"
            ]
            for index in range(5)
        ]
        deadline = time.monotonic() + 2
        statuses: list[str] = []
        while time.monotonic() < deadline:
            statuses = [
                client.get(f"/v1/reviews/{job_id}", headers=auth).json()["status"]
                for job_id in job_ids
            ]
            if statuses.count("running") == 4 and statuses.count("queued") == 1:
                break
            time.sleep(0.01)
        assert statuses.count("running") == 4
        assert statuses.count("queued") == 1
        for job_id in job_ids:
            assert wait_for_terminal(client, job_id, auth)["status"] == "done"


def test_file_boundary_chunking_and_global_order(
    client: TestClient,
    auth: dict[str, str],
) -> None:
    padding = "x" * 39_000
    diff = f"""diff --git a/z.ts b/z.ts
--- a/z.ts
+++ b/z.ts
@@ -0,0 +1,2 @@
+const padding = "{padding}";
+console.log("z");
diff --git a/a.ts b/a.ts
--- a/a.ts
+++ b/a.ts
@@ -0,0 +1,2 @@
+const padding = "{padding}";
+console.log("a");
"""
    submit = client.post("/v1/reviews", headers=auth, json={"diff": diff})
    assert submit.status_code == 202
    result = wait_for_terminal(client, submit.json()["jobId"], auth)
    assert result["usage"]["chunks"] == 2
    assert [(item["path"], item["line"]) for item in result["findings"]] == [
        ("a.ts", 2),
        ("z.ts", 2),
    ]


def test_max_findings_truncates_after_ordering(
    client: TestClient,
    auth: dict[str, str],
) -> None:
    diff = """--- a/b.ts
+++ b/b.ts
@@ -0,0 +1,2 @@
+console.log(1); // TODO
+console.log(2);
"""
    submit = client.post(
        "/v1/reviews",
        headers=auth,
        json={"diff": diff, "options": {"provider": "mock", "maxFindings": 2}},
    )
    result = wait_for_terminal(client, submit.json()["jobId"], auth)
    assert [(item["line"], item["ruleId"]) for item in result["findings"]] == [
        (1, "MOCK-007"),
        (1, "MOCK-008"),
    ]
