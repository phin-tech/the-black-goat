from __future__ import annotations

import json
import uuid
from typing import Any
from urllib import request

from pydantic import BaseModel, Field, SecretStr

from the_black_goat import current_registry


class SlackConfig(BaseModel):
    bot_token: SecretStr  # env: SLACK_BOT_TOKEN
    default_channel_id: str = Field(min_length=1)  # env: SLACK_DEFAULT_CHANNEL_ID


class SlackSendArtifactInput(BaseModel):
    artifact_id: uuid.UUID
    channel_id: str | None = None


class SlackSendArtifactOutput(BaseModel):
    channel: str
    ts: str
    receipt_id: str


def send_artifact(
    input: SlackSendArtifactInput, *, config: SlackConfig
) -> SlackSendArtifactOutput:
    registry = current_registry()
    artifact_result = registry.invoke(
        "facts.artifact_get",
        {"id": str(input.artifact_id)},
    )
    artifact = artifact_result.get("artifact")
    if artifact is None:
        raise KeyError(str(input.artifact_id))

    channel = input.channel_id or config.default_channel_id
    response = _post_message(
        token=config.bot_token.get_secret_value(),
        channel=channel,
        text=artifact["body"],
    )
    if not response.get("ok"):
        raise RuntimeError(f"slack chat.postMessage failed: {response!r}")

    ts = str(response["ts"])
    receipt = registry.invoke(
        "facts.receipt_put",
        {
            "kind": "slack.message",
            "plugin": "slack",
            "target": channel,
            "external_id": ts,
            "status": "sent",
            "artifact_id": str(input.artifact_id),
            "payload": response,
        },
    )
    return SlackSendArtifactOutput(
        channel=channel,
        ts=ts,
        receipt_id=str(receipt["id"]),
    )


def _post_message(*, token: str, channel: str, text: str) -> dict[str, Any]:
    payload = json.dumps({"channel": channel, "text": text}).encode()
    req = request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode()
    return json.loads(body)

