from __future__ import annotations

from the_black_goat import ToolDef, hookimpl, tool

from memory_plugin import tools as _tools

_PUT = tool(
    name="put",
    func=_tools.put,
    input=_tools.MemoryPutInput,
    output=_tools.MemoryPutOutput,
    config=_tools.MemoryConfig,
    is_idempotent=True,
    side_effect="writes_external",
    tags=("memory", "kv"),
)

_GET = tool(
    name="get",
    func=_tools.get,
    input=_tools.MemoryGetInput,
    output=_tools.MemoryGetOutput,
    config=_tools.MemoryConfig,
    is_idempotent=True,
    side_effect="reads_external",
    tags=("memory", "kv"),
)


@hookimpl
def goat_register_tools() -> list[ToolDef]:
    return [_PUT, _GET]
