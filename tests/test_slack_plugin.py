from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel

from the_black_goat import ToolDef, build_registry, hookimpl, tool
from the_black_goat.config import DictConfigSource


class _ArtifactGetInput(BaseModel):
    id: uuid.UUID


class _ArtifactGetOutput(BaseModel):
    artifact: dict[str, Any] | None = None


class _ReceiptPutInput(BaseModel):
    kind: str
    plugin: str
    target: str
    external_id: str
    status: str
    artifact_id: uuid.UUID
    payload: dict[str, Any] = {}


class _ReceiptPutOutput(BaseModel):
    id: str
    artifact_id: str


def _facts_plugin(*tools_: ToolDef):
    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return list(tools_)

    return _P()


class TestSlackPluginRegistration:
    def test_registers_send_artifact_tool(self):
        import slack_plugin

        reg = build_registry(
            plugins={"slack": slack_plugin},
            config_source=DictConfigSource(
                {
                    "slack": {
                        "bot_token": "xoxb-test",
                        "default_channel_id": "C123",
                    }
                }
            ),
        )

        assert [t.qualified_name for t in reg.by_plugin("slack")] == [
            "slack.send_artifact"
        ]


class TestSlackSendArtifact:
    def test_sends_artifact_body_and_writes_receipt(self, monkeypatch):
        artifact_id = uuid.uuid4()
        receipts: list[dict[str, Any]] = []
        posted: list[dict[str, Any]] = []

        def artifact_get(input: _ArtifactGetInput) -> _ArtifactGetOutput:
            assert input.id == artifact_id
            return _ArtifactGetOutput(
                artifact={
                    "id": str(artifact_id),
                    "type": "daily_brief",
                    "title": "Daily brief",
                    "body": "Today: design review.",
                }
            )

        def receipt_put(input: _ReceiptPutInput) -> _ReceiptPutOutput:
            receipts.append(input.model_dump())
            return _ReceiptPutOutput(
                id="receipt-1",
                artifact_id=str(input.artifact_id),
            )

        import slack_plugin
        from slack_plugin import tools as slack_tools

        def fake_post_message(*, token: str, channel: str, text: str):
            posted.append({"token": token, "channel": channel, "text": text})
            return {"ok": True, "channel": channel, "ts": "123.456"}

        monkeypatch.setattr(slack_tools, "_post_message", fake_post_message)

        reg = build_registry(
            plugins={
                "facts": _facts_plugin(
                    tool(
                        name="artifact_get",
                        func=artifact_get,
                        input=_ArtifactGetInput,
                        output=_ArtifactGetOutput,
                    ),
                    tool(
                        name="receipt_put",
                        func=receipt_put,
                        input=_ReceiptPutInput,
                        output=_ReceiptPutOutput,
                    ),
                ),
                "slack": slack_plugin,
            },
            config_source=DictConfigSource(
                {
                    "slack": {
                        "bot_token": "xoxb-test",
                        "default_channel_id": "C123",
                    }
                }
            ),
        )

        result = reg.invoke("slack.send_artifact", {"artifact_id": str(artifact_id)})

        assert posted == [
            {
                "token": "xoxb-test",
                "channel": "C123",
                "text": "Today: design review.",
            }
        ]
        assert receipts[0]["kind"] == "slack.message"
        assert receipts[0]["artifact_id"] == artifact_id
        assert result == {
            "channel": "C123",
            "ts": "123.456",
            "receipt_id": "receipt-1",
        }

