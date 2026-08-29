from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from the_black_goat import ToolDef, build_registry, hookimpl, tool
from the_black_goat.config import DictConfigSource


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


class _ReceiptPutInput(BaseModel):
    kind: str
    plugin: str
    target: str | None = None
    external_id: str | None = None
    status: str
    payload: dict[str, Any] = {}


class _ReceiptPutOutput(BaseModel):
    id: str


def _facts_plugin(*tools_: ToolDef):
    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return list(tools_)

    return _P()


class TestGoogleCalendarRegistration:
    def test_registers_source_tool_and_schedule(self):
        import google_calendar_plugin

        reg = build_registry(
            plugins={"google_calendar": google_calendar_plugin},
            config_source=DictConfigSource(
                {
                    "google_calendar": {
                        "calendar_id": "primary",
                        "access_token": "token",
                    }
                }
            ),
        )

        assert [s.qualified_name for s in reg.sources()] == [
            "google_calendar.primary"
        ]
        assert [t.qualified_name for t in reg.by_plugin("google_calendar")] == [
            "google_calendar.sync"
        ]
        schedule = reg.schedule("google_calendar.sync_every_3_hours")
        assert schedule.tool == "google_calendar.sync"
        assert schedule.cron == "0 */3 * * *"


class TestGoogleCalendarSync:
    def test_sync_writes_calendar_facts_state_and_receipt(self, monkeypatch):
        state: dict[str, dict[str, Any]] = {}
        facts: list[dict[str, Any]] = []
        receipts: list[dict[str, Any]] = []

        def state_get(input: _StateGetInput) -> _StateGetOutput:
            return _StateGetOutput(value=state.get(input.key))

        def state_put(input: _StatePutInput) -> _StatePutOutput:
            state[input.key] = input.value
            return _StatePutOutput()

        def upsert(input: _FactUpsertInput) -> _FactUpsertOutput:
            facts.append(input.model_dump())
            return _FactUpsertOutput(id="fact-" + input.external_id)

        def receipt_put(input: _ReceiptPutInput) -> _ReceiptPutOutput:
            receipts.append(input.model_dump())
            return _ReceiptPutOutput(id="receipt-1")

        import google_calendar_plugin
        from google_calendar_plugin import tools as calendar_tools

        def fake_fetch_events(*, access_token, calendar_id, sync_token, time_min):
            assert access_token == "token"
            assert calendar_id == "primary"
            assert sync_token is None
            assert time_min is not None
            return {
                "nextSyncToken": "next-token",
                "items": [
                    {
                        "id": "evt_1",
                        "status": "confirmed",
                        "summary": "Design review",
                        "description": "Review mocks",
                        "location": "Meet",
                        "start": {
                            "dateTime": "2026-05-24T13:00:00-04:00",
                            "timeZone": "America/New_York",
                        },
                        "end": {
                            "dateTime": "2026-05-24T14:00:00-04:00",
                            "timeZone": "America/New_York",
                        },
                    }
                ],
            }

        monkeypatch.setattr(calendar_tools, "_fetch_events", fake_fetch_events)

        reg = build_registry(
            plugins={
                "facts": _facts_plugin(
                    tool(
                        name="state_get",
                        func=state_get,
                        input=_StateGetInput,
                        output=_StateGetOutput,
                    ),
                    tool(
                        name="state_put",
                        func=state_put,
                        input=_StatePutInput,
                        output=_StatePutOutput,
                    ),
                    tool(
                        name="upsert",
                        func=upsert,
                        input=_FactUpsertInput,
                        output=_FactUpsertOutput,
                    ),
                    tool(
                        name="receipt_put",
                        func=receipt_put,
                        input=_ReceiptPutInput,
                        output=_ReceiptPutOutput,
                    ),
                ),
                "google_calendar": google_calendar_plugin,
            },
            config_source=DictConfigSource(
                {
                    "google_calendar": {
                        "calendar_id": "primary",
                        "access_token": "token",
                    }
                }
            ),
        )

        result = reg.invoke("google_calendar.sync", {})

        assert result == {"events_seen": 1, "facts_written": 1}
        assert facts == [
            {
                "domain": "calendar",
                "type": "calendar.event",
                "source_plugin": "google_calendar",
                "source_account": "primary",
                "external_id": "evt_1",
                "subject": "google_calendar:primary:evt_1",
                "title": "Design review",
                "body": "Review mocks",
                "status": "confirmed",
                "date": "2026-05-24",
                "starts_at": "2026-05-24T13:00:00-04:00",
                "ends_at": "2026-05-24T14:00:00-04:00",
                "payload": {
                    "location": "Meet",
                    "start": {
                        "dateTime": "2026-05-24T13:00:00-04:00",
                        "timeZone": "America/New_York",
                    },
                    "end": {
                        "dateTime": "2026-05-24T14:00:00-04:00",
                        "timeZone": "America/New_York",
                    },
                    "raw": {
                        "description": "Review mocks",
                        "end": {
                            "dateTime": "2026-05-24T14:00:00-04:00",
                            "timeZone": "America/New_York",
                        },
                        "id": "evt_1",
                        "location": "Meet",
                        "start": {
                            "dateTime": "2026-05-24T13:00:00-04:00",
                            "timeZone": "America/New_York",
                        },
                        "status": "confirmed",
                        "summary": "Design review",
                    },
                },
            }
        ]
        assert state["next_sync_token"] == {"token": "next-token"}
        assert receipts[0]["kind"] == "google_calendar.sync"
        assert receipts[0]["status"] == "completed"
        assert receipts[0]["payload"]["facts_written"] == 1

