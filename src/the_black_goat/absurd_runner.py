from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from the_black_goat.registry import Registry


GOAT_RUN_TOOL_NAME = "goat_run_tool"


def install_runner(absurd: Any, registry: "Registry") -> None:
    """Register the generic `goat_run_tool` task on the given absurd app.

    The task receives `{"tool": qualified_name, "input": dict}` and dispatches
    to the registry's in-process invocation flow. Async tools are run via
    asyncio.run inside the sync task body so a single task definition
    handles both sync and async tools.
    """

    @absurd.register_task(name=GOAT_RUN_TOOL_NAME)
    def goat_run_tool(params, ctx):  # pragma: no cover - covered via end-to-end
        tool_name = params["tool"]
        tool_input = params["input"]
        record = registry.get(tool_name)
        if record.is_async:
            return asyncio.run(registry._ainvoke_in_process(record, tool_input))
        return registry._invoke_in_process(record, tool_input)
