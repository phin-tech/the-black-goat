from __future__ import annotations

import dspy
import pytest
from pydantic import BaseModel, ValidationError

from the_black_goat import ToolDef, durable, tool
from the_black_goat.bridges.dspy import to_dspy_tool


class _Input(BaseModel):
    x: int
    label: str = "default"


class _Output(BaseModel):
    y: int


class _Cfg(BaseModel):
    api_key: str


def _double(input: _Input) -> _Output:
    """Double x and ignore label."""
    return _Output(y=input.x * 2)


async def _async_double(input: _Input) -> _Output:
    """Async double."""
    return _Output(y=input.x * 2)


def _bad_output(input: _Input) -> dict:
    """Returns malformed output."""
    return {"wrong": input.x}


def _atom(name: str, func, **kw) -> ToolDef:
    return tool(name=name, func=func, input=_Input, output=_Output, **kw)


class TestToDspyToolShape:
    def test_returns_a_dspy_tool(self):
        td = _atom("dbl", _double).model_copy(update={"plugin": "demo"})
        result = to_dspy_tool(td)
        assert isinstance(result, dspy.Tool)

    def test_name_uses_qualified_name(self):
        td = _atom("dbl", _double).model_copy(update={"plugin": "demo"})
        assert to_dspy_tool(td).name == "demo.dbl"

    def test_desc_uses_record_desc(self):
        td = _atom("dbl", _double).model_copy(update={"plugin": "demo"})
        assert to_dspy_tool(td).desc == "Double x and ignore label."

    def test_args_contains_entry_for_each_input_field(self):
        td = _atom("dbl", _double).model_copy(update={"plugin": "demo"})
        bridged = to_dspy_tool(td)
        assert set(bridged.args.keys()) == {"x", "label"}

    def test_arg_types_map_to_input_field_types(self):
        td = _atom("dbl", _double).model_copy(update={"plugin": "demo"})
        bridged = to_dspy_tool(td)
        assert bridged.arg_types["x"] is int
        assert bridged.arg_types["label"] is str


class TestToDspyToolCall:
    def test_call_runs_underlying_func_and_returns_dict(self):
        td = _atom("dbl", _double).model_copy(update={"plugin": "demo"})
        bridged = to_dspy_tool(td)
        result = bridged(x=5, label="hi")
        assert result == {"y": 10}

    def test_call_rejects_bad_input(self):
        # dspy.Tool's own pre-validation may surface this as ValueError
        # (jsonschema-derived) before our wrapper sees it; either is fine.
        td = _atom("dbl", _double).model_copy(update={"plugin": "demo"})
        bridged = to_dspy_tool(td)
        with pytest.raises((ValueError, ValidationError)):
            bridged(x="not-an-int")

    def test_call_validates_output_via_pydantic(self):
        td = _atom("bad", _bad_output).model_copy(update={"plugin": "demo"})
        bridged = to_dspy_tool(td)
        with pytest.raises(ValidationError):
            bridged(x=1)

    def test_call_uses_default_for_missing_optional_field(self):
        td = _atom("dbl", _double).model_copy(update={"plugin": "demo"})
        bridged = to_dspy_tool(td)
        # `label` has default; x is required.
        assert bridged(x=3) == {"y": 6}


class TestUnsupportedToolKinds:
    """For v1, the bridge refuses tool kinds it doesn't yet support."""

    def test_async_tool_raises_clear_error_when_called(self):
        td = _atom("dbl", _async_double).model_copy(update={"plugin": "demo"})
        bridged = to_dspy_tool(td)
        with pytest.raises(RuntimeError, match=r"async"):
            bridged(x=1)

    def test_config_required_tool_raises_clear_error_when_called(self):
        td = _atom("dbl", _double, config=_Cfg).model_copy(
            update={"plugin": "demo"}
        )
        bridged = to_dspy_tool(td)
        with pytest.raises(RuntimeError, match=r"config"):
            bridged(x=1)


class TestDurableTool:
    """A durable wrapper exposes the same input schema; the bridge calls
    the inner func directly (no absurd dispatch from the dspy bridge)."""

    def test_durable_tool_bridges_with_qualified_name(self):
        atom = _atom("dbl", _double)
        wrapped = durable(atom, max_attempts=3)
        record = wrapped.model_copy(update={"plugin": "demo"})
        bridged = to_dspy_tool(record)
        assert bridged.name == "demo.dbl"
        assert bridged(x=4) == {"y": 8}
