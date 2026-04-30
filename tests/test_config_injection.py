from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from the_black_goat import ToolDef, build_registry, hookimpl, tool
from the_black_goat.config import ConfigSource, DictConfigSource, EnvConfigSource
from the_black_goat.errors import ConfigError


class _Input(BaseModel):
    x: int


class _Output(BaseModel):
    y: int


class _Cfg(BaseModel):
    api_key: str


def _no_config_impl(input: _Input) -> _Output:
    return _Output(y=input.x)


def _impl_with_config(input: _Input, *, config: _Cfg) -> _Output:
    return _Output(y=input.x)


def _atom(name: str, func, *, config_schema=None) -> ToolDef:
    return tool(
        name=name,
        func=func,
        input=_Input,
        output=_Output,
        config=config_schema,
    )


def _plugin(*tools: ToolDef):
    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return list(tools)

    return _P()


# ---------- DictConfigSource ----------


class TestDictConfigSource:
    def test_resolves_from_dict(self):
        source = DictConfigSource({"twilio": {"api_key": "secret"}})
        cfg = source.resolve("twilio", _Cfg)
        assert isinstance(cfg, _Cfg)
        assert cfg.api_key == "secret"

    def test_missing_plugin_raises_config_error(self):
        source = DictConfigSource({})
        with pytest.raises(ConfigError):
            source.resolve("twilio", _Cfg)

    def test_invalid_value_raises_config_error(self):
        # api_key must be a string; provide a non-coercible bad shape.
        source = DictConfigSource({"twilio": {"api_key": {"nested": "x"}}})
        with pytest.raises(ConfigError):
            source.resolve("twilio", _Cfg)


# ---------- EnvConfigSource ----------


class TestEnvConfigSource:
    def test_reads_env_vars_with_plugin_prefix(self, monkeypatch):
        monkeypatch.setenv("TWILIO_API_KEY", "secret123")
        source = EnvConfigSource()
        cfg = source.resolve("twilio", _Cfg)
        assert cfg.api_key == "secret123"

    def test_uses_field_default_when_env_missing(self, monkeypatch):
        class _CfgWithDefault(BaseModel):
            api_key: str = "fallback"

        monkeypatch.delenv("TWILIO_API_KEY", raising=False)
        cfg = EnvConfigSource().resolve("twilio", _CfgWithDefault)
        assert cfg.api_key == "fallback"

    def test_missing_required_field_raises_config_error(self, monkeypatch):
        monkeypatch.delenv("TWILIO_API_KEY", raising=False)
        with pytest.raises(ConfigError):
            EnvConfigSource().resolve("twilio", _Cfg)

    def test_uppercases_plugin_and_field(self, monkeypatch):
        # plugin "slack" + field "api_key" → env "SLACK_API_KEY".
        monkeypatch.setenv("SLACK_API_KEY", "k")
        cfg = EnvConfigSource().resolve("slack", _Cfg)
        assert cfg.api_key == "k"


# ---------- Protocol ----------


class TestProtocolSurface:
    def test_dict_source_satisfies_protocol(self):
        assert isinstance(DictConfigSource({}), ConfigSource)

    def test_env_source_satisfies_protocol(self):
        assert isinstance(EnvConfigSource(), ConfigSource)


# ---------- build-time gating ----------


class TestBuildTimeConfigResolution:
    def test_tool_with_config_schema_without_config_source_raises_at_build(self):
        td = _atom("send", _impl_with_config, config_schema=_Cfg)
        with pytest.raises(ConfigError):
            build_registry(plugins={"twilio": _plugin(td)})

    def test_missing_plugin_in_config_source_raises_at_build(self):
        td = _atom("send", _impl_with_config, config_schema=_Cfg)
        with pytest.raises(ConfigError):
            build_registry(
                plugins={"twilio": _plugin(td)},
                config_source=DictConfigSource({}),  # plugin missing
            )

    def test_atom_without_config_does_not_require_source(self):
        td = _atom("noop", _no_config_impl)
        reg = build_registry(plugins={"twilio": _plugin(td)})
        assert reg.invoke("twilio.noop", {"x": 1}) == {"y": 1}


# ---------- runtime injection ----------


class TestConfigInjectedAtRuntime:
    def test_invoke_passes_resolved_config_as_kwarg(self):
        captured: dict = {}

        def _records(input: _Input, *, config: _Cfg) -> _Output:
            captured["config"] = config
            return _Output(y=input.x)

        td = _atom("send", _records, config_schema=_Cfg)
        reg = build_registry(
            plugins={"twilio": _plugin(td)},
            config_source=DictConfigSource({"twilio": {"api_key": "secret"}}),
        )
        result = reg.invoke("twilio.send", {"x": 1})
        assert captured["config"].api_key == "secret"
        assert isinstance(captured["config"], _Cfg)
        assert result == {"y": 1}

    def test_ainvoke_passes_resolved_config_to_async_tool(self):
        captured: dict = {}

        async def _records_async(input: _Input, *, config: _Cfg) -> _Output:
            captured["config"] = config
            return _Output(y=input.x * 2)

        td = _atom("send", _records_async, config_schema=_Cfg)
        reg = build_registry(
            plugins={"twilio": _plugin(td)},
            config_source=DictConfigSource({"twilio": {"api_key": "secret"}}),
        )
        result = asyncio.run(reg.ainvoke("twilio.send", {"x": 4}))
        assert captured["config"].api_key == "secret"
        assert result == {"y": 8}

    def test_config_resolved_once_at_build_time(self):
        # Calling invoke many times reuses the same resolved config object.
        captured: list = []

        def _records(input: _Input, *, config: _Cfg) -> _Output:
            captured.append(config)
            return _Output(y=input.x)

        td = _atom("send", _records, config_schema=_Cfg)
        reg = build_registry(
            plugins={"twilio": _plugin(td)},
            config_source=DictConfigSource({"twilio": {"api_key": "secret"}}),
        )
        reg.invoke("twilio.send", {"x": 1})
        reg.invoke("twilio.send", {"x": 2})
        reg.invoke("twilio.send", {"x": 3})
        # Same object identity each call → resolved exactly once.
        assert captured[0] is captured[1] is captured[2]
