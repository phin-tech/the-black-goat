from __future__ import annotations

import uuid

import pytest

from the_black_goat import build_registry
from the_black_goat.config import DictConfigSource


@pytest.fixture
def memory_registry(pg_url):
    """Registry with the memory plugin's tools resolved against the test DB."""
    import memory_plugin

    config_source = DictConfigSource({"memory": {"database_url": pg_url}})
    return build_registry(
        plugins={"memory": memory_plugin},
        config_source=config_source,
    )


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


class TestMemoryGet:
    def test_get_returns_stored_value_and_written_at(self, memory_registry, ns):
        put_result = memory_registry.memory.put(
            {"namespace": ns, "key": "alpha", "value": {"answer": 42}}
        )
        got = memory_registry.memory.get({"namespace": ns, "key": "alpha"})
        assert got["value"] == {"answer": 42}
        # written_at round-trips through Pydantic — it'll be an isoformat string
        # on the dict surface; just confirm it's present and matches the put.
        assert got["written_at"] == put_result["written_at"]

    def test_get_missing_returns_none_pair(self, memory_registry, ns):
        got = memory_registry.memory.get({"namespace": ns, "key": "absent"})
        assert got == {"value": None, "written_at": None}

    def test_get_isolated_by_namespace(self, memory_registry, ns):
        memory_registry.memory.put(
            {"namespace": ns, "key": "shared", "value": {"v": 1}}
        )
        # Same key, different namespace → should be missing.
        other_ns = ns + "_other"
        got = memory_registry.memory.get(
            {"namespace": other_ns, "key": "shared"}
        )
        assert got["value"] is None

    def test_get_validates_input(self, memory_registry, ns):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            memory_registry.memory.get({"namespace": ns, "key": ""})

    def test_get_after_overwrite_returns_latest(self, memory_registry, ns):
        memory_registry.memory.put(
            {"namespace": ns, "key": "alpha", "value": {"v": 1}}
        )
        memory_registry.memory.put(
            {"namespace": ns, "key": "alpha", "value": {"v": 2}}
        )
        got = memory_registry.memory.get({"namespace": ns, "key": "alpha"})
        assert got["value"] == {"v": 2}


class TestMemoryList:
    def test_list_empty_namespace_returns_empty_items(self, memory_registry, ns):
        result = memory_registry.memory.list({"namespace": ns})
        assert result == {"items": []}

    def test_list_returns_all_keys_in_namespace(self, memory_registry, ns):
        memory_registry.memory.put(
            {"namespace": ns, "key": "a", "value": {"v": 1}}
        )
        memory_registry.memory.put(
            {"namespace": ns, "key": "b", "value": {"v": 2}}
        )
        result = memory_registry.memory.list({"namespace": ns})
        keys = sorted(item["key"] for item in result["items"])
        assert keys == ["a", "b"]

    def test_list_most_recent_first(self, memory_registry, ns):
        # Two puts with a small gap so written_at differs.
        import time

        memory_registry.memory.put(
            {"namespace": ns, "key": "first", "value": {"v": 1}}
        )
        time.sleep(0.01)
        memory_registry.memory.put(
            {"namespace": ns, "key": "second", "value": {"v": 2}}
        )
        result = memory_registry.memory.list({"namespace": ns})
        assert [it["key"] for it in result["items"]] == ["second", "first"]

    def test_list_isolated_by_namespace(self, memory_registry, ns):
        memory_registry.memory.put(
            {"namespace": ns, "key": "a", "value": {"v": 1}}
        )
        result = memory_registry.memory.list({"namespace": ns + "_other"})
        assert result == {"items": []}

    def test_list_since_filters_older_entries(self, memory_registry, ns):
        # Use the second put's own written_at as the cutoff — sidesteps
        # any clock drift between Python and Postgres.
        import time

        memory_registry.memory.put(
            {"namespace": ns, "key": "old", "value": {"v": 1}}
        )
        time.sleep(0.05)
        new_result = memory_registry.memory.put(
            {"namespace": ns, "key": "new", "value": {"v": 2}}
        )

        result = memory_registry.memory.list(
            {"namespace": ns, "since": new_result["written_at"]}
        )
        keys = [it["key"] for it in result["items"]]
        assert keys == ["new"]

    def test_list_limit_caps_results(self, memory_registry, ns):
        for i in range(5):
            memory_registry.memory.put(
                {"namespace": ns, "key": f"k{i}", "value": {"v": i}}
            )
        result = memory_registry.memory.list({"namespace": ns, "limit": 2})
        assert len(result["items"]) == 2

    def test_list_validates_input(self, memory_registry, ns):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            memory_registry.memory.list({"namespace": ""})

        with pytest.raises(ValidationError):
            memory_registry.memory.list({"namespace": ns, "limit": 0})
