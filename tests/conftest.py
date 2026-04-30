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


@pytest.fixture
def clean_cron_jobs(pg_url):
    """Clear any goat:* cron.job entries before and after the test."""
    from psycopg import Connection

    def _clear():
        with Connection.connect(pg_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT jobname FROM cron.job WHERE jobname LIKE 'goat:%'"
                )
                for (jobname,) in cur.fetchall():
                    cur.execute("SELECT cron.unschedule(%s)", (jobname,))

    _clear()
    yield
    _clear()


@pytest.fixture
def background_worker(absurd_app):
    """Run absurd_app.work_batch() in a thread so invoke() on a durable
    tool (which spawns + awaits in the same call) actually completes."""
    import threading
    import time

    stop = threading.Event()

    def _loop():
        while not stop.is_set():
            try:
                absurd_app.work_batch()
            except Exception:
                pass
            time.sleep(0.02)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join(timeout=2)
