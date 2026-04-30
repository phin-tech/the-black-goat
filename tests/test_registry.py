from __future__ import annotations

import pytest
from pydantic import BaseModel

from the_black_goat import (
    Registry,
    ToolDef,
    build_registry,
    durable,
    hookimpl,
    tool,
)
from the_black_goat.errors import AbsurdNotConfigured, ToolNotFound


class _Input(BaseModel):
    x: int


class _Output(BaseModel):
    y: int


def _impl(input: _Input) -> _Output:
    """Sample tool."""
    return _Output(y=input.x)


def _atom(name: str, *, tags: tuple[str, ...] = ()) -> ToolDef:
    return tool(
        name=name,
        func=_impl,
        input=_Input,
        output=_Output,
        tags=tags,
    )


def _plugin(*tools: ToolDef):
    """Build a plugin object that returns the given tools from goat_register_tools."""

    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return list(tools)

    return _P()


class TestBuildRegistry:
    def test_returns_registry_instance(self):
        reg = build_registry(plugins={"demo": _plugin(_atom("alpha"))})
        assert isinstance(reg, Registry)

    def test_no_plugins_yields_empty_registry(self):
        reg = build_registry(plugins={})
        assert reg.list() == []


class TestNamePrefixing:
    def test_qualified_name_uses_plugin_prefix(self):
        reg = build_registry(plugins={"slack": _plugin(_atom("send"))})
        [td] = reg.list()
        assert td.qualified_name == "slack.send"
        assert td.plugin == "slack"
        assert td.name == "send"

    def test_two_plugins_same_short_name_no_collision(self):
        reg = build_registry(
            plugins={
                "slack": _plugin(_atom("send")),
                "twilio": _plugin(_atom("send")),
            }
        )
        names = sorted(t.qualified_name for t in reg.list())
        assert names == ["slack.send", "twilio.send"]


class TestGet:
    def test_get_returns_tool(self):
        reg = build_registry(plugins={"slack": _plugin(_atom("send"))})
        td = reg.get("slack.send")
        assert td.qualified_name == "slack.send"

    def test_get_missing_raises_tool_not_found(self):
        reg = build_registry(plugins={"slack": _plugin(_atom("send"))})
        with pytest.raises(ToolNotFound):
            reg.get("slack.unknown")

    def test_get_unprefixed_name_raises_tool_not_found(self):
        reg = build_registry(plugins={"slack": _plugin(_atom("send"))})
        # Lookups must use qualified names.
        with pytest.raises(ToolNotFound):
            reg.get("send")


class TestList:
    def test_list_returns_all_tools(self):
        reg = build_registry(
            plugins={
                "slack": _plugin(_atom("send"), _atom("react")),
                "twilio": _plugin(_atom("sms")),
            }
        )
        names = sorted(t.qualified_name for t in reg.list())
        assert names == ["slack.react", "slack.send", "twilio.sms"]


class TestByPlugin:
    def test_by_plugin_returns_only_that_plugin(self):
        reg = build_registry(
            plugins={
                "slack": _plugin(_atom("send"), _atom("react")),
                "twilio": _plugin(_atom("sms")),
            }
        )
        slack_tools = sorted(t.name for t in reg.by_plugin("slack"))
        twilio_tools = sorted(t.name for t in reg.by_plugin("twilio"))
        assert slack_tools == ["react", "send"]
        assert twilio_tools == ["sms"]

    def test_by_plugin_unknown_returns_empty(self):
        reg = build_registry(plugins={"slack": _plugin(_atom("send"))})
        assert reg.by_plugin("nonexistent") == []


class TestByTag:
    def test_by_tag_filters(self):
        reg = build_registry(
            plugins={
                "slack": _plugin(
                    _atom("send", tags=("messaging",)),
                    _atom("react", tags=("messaging", "emoji")),
                ),
                "twilio": _plugin(_atom("sms", tags=("messaging",))),
            }
        )
        messaging = sorted(t.qualified_name for t in reg.by_tag("messaging"))
        emoji = sorted(t.qualified_name for t in reg.by_tag("emoji"))
        assert messaging == ["slack.react", "slack.send", "twilio.sms"]
        assert emoji == ["slack.react"]

    def test_by_tag_unknown_returns_empty(self):
        reg = build_registry(plugins={"slack": _plugin(_atom("send"))})
        assert reg.by_tag("nope") == []


class TestCollisionDetection:
    def test_same_plugin_duplicate_name_raises_at_build_time(self):
        with pytest.raises(ValueError, match=r"duplicate"):
            build_registry(
                plugins={"slack": _plugin(_atom("send"), _atom("send"))}
            )


class TestAbsurdGate:
    def test_durable_tool_without_absurd_raises(self):
        atom = _atom("send")
        wrapped = durable(atom, max_attempts=3)
        with pytest.raises(AbsurdNotConfigured):
            build_registry(plugins={"slack": _plugin(wrapped)})

    def test_atom_without_absurd_is_fine(self):
        # All atoms; no durable tools => absurd not required.
        reg = build_registry(plugins={"slack": _plugin(_atom("send"))})
        assert reg.get("slack.send").durability is None

    def test_durable_tool_with_absurd_is_fine(self):
        # Sentinel; Slice D doesn't dispatch via absurd, just gates the build.
        absurd_sentinel = object()
        atom = _atom("send")
        wrapped = durable(atom, max_attempts=3)
        reg = build_registry(
            plugins={"slack": _plugin(wrapped)},
            absurd=absurd_sentinel,
        )
        assert reg.get("slack.send").durability is not None
