from __future__ import annotations

import pytest
from pydantic import BaseModel

from the_black_goat import (
    Registry,
    ToolDef,
    build_registry,
    current_registry,
    hookimpl,
    tool,
)


class _Input(BaseModel):
    pass


class _Output(BaseModel):
    pass


def _noop(input: _Input) -> _Output:
    return _Output()


def _atom(name: str = "x") -> ToolDef:
    return tool(name=name, func=_noop, input=_Input, output=_Output)


def _plugin(*tools: ToolDef):
    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return list(tools)

    return _P()


@pytest.fixture(autouse=True)
def _reset_current_registry():
    """Each test starts with no registry set in the contextvar."""
    from the_black_goat.registry import _current_registry

    token = _current_registry.set(None)
    yield
    _current_registry.reset(token)


class TestCurrentRegistryUnset:
    def test_raises_when_no_registry_built(self):
        with pytest.raises(RuntimeError, match=r"current_registry"):
            current_registry()


class TestCurrentRegistryAfterBuild:
    def test_returns_the_built_registry(self):
        reg = build_registry(plugins={"demo": _plugin(_atom())})
        assert current_registry() is reg

    def test_returned_value_is_a_registry(self):
        build_registry(plugins={"demo": _plugin(_atom())})
        assert isinstance(current_registry(), Registry)

    def test_most_recent_build_wins(self):
        a = build_registry(plugins={"demo": _plugin(_atom("a"))})
        b = build_registry(plugins={"demo": _plugin(_atom("b"))})
        assert a is not b
        assert current_registry() is b
        names = {t.qualified_name for t in current_registry().list()}
        assert names == {"demo.b"}


class TestCurrentRegistryAcrossCalls:
    """The whole point of a contextvar: helper functions can reach the
    current registry without it being threaded through every call."""

    def test_helper_function_can_read_the_contextvar(self):
        def _helper():
            return current_registry()

        reg = build_registry(plugins={"demo": _plugin(_atom("y"))})
        assert _helper() is reg

    def test_nested_helper_can_read_the_contextvar(self):
        def _inner():
            return current_registry()

        def _outer():
            return _inner()

        reg = build_registry(plugins={"demo": _plugin(_atom("z"))})
        assert _outer() is reg
