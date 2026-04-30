from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from the_black_goat import ToolDef, build_registry, durable, hookimpl, tool
from the_black_goat.errors import AbsurdNotConfigured, ToolNotFound


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


def _drain_and_get_result(absurd_app, task_id: str):
    """Run one batch of work and fetch the final task result."""
    absurd_app.work_batch()
    return absurd_app.await_task_result(task_id, timeout=5.0)


# ---------- error paths (no DB needed) ----------


class TestEnqueueErrorsNoDB:
    def test_enqueue_without_absurd_raises(self):
        reg = build_registry(plugins={"demo": _plugin(_atom("dbl"))})
        with pytest.raises(AbsurdNotConfigured):
            reg.enqueue("demo.dbl", {"x": 1})

    def test_enqueue_unknown_tool_raises(self):
        # We need an absurd-shaped object so install_runner can attach
        # `goat_run_tool`; we never actually spawn through it.
        class _FakeAbsurd:
            def register_task(self, *, name):
                def _decorator(fn):
                    return fn

                return _decorator

            def spawn(self, *args, **kwargs):
                raise AssertionError("spawn should not be reached")

        reg = build_registry(
            plugins={"demo": _plugin(_atom("dbl"))},
            absurd=_FakeAbsurd(),
        )
        with pytest.raises(ToolNotFound):
            reg.enqueue("demo.unknown", {"x": 1})


# ---------- happy paths (touch Postgres) ----------


class TestEnqueueAtom:
    def test_atom_enqueue_runs_in_worker_and_returns_result(self, absurd_app):
        reg = build_registry(
            plugins={"demo": _plugin(_atom("dbl"))},
            absurd=absurd_app,
        )

        task_id = reg.enqueue("demo.dbl", {"x": 7})
        assert isinstance(task_id, str)

        snapshot = _drain_and_get_result(absurd_app, task_id)
        assert snapshot.state == "completed"
        assert snapshot.result == {"y": 14}

    def test_enqueue_validates_input_before_spawning(self, absurd_app):
        reg = build_registry(
            plugins={"demo": _plugin(_atom("dbl"))},
            absurd=absurd_app,
        )
        with pytest.raises(ValidationError):
            reg.enqueue("demo.dbl", {"x": "not-an-int"})


class TestEnqueueDurable:
    def test_durable_tool_uses_its_durability_spec_queue(self, absurd_app):
        # Place the durable spec on the test's queue so the same fixture
        # processes the task.
        atom = _atom("dbl")
        wrapped = durable(
            atom,
            max_attempts=2,
            queue=absurd_app._queue_name,  # match the fixture's queue
        )
        reg = build_registry(
            plugins={"demo": _plugin(wrapped)},
            absurd=absurd_app,
        )

        task_id = reg.enqueue("demo.dbl", {"x": 6})
        snapshot = _drain_and_get_result(absurd_app, task_id)
        assert snapshot.state == "completed"
        assert snapshot.result == {"y": 12}
