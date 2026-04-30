from __future__ import annotations

import pytest
from pydantic import BaseModel

from the_black_goat import DurabilitySpec, ToolDef, durable, tool


class _Input(BaseModel):
    x: int


class _Output(BaseModel):
    y: int


class _Cfg(BaseModel):
    api_key: str


def _impl(input: _Input) -> _Output:
    """Sample impl."""
    return _Output(y=input.x)


async def _async_impl(input: _Input) -> _Output:
    """Async sample impl."""
    return _Output(y=input.x)


def _atom(**overrides) -> ToolDef:
    kwargs = dict(
        name="sample",
        func=_impl,
        input=_Input,
        output=_Output,
        config=_Cfg,
        is_idempotent=True,
        side_effect="spends_money",
        requires_confirmation=True,
        tags=("a", "b"),
    )
    kwargs.update(overrides)
    return tool(**kwargs)


class TestDurableWrapper:
    def test_returns_new_tooldef_instance(self):
        atom = _atom()
        wrapped = durable(atom)
        assert isinstance(wrapped, ToolDef)
        assert wrapped is not atom

    def test_inner_atom_not_mutated(self):
        atom = _atom()
        durable(atom, max_attempts=3)
        assert atom.durability is None

    def test_durability_default_queue(self):
        wrapped = durable(_atom())
        assert wrapped.durability is not None
        assert wrapped.durability.queue == "default"

    def test_durability_default_other_fields(self):
        wrapped = durable(_atom())
        assert wrapped.durability.retry_strategy is None
        assert wrapped.durability.max_attempts is None
        assert wrapped.durability.cancellation is None

    def test_durability_max_attempts_captured(self):
        wrapped = durable(_atom(), max_attempts=5)
        assert wrapped.durability.max_attempts == 5

    def test_durability_queue_captured(self):
        wrapped = durable(_atom(), queue="critical")
        assert wrapped.durability.queue == "critical"

    def test_durability_retry_strategy_captured(self):
        rs = {"kind": "exponential", "base_seconds": 1.0, "max_seconds": 60.0}
        wrapped = durable(_atom(), retry_strategy=rs)
        assert wrapped.durability.retry_strategy == rs

    def test_durability_cancellation_captured(self):
        cp = {"max_duration": 600, "max_delay": 30}
        wrapped = durable(_atom(), cancellation=cp)
        assert wrapped.durability.cancellation == cp

    def test_durability_is_a_DurabilitySpec(self):
        wrapped = durable(_atom(), max_attempts=2)
        assert isinstance(wrapped.durability, DurabilitySpec)


class TestDurableWrapperPreserves:
    """The wrapper must share name / schemas / func / metadata with the inner tool."""

    def test_name_preserved(self):
        atom = _atom()
        assert durable(atom).name == atom.name == "sample"

    def test_func_preserved(self):
        atom = _atom()
        assert durable(atom).func is atom.func is _impl

    def test_schemas_preserved(self):
        atom = _atom()
        wrapped = durable(atom)
        assert wrapped.input_schema is atom.input_schema is _Input
        assert wrapped.output_schema is atom.output_schema is _Output

    def test_config_schema_preserved(self):
        atom = _atom()
        wrapped = durable(atom)
        assert wrapped.config_schema is atom.config_schema is _Cfg

    def test_desc_preserved(self):
        atom = _atom()
        assert durable(atom).desc == atom.desc

    def test_metadata_preserved(self):
        atom = _atom()
        wrapped = durable(atom)
        assert wrapped.is_idempotent is atom.is_idempotent is True
        assert wrapped.side_effect == atom.side_effect == "spends_money"
        assert wrapped.requires_confirmation is atom.requires_confirmation is True
        assert wrapped.tags == atom.tags == ("a", "b")

    def test_is_async_preserved_for_sync(self):
        atom = _atom(func=_impl)
        assert durable(atom).is_async is False

    def test_is_async_preserved_for_async(self):
        atom = _atom(func=_async_impl)
        assert durable(atom).is_async is True

    def test_plugin_preserved(self):
        # If inner has a plugin set (post-registry), the wrapper inherits it.
        atom = _atom().model_copy(update={"plugin": "demo"})
        wrapped = durable(atom)
        assert wrapped.plugin == "demo"
        assert wrapped.qualified_name == "demo.sample"


class TestDurableDoubleWrap:
    def test_double_wrap_raises(self):
        atom = _atom()
        first = durable(atom, max_attempts=3)
        with pytest.raises(ValueError, match=r"already durable"):
            durable(first, max_attempts=5)
