from __future__ import annotations

import pluggy
from pydantic import BaseModel

from the_black_goat import ToolDef, hookimpl, tool
from the_black_goat._hookspec import GoatHooks, hookspec


class _Input(BaseModel):
    x: int


class _Output(BaseModel):
    y: int


def _impl(input: _Input) -> _Output:
    """Sample tool."""
    return _Output(y=input.x)


def _make_tool(name: str) -> ToolDef:
    return tool(name=name, func=_impl, input=_Input, output=_Output)


def _make_pm() -> pluggy.PluginManager:
    pm = pluggy.PluginManager("the_black_goat")
    pm.add_hookspecs(GoatHooks)
    return pm


class TestMarkers:
    def test_hookspec_is_pluggy_marker_for_the_black_goat(self):
        assert isinstance(hookspec, pluggy.HookspecMarker)
        assert hookspec.project_name == "the_black_goat"

    def test_hookimpl_is_pluggy_marker_for_the_black_goat(self):
        assert isinstance(hookimpl, pluggy.HookimplMarker)
        assert hookimpl.project_name == "the_black_goat"

    def test_hookspec_class_declares_goat_register_tools(self):
        assert hasattr(GoatHooks, "goat_register_tools")


class TestSinglePluginAggregation:
    def test_single_plugin_one_tool(self):
        td = _make_tool("alpha")

        class Plugin:
            @hookimpl
            def goat_register_tools(self) -> list[ToolDef]:
                return [td]

        pm = _make_pm()
        pm.register(Plugin())

        results = pm.hook.goat_register_tools()
        assert results == [[td]]

    def test_single_plugin_many_tools(self):
        a = _make_tool("alpha")
        b = _make_tool("bravo")

        class Plugin:
            @hookimpl
            def goat_register_tools(self) -> list[ToolDef]:
                return [a, b]

        pm = _make_pm()
        pm.register(Plugin())

        results = pm.hook.goat_register_tools()
        assert results == [[a, b]]

    def test_each_returned_item_is_a_tool_def(self):
        class Plugin:
            @hookimpl
            def goat_register_tools(self) -> list[ToolDef]:
                return [_make_tool("alpha")]

        pm = _make_pm()
        pm.register(Plugin())

        [tools_from_plugin] = pm.hook.goat_register_tools()
        assert all(isinstance(t, ToolDef) for t in tools_from_plugin)


class TestMultiPluginAggregation:
    def test_two_plugins_aggregate_as_list_of_lists(self):
        a = _make_tool("alpha")
        b = _make_tool("bravo")

        class PluginA:
            @hookimpl
            def goat_register_tools(self) -> list[ToolDef]:
                return [a]

        class PluginB:
            @hookimpl
            def goat_register_tools(self) -> list[ToolDef]:
                return [b]

        pm = _make_pm()
        pm.register(PluginA())
        pm.register(PluginB())

        results = pm.hook.goat_register_tools()
        # pluggy aggregates one return value per plugin; order is
        # last-registered-first by default, so just check the multiset.
        assert sorted(
            (item for sub in results for item in sub),
            key=lambda t: t.name,
        ) == [a, b]
        assert len(results) == 2


class TestEdgeCases:
    def test_plugin_returning_empty_list_is_allowed(self):
        class Plugin:
            @hookimpl
            def goat_register_tools(self) -> list[ToolDef]:
                return []

        pm = _make_pm()
        pm.register(Plugin())

        assert pm.hook.goat_register_tools() == [[]]

    def test_plugin_without_hookimpl_is_allowed_and_skipped(self):
        class Plugin:
            # No @hookimpl. Pluggy should still accept the registration
            # and simply not include this plugin in the hook results.
            def some_other_method(self) -> None:
                pass

        pm = _make_pm()
        pm.register(Plugin())

        assert pm.hook.goat_register_tools() == []

    def test_no_plugins_registered_returns_empty_list(self):
        pm = _make_pm()
        assert pm.hook.goat_register_tools() == []
