from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib import parse, request

from pydantic import BaseModel, Field, SecretStr

from the_black_goat import current_registry


class GoogleCalendarConfig(BaseModel):
    calendar_id: str = "primary"
    access_token: SecretStr
    sync_lookback_days: int = Field(default=30, ge=1)


class GoogleCalendarSyncInput(BaseModel):
    calendar_id: str | None = None
    force_full_sync: bool = False


class GoogleCalendarSyncOutput(BaseModel):
    events_seen: int
    facts_written: int


def sync(
    input: GoogleCalendarSyncInput, *, config: GoogleCalendarConfig
) -> GoogleCalendarSyncOutput:
    registry = current_registry()
    account = input.calendar_id or config.calendar_id
    sync_state = registry.invoke(
        "facts.state_get",
        {
            "plugin": "google_calendar",
            "account": account,
            "key": "next_sync_token",
        },
    )
    sync_token = None
    if not input.force_full_sync and sync_state.get("value") is not None:
        sync_token = sync_state["value"].get("token")

    time_min = None
    if sync_token is None:
        time_min = (
            datetime.now(UTC) - timedelta(days=config.sync_lookback_days)
        ).isoformat()

    response = _fetch_events(
        access_token=config.access_token.get_secret_value(),
        calendar_id=account,
        sync_token=sync_token,
        time_min=time_min,
    )
    items = response.get("items", [])
    facts_written = 0
    for event in items:
        if _upsert_event(registry, account, event):
            facts_written += 1

    next_token = response.get("nextSyncToken")
    if next_token:
        registry.invoke(
            "facts.state_put",
            {
                "plugin": "google_calendar",
                "account": account,
                "key": "next_sync_token",
                "value": {"token": next_token},
            },
        )

    registry.invoke(
        "facts.receipt_put",
        {
            "kind": "google_calendar.sync",
            "plugin": "google_calendar",
            "target": account,
            "external_id": next_token,
            "status": "completed",
            "payload": {
                "events_seen": len(items),
                "facts_written": facts_written,
            },
        },
    )
    return GoogleCalendarSyncOutput(
        events_seen=len(items),
        facts_written=facts_written,
    )


def _upsert_event(registry, account: str, event: dict[str, Any]) -> bool:
    event_id = event["id"]
    start = event.get("start", {})
    end = event.get("end", {})
    starts_at = start.get("dateTime")
    ends_at = end.get("dateTime")
    event_date = _event_date(start)
    registry.invoke(
        "facts.upsert",
        {
            "domain": "calendar",
            "type": "calendar.event",
            "source_plugin": "google_calendar",
            "source_account": account,
            "external_id": event_id,
            "subject": f"google_calendar:{account}:{event_id}",
            "title": event.get("summary"),
            "body": event.get("description"),
            "status": event.get("status"),
            "date": event_date,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "payload": {
                "location": event.get("location"),
                "start": start,
                "end": end,
                "raw": event,
            },
        },
    )
    return True


def _event_date(start: dict[str, Any]) -> str | None:
    if "date" in start:
        return start["date"]
    date_time = start.get("dateTime")
    if date_time is None:
        return None
    return date_time[:10]


def _fetch_events(
    *,
    access_token: str,
    calendar_id: str,
    sync_token: str | None,
    time_min: str | None,
) -> dict[str, Any]:
    params: dict[str, str] = {
        "singleEvents": "true",
        "showDeleted": "true",
    }
    if sync_token is not None:
        params["syncToken"] = sync_token
    elif time_min is not None:
        params["timeMin"] = time_min
    url = (
        "https://www.googleapis.com/calendar/v3/calendars/"
        + parse.quote(calendar_id, safe="")
        + "/events?"
        + parse.urlencode(params)
    )
    req = request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode()
    return json.loads(body)

