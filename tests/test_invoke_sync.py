from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from the_black_goat import ToolDef, build_registry, hookimpl, tool
from the_black_goat.errors import ToolKindMismatch, ToolNotFound


class _Input(BaseModel):
    x: int


class _Output(BaseModel):
    y: int


def _double(input: _Input) -> _Output:
    """Double x."""
    return _Output(y=input.x * 2)


def _double_returns_dict(input: _Input) -> dict:
    """Returns a dict matching _Output."""
    return {"y": input.x * 2}


def _bad_output(input: _Input) -> dict:
    """Returns something that does NOT match _Output."""
    return {"wrong_field": input.x}


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


def _registry(*tools: ToolDef):
    return build_registry(plugins={"demo": _plugin(*tools)})


class TestInvokeReturnsDict:
    def test_invoke_returns_dict_from_output_model(self):
        reg = _registry(_atom("double", _double))
        result = reg.invoke("demo.double", {"x": 4})
        assert result == {"y": 8}

    def test_invoke_validates_dict_returned_by_tool(self):
        # If the tool returns a dict, the registry validates it against
        # the output schema and emits a dict.
        reg = _registry(_atom("double", _double_returns_dict))
        result = reg.invoke("demo.double", {"x": 5})
        assert result == {"y": 10}


class TestInvokeInputValidation:
    def test_missing_required_field_raises_validation_error(self):
        reg = _registry(_atom("double", _double))
        with pytest.raises(ValidationError):
            reg.invoke("demo.double", {})

    def test_wrong_type_raises_validation_error(self):
        reg = _registry(_atom("double", _double))
        with pytest.raises(ValidationError):
            reg.invoke("demo.double", {"x": "not-an-int"})

    def test_input_validation_runs_before_tool_body(self):
        called = []

        def _records_call(input: _Input) -> _Output:
            called.append(input)
            return _Output(y=input.x)

        reg = _registry(_atom("noop", _records_call))
        with pytest.raises(ValidationError):
            reg.invoke("demo.noop", {})
        assert called == []


class TestInvokeOutputValidation:
    def test_bad_output_raises_validation_error(self):
        reg = _registry(_atom("bad", _bad_output))
        with pytest.raises(ValidationError):
            reg.invoke("demo.bad", {"x": 1})


class TestInvokeErrorsForKindAndLookup:
    def test_unknown_tool_raises_tool_not_found(self):
        reg = _registry(_atom("double", _double))
        with pytest.raises(ToolNotFound):
            reg.invoke("demo.unknown", {"x": 1})

    def test_async_tool_raises_kind_mismatch(self):
        reg = _registry(_atom("async_double", _async_double))
        with pytest.raises(ToolKindMismatch):
            reg.invoke("demo.async_double", {"x": 1})


class TestInvokeNoConfig:
    def test_tool_without_config_called_without_config_kwarg(self):
        # _double accepts only `input`. Calling it should not error with
        # 'unexpected keyword argument config'.
        reg = _registry(_atom("double", _double))
        assert reg.invoke("demo.double", {"x": 3}) == {"y": 6}
