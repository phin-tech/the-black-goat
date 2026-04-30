from __future__ import annotations

import pytest
from pydantic import BaseModel

from the_black_goat import ToolDef, build_registry, hookimpl, tool
from the_black_goat.errors import ToolNotFound


class _Input(BaseModel):
    x: int


class _Output(BaseModel):
    y: int


def _double(input: _Input) -> _Output:
    """Double x."""
    return _Output(y=input.x * 2)


def _atom(name: str, func=_double) -> ToolDef:
    return tool(name=name, func=func, input=_Input, output=_Output)


def _plugin(*tools: ToolDef):
    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return list(tools)

    return _P()


def _registry(*tools: ToolDef):
    return build_registry(plugins={"demo": _plugin(*tools)})


class TestAttributeProxyHappyPath:
    def test_proxy_call_with_dict_returns_invoke_result(self):
        reg = _registry(_atom("dbl"))
        assert reg.demo.dbl({"x": 4}) == {"y": 8}

    def test_proxy_call_with_pydantic_model_dumps_and_invokes(self):
        reg = _registry(_atom("dbl"))
        assert reg.demo.dbl(_Input(x=5)) == {"y": 10}

    def test_proxy_routes_to_invoke_dispatch(self, monkeypatch):
        reg = _registry(_atom("dbl"))
        seen: list = []

        original_invoke = reg.invoke

        def _spy(name, params):
            seen.append((name, params))
            return original_invoke(name, params)

        monkeypatch.setattr(reg, "invoke", _spy)
        reg.demo.dbl({"x": 3})
        assert seen == [("demo.dbl", {"x": 3})]


class TestAttributeProxyDoesNotShadowMethods:
    """The proxy must only kick in for genuinely missing attributes; the
    Registry's own API has to keep working."""

    def test_list_still_works(self):
        reg = _registry(_atom("a"), _atom("b"))
        names = sorted(t.qualified_name for t in reg.list())
        assert names == ["demo.a", "demo.b"]

    def test_get_still_works(self):
        reg = _registry(_atom("a"))
        assert reg.get("demo.a").qualified_name == "demo.a"

    def test_invoke_still_works(self):
        reg = _registry(_atom("dbl"))
        assert reg.invoke("demo.dbl", {"x": 1}) == {"y": 2}

    def test_by_plugin_still_works(self):
        reg = _registry(_atom("a"), _atom("b"))
        assert {t.name for t in reg.by_plugin("demo")} == {"a", "b"}

    def test_by_tag_still_works(self):
        reg = _registry(
            tool(
                name="tagged",
                func=_double,
                input=_Input,
                output=_Output,
                tags=("messaging",),
            )
        )
        assert {t.name for t in reg.by_tag("messaging")} == {"tagged"}


class TestAttributeProxyLateBinding:
    """The proxy doesn't validate plugin/tool names up front; the registry
    raises ToolNotFound when the resolved qname doesn't exist."""

    def test_unknown_tool_in_known_plugin_raises_at_call(self):
        reg = _registry(_atom("a"))
        with pytest.raises(ToolNotFound):
            reg.demo.unknown({"x": 1})

    def test_unknown_plugin_raises_at_call(self):
        reg = _registry(_atom("a"))
        with pytest.raises(ToolNotFound):
            reg.no_such_plugin.tool({"x": 1})


class TestAttributeProxyPrivateAttrs:
    """Underscore attributes set in __init__ must NOT route through the
    proxy (otherwise reg._tools would silently become a plugin namespace)."""

    def test_private_attribute_not_intercepted(self):
        reg = _registry(_atom("a"))
        # _tools is a real instance attribute; reading it must return the
        # actual dict, not a proxy.
        assert isinstance(reg._tools, dict)
        assert "demo.a" in reg._tools


class TestAttributeProxyIsolation:
    """Calling proxies on the same registry returns equivalent results
    each time (the proxy must not stash state that would corrupt
    subsequent calls)."""

    def test_repeated_calls_independent(self):
        reg = _registry(_atom("dbl"))
        a = reg.demo.dbl({"x": 1})
        b = reg.demo.dbl({"x": 7})
        assert a == {"y": 2}
        assert b == {"y": 14}
