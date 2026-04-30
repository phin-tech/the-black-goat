from __future__ import annotations

import pytest
from pydantic import BaseModel

from the_black_goat import ToolDef, build_registry, durable, hookimpl, tool


class _Input(BaseModel):
    x: int


class _Output(BaseModel):
    y: int


def _double(input: _Input) -> _Output:
    """Sync double."""
    return _Output(y=input.x * 2)


async def _async_double(input: _Input) -> _Output:
    """Async double."""
    return _Output(y=input.x * 2)


def _atom(name: str, func) -> ToolDef:
    return tool(name=name, func=func, input=_Input, output=_Output)


def _plugin(*tools: ToolDef):
    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return list(tools)

    return _P()


class TestInvokeDurable:
    """invoke() on a durable tool spawns via absurd, awaits the result,
    and returns the OutputBM dict."""

    def test_returns_inner_result_via_absurd_path(
        self, absurd_app, background_worker
    ):
        atom = _atom("dbl", _double)
        wrapped = durable(atom, queue=absurd_app._queue_name)
        reg = build_registry(
            plugins={"demo": _plugin(wrapped)},
            absurd=absurd_app,
        )
        result = reg.invoke("demo.dbl", {"x": 7})
        assert result == {"y": 14}

    def test_matches_in_process_atom_result(
        self, absurd_app, background_worker
    ):
        atom = _atom("dbl", _double)
        wrapped = durable(atom, queue=absurd_app._queue_name)

        # Same callable, registered both ways. The durable result must
        # equal the in-process result for the same input.
        atom_for_inproc = _atom("dbl_atom", _double)

        reg = build_registry(
            plugins={"demo": _plugin(wrapped, atom_for_inproc)},
            absurd=absurd_app,
        )

        durable_result = reg.invoke("demo.dbl", {"x": 9})
        inproc_result = reg.invoke("demo.dbl_atom", {"x": 9})

        assert durable_result == inproc_result == {"y": 18}


class TestAinvokeDurable:
    """ainvoke() on a durable tool also spawns via absurd and awaits."""

    @pytest.mark.asyncio
    async def test_async_path_returns_inner_result(
        self, absurd_app, background_worker
    ):
        atom = _atom("dbl", _double)
        wrapped = durable(atom, queue=absurd_app._queue_name)
        reg = build_registry(
            plugins={"demo": _plugin(wrapped)},
            absurd=absurd_app,
        )
        result = await reg.ainvoke("demo.dbl", {"x": 5})
        assert result == {"y": 10}

    @pytest.mark.asyncio
    async def test_async_durable_with_async_inner_func(
        self, absurd_app, background_worker
    ):
        atom = _atom("dbl", _async_double)
        wrapped = durable(atom, queue=absurd_app._queue_name)
        reg = build_registry(
            plugins={"demo": _plugin(wrapped)},
            absurd=absurd_app,
        )
        # The runner uses asyncio.run inside the sync task body to handle
        # async tools; ainvoke awaits the eventual result.
        result = await reg.ainvoke("demo.dbl", {"x": 11})
        assert result == {"y": 22}
