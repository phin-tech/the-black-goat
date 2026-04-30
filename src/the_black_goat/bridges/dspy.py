from __future__ import annotations

import dspy

from the_black_goat.tools import ToolDef


def to_dspy_tool(record: ToolDef) -> dspy.Tool:
    """Wrap a ToolDef as a dspy.Tool for LLM tool-use.

    The returned Tool exposes:
    - `name`     == record.qualified_name
    - `desc`     == record.desc
    - `args`     == per-field JSON schema dict from input_schema
    - `arg_types`== per-field Python type from input_schema

    Calling the returned Tool with kwargs validates input via Pydantic,
    invokes the underlying func, and validates output via Pydantic.
    Returns the output as a plain dict (model_dump).

    v1 limitations (raise RuntimeError on call):
    - async tools (use the registry's `ainvoke` directly).
    - tools requiring config (no config-bound bridge yet).
    Durable wrappers are bridged via their inner func — durability metadata
    is ignored at the bridge level (the dspy use case is in-process LLM
    tool-calling, not durable execution).
    """
    schema = record.input_schema.model_json_schema()
    properties = schema.get("properties", {})

    args = {name: prop_schema for name, prop_schema in properties.items()}
    arg_types = {
        field_name: field_info.annotation
        for field_name, field_info in record.input_schema.model_fields.items()
    }

    qualified_name = record.qualified_name
    desc = record.desc
    input_schema = record.input_schema
    output_schema = record.output_schema
    is_async = record.is_async
    needs_config = record.config_schema is not None
    func = record.func

    def _wrapped(**kwargs):
        if needs_config:
            raise RuntimeError(
                f"tool {qualified_name!r} requires config; the dspy "
                "bridge does not yet support config-required tools"
            )
        if is_async:
            raise RuntimeError(
                f"tool {qualified_name!r} is async; the dspy bridge does "
                "not yet support async tools (use registry.ainvoke directly)"
            )
        input_obj = input_schema.model_validate(kwargs)
        result = func(input_obj)
        if isinstance(result, output_schema):
            output = result
        else:
            output = output_schema.model_validate(result)
        return output.model_dump()

    _wrapped.__name__ = qualified_name.replace(".", "_") or "tool"
    _wrapped.__doc__ = desc

    return dspy.Tool(
        _wrapped,
        name=qualified_name,
        desc=desc,
        args=args,
        arg_types=arg_types,
    )
