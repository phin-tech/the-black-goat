from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from the_black_goat import SignalDefinition, SignalProposal, ToolDef, hookimpl, tool
from the_black_goat.config import DictConfigSource
from the_black_goat.registry import build_registry


class _StateGetInput(BaseModel):
    plugin: str
    account: str = ""
    key: str


class _StateGetOutput(BaseModel):
    value: dict[str, Any] | None = None


class _StatePutInput(BaseModel):
    plugin: str
    account: str = ""
    key: str
    value: dict[str, Any]


class _StatePutOutput(BaseModel):
    updated_at: str = "2026-05-24T00:00:00Z"


class _FactUpsertInput(BaseModel):
    domain: str
    type: str
    source_plugin: str
    source_account: str
    external_id: str
    subject: str
    title: str | None = None
    body: str | None = None
    status: str | None = None
    date: str | None = None
    starts_at: str | None = None
    ends_at: str | None = None
    payload: dict[str, Any] = {}


class _FactUpsertOutput(BaseModel):
    id: str


class _FactGetInput(BaseModel):
    id: uuid.UUID


class _FactGetOutput(BaseModel):
    fact: dict[str, Any] | None = None


class _FactsQueryInput(BaseModel):
    domain: str | None = None
    date: str | None = None
    starts_from: str | None = None
    starts_until: str | None = None
    limit: int = 100


class _FactsQueryOutput(BaseModel):
    facts: list[dict[str, Any]]


class _SignalPutInput(BaseModel):
    definition_name: str
    dedupe_key: str
    domain: str
    kind: str
    title: str
    summary: str
    severity: str
    confidence: float
    generated_by: str
    fact_ids: list[str]
    payload: dict[str, Any] = {}


class _SignalPutOutput(BaseModel):
    id: str


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


class _ArtifactGetInput(BaseModel):
    id: uuid.UUID


class _ArtifactGetOutput(BaseModel):
    artifact: dict[str, Any] | None = None


class _ReceiptPutInput(BaseModel):
    kind: str
    plugin: str
    target: str | None = None
    external_id: str | None = None
    status: str
    artifact_id: uuid.UUID | None = None
    payload: dict[str, Any] = {}


class _ReceiptPutOutput(BaseModel):
    id: str
    artifact_id: str | None = None


class _ProposalInput(BaseModel):
    definition: dict[str, Any]
    params: dict[str, Any] = {}


class _ProposalOutput(BaseModel):
    proposals: list[SignalProposal]


class _Store:
    def __init__(self):
        self.state: dict[str, dict[str, Any]] = {}
        self.facts: dict[str, dict[str, Any]] = {}
        self.signals: dict[str, dict[str, Any]] = {}
        self.artifacts: dict[str, dict[str, Any]] = {}
        self.receipts: list[dict[str, Any]] = []

    def state_get(self, input: _StateGetInput) -> _StateGetOutput:
        return _StateGetOutput(value=self.state.get(input.key))

    def state_put(self, input: _StatePutInput) -> _StatePutOutput:
        self.state[input.key] = input.value
        return _StatePutOutput()

    def upsert(self, input: _FactUpsertInput) -> _FactUpsertOutput:
        fact_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{input.source_plugin}:{input.source_account}:{input.external_id}:{input.type}",
            )
        )
        fact = {**input.model_dump(), "id": fact_id}
        self.facts[fact_id] = fact
        return _FactUpsertOutput(id=fact_id)

    def get(self, input: _FactGetInput) -> _FactGetOutput:
        return _FactGetOutput(fact=self.facts.get(str(input.id)))

    def query(self, input: _FactsQueryInput) -> _FactsQueryOutput:
        facts = [
            fact
            for fact in self.facts.values()
            if (input.domain is None or fact["domain"] == input.domain)
            and (input.date is None or fact["date"] == input.date)
        ]
        return _FactsQueryOutput(facts=facts)

    def signal_put(self, input: _SignalPutInput) -> _SignalPutOutput:
        signal_id = "signal-" + input.dedupe_key.replace(":", "-")
        self.signals[signal_id] = {**input.model_dump(), "id": signal_id}
        return _SignalPutOutput(id=signal_id)

    def signals_query(self, input: _SignalsQueryInput) -> _SignalsQueryOutput:
        return _SignalsQueryOutput(signals=list(self.signals.values()))

    def artifact_put(self, input: _ArtifactPutInput) -> _ArtifactPutOutput:
        artifact_id = str(uuid.uuid4())
        self.artifacts[artifact_id] = {**input.model_dump(), "id": artifact_id}
        return _ArtifactPutOutput(id=artifact_id)

    def artifact_get(self, input: _ArtifactGetInput) -> _ArtifactGetOutput:
        return _ArtifactGetOutput(artifact=self.artifacts.get(str(input.id)))

    def receipt_put(self, input: _ReceiptPutInput) -> _ReceiptPutOutput:
        receipt_id = "receipt-" + str(len(self.receipts) + 1)
        receipt = {**input.model_dump(), "id": receipt_id}
        self.receipts.append(receipt)
        return _ReceiptPutOutput(
            id=receipt_id,
            artifact_id=str(input.artifact_id) if input.artifact_id else None,
        )


