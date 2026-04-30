from __future__ import annotations

import uuid

import pytest

from the_black_goat import build_registry
from the_black_goat.config import DictConfigSource


@pytest.fixture
def memory_registry(pg_url):
    """Registry with the memory plugin's tools resolved against the test DB."""
    config_source = DictConfigSource({"memory": {"database_url": pg_url}})
    return build_registry(config_source=config_source)


@pytest.fixture
def ns() -> str:
    """Unique namespace per test for isolation."""
    return f"test_{uuid.uuid4().hex[:8]}"


class TestMemoryPut:
    def test_put_returns_written_at(self, memory_registry, ns):
        result = memory_registry.invoke(
            "memory.put",
            {"namespace": ns, "key": "alpha", "value": {"hi": 1}},
        )
        assert "written_at" in result

    def test_put_persists_value_readable_via_psycopg(
        self, memory_registry, ns, pg_url
    ):
        memory_registry.invoke(
            "memory.put",
            {"namespace": ns, "key": "alpha", "value": {"answer": 42}},
        )
        from psycopg import Connection
        from psycopg.rows import dict_row

        with Connection.connect(pg_url) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT value FROM goat_memory.kv WHERE namespace=%s AND key=%s",
                    (ns, "alpha"),
                )
                row = cur.fetchone()
        assert row is not None
        assert row["value"] == {"answer": 42}

    def test_put_upserts_overwrites_value(self, memory_registry, ns):
        memory_registry.invoke(
            "memory.put",
            {"namespace": ns, "key": "alpha", "value": {"v": 1}},
        )
        memory_registry.invoke(
            "memory.put",
            {"namespace": ns, "key": "alpha", "value": {"v": 2}},
        )

        from psycopg import Connection
        from psycopg.rows import dict_row

        with Connection.connect(memory_registry._configs["memory.put"].database_url.get_secret_value()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT value, count(*) OVER () AS n "
                    "FROM goat_memory.kv WHERE namespace=%s AND key=%s",
                    (ns, "alpha"),
                )
                rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0]["value"] == {"v": 2}

    def test_put_via_attribute_proxy(self, memory_registry, ns):
        result = memory_registry.memory.put(
            {"namespace": ns, "key": "via-proxy", "value": {"ok": True}}
        )
        assert "written_at" in result

    def test_put_validates_input(self, memory_registry, ns):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            memory_registry.invoke(
                "memory.put",
                {"namespace": ns, "key": "", "value": {}},  # empty key
            )

    def test_put_distinct_keys_independent(self, memory_registry, ns):
        memory_registry.memory.put(
            {"namespace": ns, "key": "a", "value": {"v": 1}}
        )
        memory_registry.memory.put(
            {"namespace": ns, "key": "b", "value": {"v": 2}}
        )

        from psycopg import Connection
        from psycopg.rows import dict_row

        url = memory_registry._configs["memory.put"].database_url.get_secret_value()
        with Connection.connect(url) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT key, value FROM goat_memory.kv WHERE namespace=%s ORDER BY key",
                    (ns,),
                )
                rows = cur.fetchall()
        assert [(r["key"], r["value"]) for r in rows] == [
            ("a", {"v": 1}),
            ("b", {"v": 2}),
        ]
