from __future__ import annotations

import os
import uuid

import pytest

DEFAULT_PG_URL = os.environ.get(
    "TEST_PG_URL",
    "postgresql://absurd:absurd@localhost:5432/absurd",
)


@pytest.fixture
def pg_url() -> str:
    """Provides the test Postgres URL. Skips the test if the DB is unreachable."""
    try:
        from psycopg import Connection

        Connection.connect(DEFAULT_PG_URL, connect_timeout=2).close()
    except Exception as exc:
        pytest.skip(f"Postgres not reachable at {DEFAULT_PG_URL}: {exc}")
    return DEFAULT_PG_URL


@pytest.fixture
def absurd_app(pg_url: str):
    """Per-test Absurd client on a unique queue. Drops the queue at teardown."""
    from absurd_sdk import Absurd

    queue = f"goattest_{uuid.uuid4().hex[:8]}"
    app = Absurd(pg_url, queue_name=queue)
    app.create_queue(queue)
    try:
        yield app
    finally:
        try:
            app.drop_queue(queue)
        except Exception:
            pass