def _facts_plugin(store: _Store):
    tools = [
        tool(name="state_get", func=store.state_get, input=_StateGetInput, output=_StateGetOutput),
        tool(name="state_put", func=store.state_put, input=_StatePutInput, output=_StatePutOutput),
        tool(name="upsert", func=store.upsert, input=_FactUpsertInput, output=_FactUpsertOutput),
        tool(name="get", func=store.get, input=_FactGetInput, output=_FactGetOutput),
        tool(name="query", func=store.query, input=_FactsQueryInput, output=_FactsQueryOutput),
        tool(name="signal_put", func=store.signal_put, input=_SignalPutInput, output=_SignalPutOutput),
        tool(name="signals_query", func=store.signals_query, input=_SignalsQueryInput, output=_SignalsQueryOutput),
        tool(name="artifact_put", func=store.artifact_put, input=_ArtifactPutInput, output=_ArtifactPutOutput),
        tool(name="artifact_get", func=store.artifact_get, input=_ArtifactGetInput, output=_ArtifactGetOutput),
        tool(name="receipt_put", func=store.receipt_put, input=_ReceiptPutInput, output=_ReceiptPutOutput),
    ]

    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return tools

    return _P()


def _calendar_signals_plugin(store: _Store):
    def propose(input: _ProposalInput) -> _ProposalOutput:
        [fact] = list(store.facts.values())
        return _ProposalOutput(
            proposals=[
                SignalProposal(
                    dedupe_key="prep:" + fact["id"],
                    domain="calendar",
                    kind="prep_needed",
                    title="Prep for " + fact["title"],
                    summary="No notes are attached.",
                    severity="important",
                    confidence=0.9,
                    generated_by="calendar_signals.propose",
                    fact_ids=[fact["id"]],
                )
            ]
        )

    generator = tool(
        name="propose",
        func=propose,
        input=_ProposalInput,
        output=_ProposalOutput,
    )
    definition = SignalDefinition(
        name="prep_needed",
        domain="calendar",
        kind="prep_needed",
        title="Prep needed",
        generator_tool="calendar_signals.propose",
        min_confidence=0.8,
    )

    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return [generator]

        @hookimpl
        def goat_register_signal_definitions(self) -> list[SignalDefinition]:
            return [definition]

    return _P()


def test_calendar_to_signal_to_daily_brief_to_slack(monkeypatch):
    import daily_brief_plugin
    import google_calendar_plugin
    import signals_plugin
    import slack_plugin
    from google_calendar_plugin import tools as calendar_tools
    from slack_plugin import tools as slack_tools

    store = _Store()
    posted: list[dict[str, Any]] = []

    def fake_fetch_events(*, access_token, calendar_id, sync_token, time_min):
        return {
            "nextSyncToken": "next-token",
            "items": [
                {
                    "id": "evt_1",
                    "status": "confirmed",
                    "summary": "Design review",
                    "description": "Review mocks",
                    "start": {"dateTime": "2026-05-24T13:00:00-04:00"},
                    "end": {"dateTime": "2026-05-24T14:00:00-04:00"},
                }
            ],
        }

    def fake_post_message(*, token: str, channel: str, text: str):
        posted.append({"channel": channel, "text": text})
        return {"ok": True, "channel": channel, "ts": "123.456"}

    monkeypatch.setattr(calendar_tools, "_fetch_events", fake_fetch_events)
    monkeypatch.setattr(slack_tools, "_post_message", fake_post_message)

    reg = build_registry(
        plugins={
            "facts": _facts_plugin(store),
            "google_calendar": google_calendar_plugin,
            "calendar_signals": _calendar_signals_plugin(store),
            "signals": signals_plugin,
            "daily_brief": daily_brief_plugin,
            "slack": slack_plugin,
        },
        config_source=DictConfigSource(
            {
                "google_calendar": {
                    "calendar_id": "primary",
                    "access_token": "token",
                },
                "slack": {
                    "bot_token": "xoxb-test",
                    "default_channel_id": "C123",
                },
            }
        ),
    )

    assert reg.invoke("google_calendar.sync", {}) == {
        "events_seen": 1,
        "facts_written": 1,
    }
    assert reg.invoke("signals.generate", {})["generated"][0][
        "definition_name"
    ] == "calendar_signals.prep_needed"
    result = reg.invoke(
        "daily_brief.generate",
        {"date": "2026-05-24", "deliver": True},
    )

    artifact = store.artifacts[result["artifact_id"]]
    assert result["delivered"] is True
    assert "Design review" in artifact["body"]
    assert "Prep for Design review" in artifact["body"]
    assert posted[0]["channel"] == "C123"
    assert posted[0]["text"] == artifact["body"]
    assert store.receipts[-1]["kind"] == "slack.message"
    assert store.receipts[-1]["artifact_id"] == uuid.UUID(result["artifact_id"])
    assert store.state["next_sync_token"] == {"token": "next-token"}


