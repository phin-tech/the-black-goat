from __future__ import annotations

from typing import Any, Mapping

import pluggy

from the_black_goat._hookspec import PROJECT_NAME, GoatHooks
from the_black_goat.errors import AbsurdNotConfigured, ToolNotFound
from the_black_goat.tools import ToolDef


class Registry:
    """Immutable registry of ToolDefs keyed by qualified name."""

    def __init__(
        self,
        tools: Mapping[str, ToolDef],
        *,
        absurd: Any = None,
    ) -> None:
        self._tools: dict[str, ToolDef] = dict(tools)
        self._absurd = absurd

    def list(self) -> list[ToolDef]:
        return list(self._tools.values())

    def get(self, qualified_name: str) -> ToolDef:
        try:
            return self._tools[qualified_name]
        except KeyError:
            raise ToolNotFound(qualified_name) from None

    def by_plugin(self, plugin: str) -> list[ToolDef]:
        return [t for t in self._tools.values() if t.plugin == plugin]

    def by_tag(self, tag: str) -> list[ToolDef]:
        return [t for t in self._tools.values() if tag in t.tags]


def build_registry(
    plugins: Mapping[str, Any] | None = None,
    *,
    config_source: Any = None,
    absurd: Any = None,
) -> Registry:
    """Build a Registry by aggregating ToolDefs from plugins.

    If `plugins` is None, plugins are auto-discovered via setuptools
    entry points (group: "the_black_goat"). Otherwise, `plugins` is a
    mapping of plugin_name -> plugin_object; each is registered under
    that name and its tools are prefixed with it.
    """
    pm = pluggy.PluginManager(PROJECT_NAME)
    pm.add_hookspecs(GoatHooks)

    if plugins is not None:
        for name, plugin in plugins.items():
            pm.register(plugin, name=name)
    else:
        pm.load_setuptools_entrypoints(PROJECT_NAME)

    tools_by_qname: dict[str, ToolDef] = {}
    for hookimpl_obj in pm.hook.goat_register_tools.get_hookimpls():
        plugin_name = hookimpl_obj.plugin_name
        plugin_obj = hookimpl_obj.plugin
        method = getattr(plugin_obj, "goat_register_tools")
        for td in method():
            prefixed = td.model_copy(update={"plugin": plugin_name})
            qname = prefixed.qualified_name
            if qname in tools_by_qname:
                raise ValueError(f"duplicate tool name: {qname!r}")
            if prefixed.durability is not None and absurd is None:
                raise AbsurdNotConfigured(
                    f"tool {qname!r} is durable but no absurd= was "
                    "provided to build_registry()"
                )
            tools_by_qname[qname] = prefixed

    return Registry(tools_by_qname, absurd=absurd)
