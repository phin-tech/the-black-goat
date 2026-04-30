from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from the_black_goat import DurabilitySpec, SideEffect, ToolDef, tool


class _Input(BaseModel):
    x: int


class _Output(BaseModel):
    y: int


def _sync_func(input: _Input) -> _Output:
    """Sync sample tool."""
    return _Output(y=input.x * 2)


async def _async_func(input: _Input) -> _Output:
    """Async sample tool."""
    return _Output(y=input.x * 2)


def _no_docstring_func(input: _Input) -> _Output:
    return _Output(y=input.x)


class TestToolFactory:
    def test_returns_tool_def(self):
        td = tool(name="double", func=_sync_func, input=_Input, output=_Output)
        assert isinstance(td, ToolDef)

    def test_short_name_unprefixed_until_registry(self):
        td = tool(name="double", func=_sync_func, input=_Input, output=_Output)
        assert td.name == "double"
        assert td.plugin == ""

    def test_desc_inferred_from_docstring(self):
        td = tool(name="double", func=_sync_func, input=_Input, output=_Output)
        assert td.desc == "Sync sample tool."

    def test_explicit_desc_overrides_docstring(self):
        td = tool(
            name="double",
            func=_sync_func,
            input=_Input,
            output=_Output,
            desc="Custom description.",
        )
        assert td.desc == "Custom description."

    def test_is_async_false_for_sync(self):
        td = tool(name="double", func=_sync_func, input=_Input, output=_Output)
        assert td.is_async is False

    def test_is_async_true_for_async(self):
        td = tool(name="double", func=_async_func, input=_Input, output=_Output)
        assert td.is_async is True

    def test_default_metadata(self):
        td = tool(name="double", func=_sync_func, input=_Input, output=_Output)
        assert td.is_idempotent is False
        assert td.side_effect == "writes_external"
        assert td.requires_confirmation is False
        assert td.tags == ()
        assert td.config_schema is None
        assert td.durability is None

    def test_metadata_overrides(self):
        td = tool(
            name="double",
            func=_sync_func,
            input=_Input,
            output=_Output,
            is_idempotent=True,
            side_effect="pure",
            requires_confirmation=True,
            tags=("sample", "test"),
        )
        assert td.is_idempotent is True
        assert td.side_effect == "pure"
        assert td.requires_confirmation is True
        assert td.tags == ("sample", "test")

    def test_config_schema_captured(self):
        class _Cfg(BaseModel):
            api_key: str

        td = tool(
            name="double",
            func=_sync_func,
            input=_Input,
            output=_Output,
            config=_Cfg,
        )
        assert td.config_schema is _Cfg

    def test_schemas_stored(self):
        td = tool(name="double", func=_sync_func, input=_Input, output=_Output)
        assert td.input_schema is _Input
        assert td.output_schema is _Output

    def test_func_stored(self):
        td = tool(name="double", func=_sync_func, input=_Input, output=_Output)
        assert td.func is _sync_func

    def test_desc_empty_when_no_docstring_and_no_explicit(self):
        td = tool(
            name="bare",
            func=_no_docstring_func,
            input=_Input,
            output=_Output,
        )
        assert td.desc == ""

    def test_tags_list_converted_to_tuple(self):
        td = tool(
            name="x",
            func=_sync_func,
            input=_Input,
            output=_Output,
            tags=["a", "b"],
        )
        assert td.tags == ("a", "b")
        assert isinstance(td.tags, tuple)


class TestToolDefBareConstruction:
    """ToolDef defaults when constructed directly (not through tool() factory)."""

    def _bare(self, **overrides) -> ToolDef:
        kwargs = dict(
            name="raw",
            func=_sync_func,
            input_schema=_Input,
            output_schema=_Output,
        )
        kwargs.update(overrides)
        return ToolDef(**kwargs)

    def test_plugin_defaults_to_empty_string(self):
        assert self._bare().plugin == ""

    def test_desc_defaults_to_empty_string(self):
        assert self._bare().desc == ""

    def test_config_schema_defaults_to_none(self):
        assert self._bare().config_schema is None

    def test_is_async_defaults_to_false(self):
        # Note: bare construction does NOT auto-detect; that is the factory's job.
        assert self._bare().is_async is False

    def test_is_idempotent_defaults_to_false(self):
        assert self._bare().is_idempotent is False

    def test_side_effect_defaults_to_writes_external(self):
        assert self._bare().side_effect == "writes_external"

    def test_requires_confirmation_defaults_to_false(self):
        assert self._bare().requires_confirmation is False

    def test_tags_defaults_to_empty_tuple(self):
        assert self._bare().tags == ()

    def test_durability_defaults_to_none(self):
        assert self._bare().durability is None


class TestToolDefQualifiedName:
    def test_qualified_name_combines_plugin_and_name(self):
        td = tool(
            name="double", func=_sync_func, input=_Input, output=_Output
        ).model_copy(update={"plugin": "demo"})
        assert td.qualified_name == "demo.double"

    def test_qualified_name_falls_back_when_plugin_unset(self):
        td = tool(name="double", func=_sync_func, input=_Input, output=_Output)
        # Without a plugin yet, qualified_name is exactly the short name.
        assert td.qualified_name == td.name == "double"


class TestToolDefFrozen:
    def test_cannot_mutate_after_construction(self):
        td = tool(name="double", func=_sync_func, input=_Input, output=_Output)
        with pytest.raises(ValidationError):
            td.name = "tripled"  # type: ignore[misc]


class TestDurabilitySpec:
    def test_defaults(self):
        spec = DurabilitySpec()
        assert spec.queue == "default"
        assert spec.max_attempts is None
        assert spec.retry_strategy is None
        assert spec.cancellation is None

    def test_frozen(self):
        spec = DurabilitySpec(max_attempts=3)
        with pytest.raises(ValidationError):
            spec.max_attempts = 5  # type: ignore[misc]


class TestSideEffectValues:
    def test_accepts_documented_values(self):
        for value in (
            "pure",
            "reads_external",
            "writes_external",
            "human_interaction",
            "spends_money",
        ):
            td = tool(
                name="x",
                func=_sync_func,
                input=_Input,
                output=_Output,
                side_effect=value,  # type: ignore[arg-type]
            )
            assert td.side_effect == value

    def test_rejects_undocumented_value(self):
        with pytest.raises(ValidationError):
            tool(
                name="x",
                func=_sync_func,
                input=_Input,
                output=_Output,
                side_effect="bogus",  # type: ignore[arg-type]
            )
