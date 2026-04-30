from __future__ import annotations

from the_black_goat import ToolDef, hookimpl, tool

from stdlib_plugin import tools as _tools

_NOW = tool(
    name="now",
    func=_tools.now,
    input=_tools.NowInput,
    output=_tools.NowOutput,
    is_idempotent=False,  # different timestamp each call
    side_effect="reads_external",
    tags=("time",),
)

_SLEEP = tool(
    name="sleep",
    func=_tools.sleep,
    input=_tools.SleepInput,
    output=_tools.SleepOutput,
    is_idempotent=True,
    side_effect="pure",
    tags=("time",),
)

_ECHO = tool(
    name="echo",
    func=_tools.echo,
    input=_tools.EchoInput,
    output=_tools.EchoOutput,
    is_idempotent=True,
    side_effect="pure",
    tags=("debug",),
)


@hookimpl
def goat_register_tools() -> list[ToolDef]:
    return [_NOW, _SLEEP, _ECHO]
