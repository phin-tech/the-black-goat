from __future__ import annotations

from the_black_goat import (
    ToolDef,
    hookimpl,
    tool,
)

from slack_plugin import tools as _tools


_SEND_ARTIFACT = tool(
    name="send_artifact",
    func=_tools.send_artifact,
    input=_tools.SlackSendArtifactInput,
    output=_tools.SlackSendArtifactOutput,
    config=_tools.SlackConfig,
    is_idempotent=False,
    side_effect="writes_external",
    tags=("slack", "delivery"),
)

@hookimpl
def goat_register_tools() -> list[ToolDef]:
    return [_SEND_ARTIFACT]