def test_calendar_to_daily_brief_flow_with_real_postgres(pg_url, monkeypatch):
    import daily_brief_plugin
    import facts_plugin
    import google_calendar_plugin
    import signals_plugin
    import slack_plugin
    from google_calendar_plugin import tools as calendar_tools
    from psycopg import Connection
    from slack_plugin import tools as slack_tools
    from the_black_goat import current_registry

    with Connection.connect(pg_url, autocommit=True) as conn:
        conn.cursor().execute(open("db/memory.sql").read())

    event_id = "evt_" + uuid.uuid4().hex
    account = "primary_" + uuid.uuid4().hex[:8]
    event_date = "2031-01-17"
    starts_at = event_date + "T13:00:00-05:00"
    ends_at = event_date + "T14:00:00-05:00"
    posted: list[dict[str, Any]] = []

    def fake_fetch_events(*, access_token, calendar_id, sync_token, time_min):
        return {
            "nextSyncToken": "next-token-" + event_id,
            "items": [
                {
                    "id": event_id,
                    "status": "confirmed",
                    "summary": "Design review",
                    "description": "Review mocks",
                    "start": {"dateTime": starts_at},
                    "end": {"dateTime": ends_at},
                }
            ],
        }

    def fake_post_message(*, token: str, channel: str, text: str):
        posted.append({"channel": channel, "text": text})
        return {"ok": True, "channel": channel, "ts": "123.456"}

    def propose(input: _ProposalInput) -> _ProposalOutput:
        facts = current_registry().invoke(
            "facts.query",
            {
                "domain": "calendar",
                "source_account": account,
                "date": event_date,
                "limit": 1,
            },
        )["facts"]
        [fact] = facts
        return _ProposalOutput(
            proposals=[
                SignalProposal(
                    dedupe_key="prep:" + fact["id"],
                    domain="calendar",
                    kind="prep_needed",
                    title="Prep for " + fact["title"],
                    summary="No notes are attached.",
                    severity="important",
                    confidence=0.9,
                    generated_by="calendar_signals.propose",
                    fact_ids=[fact["id"]],
                )
            ]
        )

    generator = tool(
        name="propose",
        func=propose,
        input=_ProposalInput,
        output=_ProposalOutput,
    )
    definition = SignalDefinition(
        name="prep_needed",
        domain="calendar",
        kind="prep_needed",
        title="Prep needed",
        generator_tool="calendar_signals.propose",
        min_confidence=0.8,
    )

    class CalendarSignalsPlugin:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return [generator]

        @hookimpl
        def goat_register_signal_definitions(self) -> list[SignalDefinition]:
            return [definition]

    monkeypatch.setattr(calendar_tools, "_fetch_events", fake_fetch_events)
    monkeypatch.setattr(slack_tools, "_post_message", fake_post_message)

    reg = build_registry(
        plugins={
            "facts": facts_plugin,
            "google_calendar": google_calendar_plugin,
            "calendar_signals": CalendarSignalsPlugin(),
            "signals": signals_plugin,
            "daily_brief": daily_brief_plugin,
            "slack": slack_plugin,
        },
        config_source=DictConfigSource(
            {
                "facts": {"database_url": pg_url},
                "google_calendar": {
                    "calendar_id": account,
                    "access_token": "token",
                },
                "slack": {
                    "bot_token": "xoxb-test",
                    "default_channel_id": "C123",
                },
            }
        ),
    )

    assert reg.invoke("google_calendar.sync", {}) == {
        "events_seen": 1,
        "facts_written": 1,
    }
    generated = reg.invoke("signals.generate", {})["generated"]
    result = reg.invoke(
        "daily_brief.generate",
        {"date": event_date, "deliver": True},
    )
    artifact = reg.invoke("facts.artifact_get", {"id": result["artifact_id"]})[
        "artifact"
    ]
    receipts = reg.invoke(
        "facts.receipts_query",
        {"artifact_id": result["artifact_id"], "kind": "slack.message"},
    )["receipts"]

    assert generated[0]["definition_name"] == "calendar_signals.prep_needed"
    assert result["delivered"] is True
    assert result["receipt_id"] == receipts[0]["id"]
    assert "Design review" in artifact["body"]
    assert "Prep for Design review" in artifact["body"]
    assert posted[0]["text"] == artifact["body"]
    assert receipts[0]["status"] == "sent"
