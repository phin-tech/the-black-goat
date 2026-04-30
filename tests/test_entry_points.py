from __future__ import annotations

import pluggy
from pydantic import BaseModel

from the_black_goat import ToolDef, build_registry, hookimpl, tool


class _Input(BaseModel):
    x: int


class _Output(BaseModel):
    y: int


def _impl(input: _Input) -> _Output:
    """Sample tool."""
    return _Output(y=input.x)


def _atom(name: str = "alpha") -> ToolDef:
    return tool(name=name, func=_impl, input=_Input, output=_Output)


class _FakePlugin:
    @hookimpl
    def goat_register_tools(self) -> list[ToolDef]:
        return [_atom("alpha")]


class TestDefaultPathLoadsEntryPoints:
    def test_no_plugins_arg_calls_load_setuptools_entrypoints(self, monkeypatch):
        called: list[str] = []

        def _fake_load(self, group):
            called.append(group)
            return 0

        monkeypatch.setattr(
            pluggy.PluginManager, "load_setuptools_entrypoints", _fake_load
        )

        build_registry()  # plugins=None
        assert called == ["the_black_goat"]


class TestExplicitPluginsSkipsEntryPoints:
    def test_explicit_dict_does_not_load_entry_points(self, monkeypatch):
        called: list[str] = []

        def _fake_load(self, group):
            called.append(group)
            return 0

        monkeypatch.setattr(
            pluggy.PluginManager, "load_setuptools_entrypoints", _fake_load
        )

        build_registry(plugins={})
        assert called == []

    def test_explicit_dict_with_plugins_does_not_load_entry_points(
        self, monkeypatch
    ):
        called: list[str] = []

        def _fake_load(self, group):
            called.append(group)
            return 0

        monkeypatch.setattr(
            pluggy.PluginManager, "load_setuptools_entrypoints", _fake_load
        )

        build_registry(plugins={"demo": _FakePlugin()})
        assert called == []


class TestEntryPointDiscoveryEndToEnd:
    """When entry_points contributes a plugin, the registry processes it the
    same way as an explicit plugin: name prefix, list/get, etc."""

    def test_plugin_loaded_via_entry_points_is_aggregated(self, monkeypatch):
        def _fake_load(self, group):
            if group == "the_black_goat":
                self.register(_FakePlugin(), name="demo")
                return 1
            return 0

        monkeypatch.setattr(
            pluggy.PluginManager, "load_setuptools_entrypoints", _fake_load
        )

        reg = build_registry()  # plugins=None → entry-point path

        names = sorted(t.qualified_name for t in reg.list())
        assert names == ["demo.alpha"]
        assert reg.get("demo.alpha").plugin == "demo"
