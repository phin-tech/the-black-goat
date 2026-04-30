"""Integration test: build a registry from the real `the-black-goat-stdlib`
plugin (loaded via setuptools entry points) and exercise its tools end-to-end.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from the_black_goat import build_registry


@pytest.fixture
def registry():
    """Build a registry against actual entry points (no plugins= override)."""
    return build_registry()


class TestStdlibDiscovery:
    def test_stdlib_plugin_is_loaded(self, registry):
        names = {t.qualified_name for t in registry.list()}
        assert {"stdlib.now", "stdlib.sleep", "stdlib.echo"} <= names

    def test_each_tool_carries_its_plugin_attribute(self, registry):
        for qname in ("stdlib.now", "stdlib.sleep", "stdlib.echo"):
            assert registry.get(qname).plugin == "stdlib"


class TestStdlibInvoke:
    def test_now_returns_iso_and_epoch(self, registry):
        result = registry.invoke("stdlib.now", {})
        assert "iso" in result and "epoch" in result
        # Parse it back to confirm it's a real ISO timestamp.
        parsed = datetime.fromisoformat(result["iso"])
        assert parsed.tzinfo is not None
        assert isinstance(result["epoch"], float)

    def test_now_advances(self, registry):
        a = registry.invoke("stdlib.now", {})
        b = registry.invoke("stdlib.now", {})
        assert b["epoch"] >= a["epoch"]

    def test_echo_returns_message_unchanged(self, registry):
        result = registry.invoke("stdlib.echo", {"message": "ia! ia!"})
        assert result == {"message": "ia! ia!"}

    def test_sleep_blocks_for_at_least_the_requested_duration(self, registry):
        result = registry.invoke("stdlib.sleep", {"seconds": 0.05})
        assert result["slept"] >= 0.05


class TestStdlibTypedImport:
    """The typed-handle path: program code can `import` the underlying
    callables and call them directly with their Pydantic input model."""

    def test_typed_import_now(self):
        from stdlib_plugin.tools import NowInput, NowOutput, now

        out = now(NowInput())
        assert isinstance(out, NowOutput)
        assert out.epoch > 0

    def test_typed_import_echo(self):
        from stdlib_plugin.tools import EchoInput, echo

        out = echo(EchoInput(message="hi"))
        assert out.message == "hi"


class TestStdlibTags:
    def test_by_tag_finds_time_tools(self, registry):
        time_tools = sorted(t.qualified_name for t in registry.by_tag("time"))
        assert time_tools == ["stdlib.now", "stdlib.sleep"]

    def test_by_tag_finds_debug_tools(self, registry):
        debug_tools = [t.qualified_name for t in registry.by_tag("debug")]
        assert debug_tools == ["stdlib.echo"]
