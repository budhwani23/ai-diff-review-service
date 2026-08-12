from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def token() -> str:
    return "test-bearer-token"


@pytest.fixture
def client(tmp_path: Path, token: str) -> Iterator[TestClient]:
    database_path = (tmp_path / "reviews.db").as_posix()
    settings = Settings(
        bearer_token=token,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        worker_poll_seconds=0.01,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def simple_diff() -> str:
    return """diff --git a/src/app.ts b/src/app.ts
index 1111111..2222222 100644
--- a/src/app.ts
+++ b/src/app.ts
@@ -1,2 +1,3 @@
 const value = 1;
+console.log(value);
+// TODO remove this
 export { value };
"""
