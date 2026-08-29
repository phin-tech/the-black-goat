from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel

from the_black_goat import ToolDef, build_registry, hookimpl, tool


class _FactsQueryInput(BaseModel):
    domain: str | None = None
    date: str | None = None
    starts_from: str | None = None
    starts_until: str | None = None
    limit: int = 100


class _FactsQueryOutput(BaseModel):
    facts: list[dict[str, Any]]


class _SignalsQueryInput(BaseModel):
    status: str | None = None
    limit: int = 100


class _SignalsQueryOutput(BaseModel):
    signals: list[dict[str, Any]]


class _ArtifactPutInput(BaseModel):
    type: str
    title: str
    body: str
    date: str
    generated_by: str
    fact_ids: list[str] = []
    signal_ids: list[str] = []
    payload: dict[str, Any] = {}


class _ArtifactPutOutput(BaseModel):
    id: str


class _SendArtifactInput(BaseModel):
    artifact_id: uuid.UUID


class _SendArtifactOutput(BaseModel):
    channel: str
    ts: str
    receipt_id: str


def _facts_plugin(*tools_: ToolDef):
    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return list(tools_)

    return _P()


def _slack_plugin(send_tool: ToolDef):
    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return [send_tool]

    return _P()


class TestDailyBriefRegistration:
    def test_registers_routine_tool_and_schedule(self):
        import daily_brief_plugin

        reg = build_registry(plugins={"daily_brief": daily_brief_plugin})

        assert [r.qualified_name for r in reg.routines()] == [
            "daily_brief.daily_brief"
        ]
        routine = reg.routine("daily_brief.daily_brief")
        assert routine.schedule == "30 7 * * *"
        assert routine.timezone == "America/New_York"
        assert routine.output_artifact_type == "daily_brief"
        assert routine.delivery_tool == "slack.send_artifact"
        schedule = reg.schedule("daily_brief.daily_brief_730")
        assert schedule.tool == "daily_brief.generate"
        assert schedule.cron == "30 7 * * *"


class TestDailyBriefGenerate:
    def test_generates_artifact_before_delivery(self):
        artifact_id = uuid.uuid4()
        calls: list[str] = []
        artifact_inputs: list[dict[str, Any]] = []
        sent: list[str] = []

        fact = {
            "id": str(uuid.uuid4()),
            "title": "Design review",
            "starts_at": "2026-05-24T13:00:00-04:00",
            "ends_at": "2026-05-24T14:00:00-04:00",
        }
        signal = {
            "id": str(uuid.uuid4()),
            "title": "Prep for design review",
            "summary": "No notes are attached.",
            "severity": "important",
        }

        def facts_query(input: _FactsQueryInput) -> _FactsQueryOutput:
            calls.append("facts.query")
            return _FactsQueryOutput(facts=[fact])

        def signals_query(input: _SignalsQueryInput) -> _SignalsQueryOutput:
            calls.append("facts.signals_query")
            return _SignalsQueryOutput(signals=[signal])

        def artifact_put(input: _ArtifactPutInput) -> _ArtifactPutOutput:
            calls.append("facts.artifact_put")
            artifact_inputs.append(input.model_dump())
            return _ArtifactPutOutput(id=str(artifact_id))

        def send_artifact(input: _SendArtifactInput) -> _SendArtifactOutput:
            calls.append("slack.send_artifact")
            sent.append(str(input.artifact_id))
            return _SendArtifactOutput(
                channel="C123",
                ts="123.456",
                receipt_id="receipt-1",
            )

        import daily_brief_plugin

        reg = build_registry(
            plugins={
                "facts": _facts_plugin(
                    tool(
                        name="query",
                        func=facts_query,
                        input=_FactsQueryInput,
                        output=_FactsQueryOutput,
                    ),
                    tool(
                        name="signals_query",
                        func=signals_query,
                        input=_SignalsQueryInput,
                        output=_SignalsQueryOutput,
                    ),
                    tool(
                        name="artifact_put",
                        func=artifact_put,
                        input=_ArtifactPutInput,
                        output=_ArtifactPutOutput,
                    ),
                ),
                "slack": _slack_plugin(
                    tool(
                        name="send_artifact",
                        func=send_artifact,
                        input=_SendArtifactInput,
                        output=_SendArtifactOutput,
                    )
                ),
                "daily_brief": daily_brief_plugin,
            }
        )

        result = reg.invoke(
            "daily_brief.generate",
            {"date": "2026-05-24", "deliver": True},
        )

        assert calls == [
            "facts.query",
            "facts.signals_query",
            "facts.artifact_put",
            "slack.send_artifact",
        ]
        assert artifact_inputs[0]["type"] == "daily_brief"
        assert artifact_inputs[0]["date"] == "2026-05-24"
        assert artifact_inputs[0]["fact_ids"] == [fact["id"]]
        assert artifact_inputs[0]["signal_ids"] == [signal["id"]]
        assert "Design review" in artifact_inputs[0]["body"]
        assert "Prep for design review" in artifact_inputs[0]["body"]
        assert sent == [str(artifact_id)]
        assert result == {
            "artifact_id": str(artifact_id),
            "delivered": True,
            "receipt_id": "receipt-1",
        }

