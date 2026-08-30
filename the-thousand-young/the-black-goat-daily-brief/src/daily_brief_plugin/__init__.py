from __future__ import annotations

from datetime import date as Date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from the_black_goat import (
    RoutineDefinition,
    Schedule,
    ToolDef,
    current_registry,
    hookimpl,
    tool,
)


DEFAULT_TIMEZONE = "America/New_York"


class DailyBriefGenerateInput(BaseModel):
    date: Date | None = None
    timezone: str = DEFAULT_TIMEZONE
    deliver: bool = True


class DailyBriefGenerateOutput(BaseModel):
    artifact_id: str
    delivered: bool
    receipt_id: str | None = None


def generate(input: DailyBriefGenerateInput) -> DailyBriefGenerateOutput:
    registry = current_registry()
    brief_date = input.date or datetime.now(ZoneInfo(input.timezone)).date()
    start = datetime.combine(
        brief_date,
        time.min,
        tzinfo=ZoneInfo(input.timezone),
    )
    end = start + timedelta(days=1)

    calendar_facts = registry.invoke(
        "facts.query",
        {
            "domain": "calendar",
            "date": brief_date.isoformat(),
            "starts_from": start.isoformat(),
            "starts_until": end.isoformat(),
            "limit": 100,
        },
    ).get("facts", [])
    # Homework due today that is not yet done (status projected each sync by the
    # source). Homework facts carry `date` = due date and a `person` handle.
    homework_facts = registry.invoke(
        "facts.query",
        {
            "domain": "homework",
            "date": brief_date.isoformat(),
            "status": "todo",
            "limit": 200,
        },
    ).get("facts", [])
    signals = registry.invoke(
        "facts.signals_query",
        {"status": "active", "limit": 100},
    ).get("signals", [])

    people_names = _people_names(registry)
    facts = calendar_facts + homework_facts
    body = _render_brief(
        brief_date, calendar_facts, homework_facts, signals, people_names
    )
    artifact = registry.invoke(
        "facts.artifact_put",
        {
            "type": "daily_brief",
            "title": f"Daily brief for {brief_date.isoformat()}",
            "body": body,
            "date": brief_date.isoformat(),
            "generated_by": "daily_brief.generate",
            "fact_ids": [f["id"] for f in facts if f.get("id")],
            "signal_ids": [s["id"] for s in signals if s.get("id")],
            "payload": {
                "timezone": input.timezone,
                "calendar_count": len(calendar_facts),
                "homework_count": len(homework_facts),
                "signals_count": len(signals),
            },
        },
    )
    receipt_id = None
    if input.deliver:
        delivery = registry.invoke(
            "slack.send_artifact",
            {"artifact_id": artifact["id"]},
        )
        receipt_id = delivery.get("receipt_id")

    return DailyBriefGenerateOutput(
        artifact_id=str(artifact["id"]),
        delivered=input.deliver,
        receipt_id=receipt_id,
    )


def _people_names(registry) -> dict[str, str]:
    """handle -> display name, best-effort (empty if the people table is unset)."""
    try:
        result = registry.invoke("facts.people_query", {"limit": 1000})
    except Exception:
        return {}
    names: dict[str, str] = {}
    for person in result.get("people", []):
        handle = person.get("handle")
        if handle:
            names[handle] = person.get("display_name") or handle
    return names


def _render_brief(
    brief_date: Date,
    calendar_facts: list[dict],
    homework_facts: list[dict],
    signals: list[dict],
    people_names: dict[str, str],
) -> str:
    lines = [f"Daily brief for {brief_date.isoformat()}"]
    if signals:
        lines.append("")
        lines.append("Signals")
        for signal in signals:
            summary = signal.get("summary")
            suffix = f": {summary}" if summary else ""
            lines.append(f"- {signal.get('title', 'Untitled signal')}{suffix}")
    if calendar_facts:
        lines.append("")
        lines.append("Calendar")
        for fact in calendar_facts:
            starts_at = fact.get("starts_at")
            time_label = f"{starts_at} - " if starts_at else ""
            lines.append(f"- {time_label}{fact.get('title', 'Untitled event')}")
    if homework_facts:
        lines.append("")
        lines.append("Homework due today")
        # Group by person so the brief reads "Adam" / "Maya", not a flat list.
        by_person: dict[str, list[dict]] = {}
        for fact in homework_facts:
            handle = fact.get("person") or ""
            by_person.setdefault(handle, []).append(fact)

        def _label(handle: str) -> str:
            if not handle:
                return "Unassigned"
            return people_names.get(handle, handle)

        for handle in sorted(by_person, key=lambda h: _label(h).lower()):
            lines.append(f"  {_label(handle)}")
            for fact in by_person[handle]:
                klass = (fact.get("payload") or {}).get("class")
                suffix = f" ({klass})" if klass else ""
                lines.append(f"  - {fact.get('title', 'Untitled assignment')}{suffix}")
    if not calendar_facts and not homework_facts and not signals:
        lines.append("")
        lines.append("No events, homework, or active signals found.")
    return "\n".join(lines)


_GENERATE = tool(
    name="generate",
    func=generate,
    input=DailyBriefGenerateInput,
    output=DailyBriefGenerateOutput,
    is_idempotent=False,
    side_effect="writes_external",
    tags=("daily_brief", "routine"),
)

_ROUTINE = RoutineDefinition(
    name="daily_brief",
    title="Daily brief",
    desc="Generate and deliver the daily brief.",
    schedule="30 7 * * *",
    timezone=DEFAULT_TIMEZONE,
    fact_query={"date": "today"},
    signal_query={"status": "active"},
    output_artifact_type="daily_brief",
    delivery_tool="slack.send_artifact",
)

_SCHEDULE = Schedule(
    name="daily_brief_730",
    tool="daily_brief.generate",
    cron="30 7 * * *",
    input={"deliver": True},
)

@hookimpl
def goat_register_tools() -> list[ToolDef]:
    return [_GENERATE]


@hookimpl
def goat_register_routines() -> list[RoutineDefinition]:
    return [_ROUTINE]


@hookimpl
def goat_register_schedules() -> list[Schedule]:
    return [_SCHEDULE]
