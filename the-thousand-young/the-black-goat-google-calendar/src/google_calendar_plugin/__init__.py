from __future__ import annotations

from the_black_goat import (
    Schedule,
    SourceDefinition,
    ToolDef,
    hookimpl,
    tool,
)

from google_calendar_plugin import tools as _tools


_SOURCE = SourceDefinition(
    name="primary",
    domain="calendar",
    desc="Primary Google Calendar source.",
    config_schema=_tools.GoogleCalendarConfig,
    tags=("calendar", "google"),
)

_SYNC = tool(
    name="sync",
    func=_tools.sync,
    input=_tools.GoogleCalendarSyncInput,
    output=_tools.GoogleCalendarSyncOutput,
    config=_tools.GoogleCalendarConfig,
    is_idempotent=True,
    side_effect="reads_external",
    tags=("calendar", "ingestor"),
)

_SYNC_SCHEDULE = Schedule(
    name="sync_every_3_hours",
    tool="google_calendar.sync",
    cron="0 */3 * * *",
)

@hookimpl
def goat_register_sources() -> list[SourceDefinition]:
    return [_SOURCE]


@hookimpl
def goat_register_tools() -> list[ToolDef]:
    return [_SYNC]


@hookimpl
def goat_register_schedules() -> list[Schedule]:
    return [_SYNC_SCHEDULE]
