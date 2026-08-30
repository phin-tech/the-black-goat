from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from the_black_goat import build_registry
from the_black_goat.config import DictConfigSource


class TestFactsPluginRegistration:
    def test_registers_expected_tools(self):
        import facts_plugin

        reg = build_registry(
            plugins={"facts": facts_plugin},
            config_source=DictConfigSource(
                {"facts": {"database_url": "postgresql://unused"}}
            ),
        )

        names = sorted(t.qualified_name for t in reg.by_plugin("facts"))
        assert names == [
            "facts.artifact_get",
            "facts.artifact_put",
            "facts.artifacts_query",
            "facts.define",
            "facts.definitions_query",
            "facts.get",
            "facts.people_put",
            "facts.people_query",
            "facts.query",
            "facts.receipt_put",
            "facts.receipts_query",
            "facts.signal_dismiss",
            "facts.signal_put",
            "facts.signals_query",
            "facts.state_get",
            "facts.state_put",
            "facts.upsert",
        ]


@pytest.fixture
def facts_registry(pg_url):
    import facts_plugin
    from psycopg import Connection

    with Connection.connect(pg_url, autocommit=True) as conn:
        conn.cursor().execute(open("db/memory.sql").read())

    config_source = DictConfigSource({"facts": {"database_url": pg_url}})
    return build_registry(
        plugins={"facts": facts_plugin},
        config_source=config_source,
    )


def _event_payload(external_id: str, *, starts_at: datetime | None = None):
    starts = starts_at or datetime(2026, 5, 24, 13, 0, tzinfo=UTC)
    return {
        "domain": "calendar",
        "type": "calendar.event",
        "source_plugin": "google_calendar",
        "source_account": "primary",
        "external_id": external_id,
        "subject": f"google_calendar:primary:{external_id}",
        "title": "Design review",
        "status": "confirmed",
        "date": starts.date().isoformat(),
        "starts_at": starts.isoformat(),
        "ends_at": (starts + timedelta(hours=1)).isoformat(),
        "payload": {"hangout_link": "https://meet.example/review"},
    }


class TestFactsUpsertGetQuery:
    def test_upsert_get_roundtrip(self, facts_registry):
        upserted = facts_registry.facts.upsert(_event_payload("evt_roundtrip"))

        got = facts_registry.facts.get({"id": upserted["id"]})

        assert got["fact"]["id"] == upserted["id"]
        assert got["fact"]["domain"] == "calendar"
        assert got["fact"]["type"] == "calendar.event"
        assert got["fact"]["title"] == "Design review"
        assert got["fact"]["payload"] == {
            "hangout_link": "https://meet.example/review"
        }

    def test_upsert_same_source_identity_updates_existing_fact(
        self, facts_registry
    ):
        first = facts_registry.facts.upsert(_event_payload("evt_upsert"))
        changed = _event_payload("evt_upsert")
        changed["title"] = "Updated design review"

        second = facts_registry.facts.upsert(changed)

        assert second["id"] == first["id"]
        got = facts_registry.facts.get({"id": first["id"]})
        assert got["fact"]["title"] == "Updated design review"

    def test_query_filters_by_domain_date_and_start_range(self, facts_registry):
        account = "query_" + uuid.uuid4().hex[:8]
        today = datetime(2026, 5, 24, 13, 0, tzinfo=UTC)
        tomorrow = datetime(2026, 5, 25, 13, 0, tzinfo=UTC)
        today_payload = _event_payload("evt_today", starts_at=today)
        today_payload["source_account"] = account
        today_payload["subject"] = f"google_calendar:{account}:evt_today"
        tomorrow_payload = _event_payload("evt_tomorrow", starts_at=tomorrow)
        tomorrow_payload["source_account"] = account
        tomorrow_payload["subject"] = f"google_calendar:{account}:evt_tomorrow"
        facts_registry.facts.upsert(today_payload)
        facts_registry.facts.upsert(tomorrow_payload)

        result = facts_registry.facts.query(
            {
                "domain": "calendar",
                "source_account": account,
                "date": "2026-05-24",
                "starts_from": "2026-05-24T00:00:00+00:00",
                "starts_until": "2026-05-25T00:00:00+00:00",
            }
        )

        assert [fact["external_id"] for fact in result["facts"]] == [
            "evt_today"
        ]


class TestSourceState:
    def test_state_put_get_roundtrip(self, facts_registry):
        put = facts_registry.facts.state_put(
            {
                "plugin": "google_calendar",
                "account": "primary",
                "key": "next_sync_token",
                "value": {"token": "abc"},
            }
        )
        got = facts_registry.facts.state_get(
            {
                "plugin": "google_calendar",
                "account": "primary",
                "key": "next_sync_token",
            }
        )

        assert "updated_at" in put
        assert got["value"] == {"token": "abc"}


class TestArtifactsReceiptsAndSignals:
    def test_artifact_put_and_receipt_put(self, facts_registry):
        generated_by = "daily_brief.generate." + uuid.uuid4().hex[:8]
        artifact = facts_registry.facts.artifact_put(
            {
                "type": "daily_brief",
                "title": "Daily brief",
                "body": "Today: design review.",
                "date": "2026-05-24",
                "generated_by": generated_by,
            }
        )
        got_artifact = facts_registry.facts.artifact_get(
            {"id": artifact["id"]}
        )

        receipt = facts_registry.facts.receipt_put(
            {
                "kind": "slack.message",
                "plugin": "slack",
                "target": "C123",
                "external_id": "123.456",
                "status": "sent",
                "artifact_id": artifact["id"],
                "payload": {"ts": "123.456"},
            }
        )
        receipts = facts_registry.facts.receipts_query(
            {"artifact_id": artifact["id"]}
        )
        artifacts = facts_registry.facts.artifacts_query(
            {
                "type": "daily_brief",
                "date": "2026-05-24",
                "generated_by": generated_by,
            }
        )

        assert uuid.UUID(artifact["id"])
        assert got_artifact["artifact"]["body"] == "Today: design review."
        assert receipt["artifact_id"] == artifact["id"]
        assert [r["id"] for r in receipts["receipts"]] == [receipt["id"]]
        assert [a["id"] for a in artifacts["artifacts"]] == [artifact["id"]]

    def test_signal_put_query_and_dismiss(self, facts_registry):
        domain = "calendar_" + uuid.uuid4().hex[:8]
        fact = facts_registry.facts.upsert(_event_payload("evt_signal"))
        signal = facts_registry.facts.signal_put(
            {
                "definition_name": "calendar.prep_needed",
                "dedupe_key": "evt_signal:prep",
                "domain": domain,
                "kind": "prep_needed",
                "title": "Prep for design review",
                "summary": "No notes are attached.",
                "severity": "important",
                "confidence": 0.9,
                "generated_by": "signals.generate",
                "fact_ids": [fact["id"]],
            }
        )

        queried = facts_registry.facts.signals_query(
            {"domain": domain, "status": "active"}
        )
        dismissed = facts_registry.facts.signal_dismiss({"id": signal["id"]})

        assert [s["id"] for s in queried["signals"]] == [signal["id"]]
        assert dismissed["status"] == "dismissed"
