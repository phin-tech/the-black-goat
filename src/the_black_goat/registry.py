from __future__ import annotations

from typing import Any, Mapping

import pluggy
from pydantic import BaseModel

from the_black_goat._hookspec import PROJECT_NAME, GoatHooks
from the_black_goat.config import ConfigSource
from the_black_goat.errors import (
    AbsurdNotConfigured,
    ConfigError,
    ToolKindMismatch,
    ToolNotFound,
)
from the_black_goat.tools import ToolDef


class Registry:
    """Immutable registry of ToolDefs keyed by qualified name."""

    def __init__(
        self,
        tools: Mapping[str, ToolDef],
        *,
        absurd: Any = None,
        configs: Mapping[str, BaseModel] | None = None,
    ) -> None:
        self._tools: dict[str, ToolDef] = dict(tools)
        self._absurd = absurd
        self._configs: dict[str, BaseModel] = dict(configs or {})

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

    def invoke(self, qualified_name: str, params: dict) -> dict:
        """Run a sync atom in-process. Raises:
        - ToolNotFound if `qualified_name` is unknown.
        - ToolKindMismatch if the tool is async (use ainvoke).
        """
        record = self.get(qualified_name)
        if record.is_async:
            raise ToolKindMismatch(
                f"tool {qualified_name!r} is async; use ainvoke() instead"
            )
        if record.durability is not None:
            # Slice K replaces this with absurd spawn + await.
            raise NotImplementedError(
                f"durable tool {qualified_name!r} dispatch via absurd is "
                "not yet implemented (Slice K)"
            )
        return self._invoke_in_process(record, params)

    async def ainvoke(self, qualified_name: str, params: dict) -> dict:
        """Run an atom in-process from an async context. Accepts both
        sync and async tools (sync ones run inline; we are not in a
        thread-safe-only context).

        Raises ToolNotFound for unknown names.
        """
        record = self.get(qualified_name)
        if record.durability is not None:
            # Slice K replaces this with absurd spawn + await.
            raise NotImplementedError(
                f"durable tool {qualified_name!r} dispatch via absurd is "
                "not yet implemented (Slice K)"
            )
        return await self._ainvoke_in_process(record, params)

    def _invoke_in_process(self, record: ToolDef, params: dict) -> dict:
        input_obj = self._validate_input(record, params)
        result = self._call_sync(record, input_obj)
        return self._dump_output(record, result)

    async def _ainvoke_in_process(self, record: ToolDef, params: dict) -> dict:
        input_obj = self._validate_input(record, params)
        if record.is_async:
            result = await self._call_async(record, input_obj)
        else:
            result = self._call_sync(record, input_obj)
        return self._dump_output(record, result)

    @staticmethod
    def _validate_input(record: ToolDef, params: dict):
        return record.input_schema.model_validate(params)

    def _call_sync(self, record: ToolDef, input_obj):
        if record.config_schema is None:
            return record.func(input_obj)
        config = self._configs[record.qualified_name]
        return record.func(input_obj, config=config)

    async def _call_async(self, record: ToolDef, input_obj):
        if record.config_schema is None:
            return await record.func(input_obj)
        config = self._configs[record.qualified_name]
        return await record.func(input_obj, config=config)

    @staticmethod
    def _dump_output(record: ToolDef, result):
        if isinstance(result, record.output_schema):
            output = result
        else:
            output = record.output_schema.model_validate(result)
        return output.model_dump()


def build_registry(
    plugins: Mapping[str, Any] | None = None,
    *,
    config_source: ConfigSource | None = None,
    absurd: Any = None,
) -> Registry:
    """Build a Registry by aggregating ToolDefs from plugins.

    If `plugins` is None, plugins are auto-discovered via setuptools
    entry points (group: "the_black_goat"). Otherwise, `plugins` is a
    mapping of plugin_name -> plugin_object; each is registered under
    that name and its tools are prefixed with it.

    Tools that declare a `config_schema` have their config resolved at
    build time via `config_source`. A missing source or unresolvable
    config raises `ConfigError` immediately, never at call time.

    Tools with a populated `durability` require `absurd` to be provided
    (see Slices J/K).
    """
    pm = pluggy.PluginManager(PROJECT_NAME)
    pm.add_hookspecs(GoatHooks)

    if plugins is not None:
        for name, plugin in plugins.items():
            pm.register(plugin, name=name)
    else:
        pm.load_setuptools_entrypoints(PROJECT_NAME)

    tools_by_qname: dict[str, ToolDef] = {}
    configs_by_qname: dict[str, BaseModel] = {}

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
            if prefixed.config_schema is not None:
                if config_source is None:
                    raise ConfigError(
                        f"tool {qname!r} declares config_schema but no "
                        "config_source= was provided to build_registry()"
                    )
                configs_by_qname[qname] = config_source.resolve(
                    plugin_name, prefixed.config_schema
                )
            tools_by_qname[qname] = prefixed

    return Registry(tools_by_qname, absurd=absurd, configs=configs_by_qname)
