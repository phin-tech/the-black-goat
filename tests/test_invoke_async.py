from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel, ValidationError

from the_black_goat import ToolDef, build_registry, hookimpl, tool
from the_black_goat.errors import ToolNotFound


class _Input(BaseModel):
    x: int


class _Output(BaseModel):
    y: int


def _sync_double(input: _Input) -> _Output:
    """Sync double."""
    return _Output(y=input.x * 2)


async def _async_double(input: _Input) -> _Output:
    """Async double."""
    return _Output(y=input.x * 2)


async def _async_returns_dict(input: _Input) -> dict:
    """Async tool returning a raw dict."""
    return {"y": input.x * 2}


async def _async_bad_output(input: _Input) -> dict:
    """Async tool returning malformed output."""
    return {"wrong_field": input.x}


def _atom(name: str, func) -> ToolDef:
    return tool(name=name, func=func, input=_Input, output=_Output)


def _plugin(*tools: ToolDef):
    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return list(tools)

    return _P()


def _registry(*tools: ToolDef):
    return build_registry(plugins={"demo": _plugin(*tools)})


class TestAinvokeAsyncTool:
    @pytest.mark.asyncio
    async def test_returns_dict_from_output_model(self):
        reg = _registry(_atom("dbl", _async_double))
        assert await reg.ainvoke("demo.dbl", {"x": 4}) == {"y": 8}

    @pytest.mark.asyncio
    async def test_validates_dict_returned_by_async_tool(self):
        reg = _registry(_atom("dbl", _async_returns_dict))
        assert await reg.ainvoke("demo.dbl", {"x": 5}) == {"y": 10}

    @pytest.mark.asyncio
    async def test_input_validation_raises_before_body_runs(self):
        called: list = []

        async def _records_call(input: _Input) -> _Output:
            called.append(input)
            return _Output(y=input.x)

        reg = _registry(_atom("rec", _records_call))
        with pytest.raises(ValidationError):
            await reg.ainvoke("demo.rec", {})
        assert called == []

    @pytest.mark.asyncio
    async def test_bad_output_raises_validation_error(self):
        reg = _registry(_atom("bad", _async_bad_output))
        with pytest.raises(ValidationError):
            await reg.ainvoke("demo.bad", {"x": 1})


class TestAinvokeSyncTool:
    """Sync atoms must also be reachable via ainvoke()."""

    @pytest.mark.asyncio
    async def test_sync_atom_runs_via_ainvoke(self):
        reg = _registry(_atom("dbl", _sync_double))
        assert await reg.ainvoke("demo.dbl", {"x": 3}) == {"y": 6}


class TestAinvokeErrors:
    @pytest.mark.asyncio
    async def test_unknown_tool_raises_tool_not_found(self):
        reg = _registry(_atom("dbl", _async_double))
        with pytest.raises(ToolNotFound):
            await reg.ainvoke("demo.unknown", {"x": 1})


class TestAinvokeShape:
    def test_ainvoke_is_a_coroutine_function(self):
        reg = _registry(_atom("dbl", _async_double))
        coro = reg.ainvoke("demo.dbl", {"x": 1})
        try:
            assert asyncio.iscoroutine(coro)
        finally:
            coro.close()
