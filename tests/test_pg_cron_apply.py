from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from the_black_goat import (
    Schedule,
    ToolDef,
    build_registry,
    hookimpl,
    tool,
)
from the_black_goat.scheduling import apply_schedules


class _Input(BaseModel):
    location: str = "PDX"


class _Output(BaseModel):
    ok: bool = True


def _impl(input: _Input) -> _Output:
    return _Output()


def _atom(name: str = "weather_daily") -> ToolDef:
    return tool(name=name, func=_impl, input=_Input, output=_Output)


def _plugin(*, tools: list[ToolDef] = (), schedules: list[Schedule] = ()):
    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return list(tools)

        @hookimpl
        def goat_register_schedules(self) -> list[Schedule]:
            return list(schedules)

    return _P()


def _existing_goat_jobs(pg_url: str) -> dict[str, dict]:
    """Return a {jobname: {schedule, command}} map for goat:* cron entries."""
    from psycopg import Connection
    from psycopg.rows import dict_row

    with Connection.connect(pg_url) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT jobname, schedule, command FROM cron.job "
                "WHERE jobname LIKE 'goat:%'"
            )
            return {row["jobname"]: row for row in cur.fetchall()}


class TestApplySchedulesCreatesEntries:
    def test_single_schedule_creates_cron_job_row(
        self, pg_url, clean_cron_jobs
    ):
        atom = _atom("weather_daily")
        sched = Schedule(
            name="morning",
            tool="routine.weather_daily",
            cron="0 5 * * *",
            input={"location": "PDX"},
        )
        reg = build_registry(
            plugins={"routine": _plugin(tools=[atom], schedules=[sched])}
        )

        summary = apply_schedules(reg, pg_url)

        existing = _existing_goat_jobs(pg_url)
        assert "goat:routine.morning" in existing
        assert summary["added"] == ["goat:routine.morning"]
        assert summary["kept"] == []
        assert summary["removed"] == []

    def test_cron_schedule_field_matches_registry(
        self, pg_url, clean_cron_jobs
    ):
        atom = _atom("weather_daily")
        sched = Schedule(
            name="morning",
            tool="routine.weather_daily",
            cron="15 7 * * 1-5",
        )
        reg = build_registry(
            plugins={"routine": _plugin(tools=[atom], schedules=[sched])}
        )

        apply_schedules(reg, pg_url)

        existing = _existing_goat_jobs(pg_url)
        assert existing["goat:routine.morning"]["schedule"] == "15 7 * * 1-5"

    def test_command_calls_absurd_spawn_task_with_input(
        self, pg_url, clean_cron_jobs
    ):
        atom = _atom("weather_daily")
        sched = Schedule(
            name="morning",
            tool="routine.weather_daily",
            cron="0 5 * * *",
            input={"location": "PDX"},
        )
        reg = build_registry(
            plugins={"routine": _plugin(tools=[atom], schedules=[sched])}
        )

        apply_schedules(reg, pg_url)

        existing = _existing_goat_jobs(pg_url)
        cmd = existing["goat:routine.morning"]["command"]
        assert "absurd.spawn_task" in cmd
        assert "goat_run_tool" in cmd
        # The payload must reference the tool name and the input.
        assert "routine.weather_daily" in cmd
        assert '"location"' in cmd
        assert '"PDX"' in cmd

    def test_multiple_schedules_create_multiple_rows(
        self, pg_url, clean_cron_jobs
    ):
        atom = _atom("weather_daily")
        s_morning = Schedule(
            name="morning",
            tool="routine.weather_daily",
            cron="0 5 * * *",
        )
        s_evening = Schedule(
            name="evening",
            tool="routine.weather_daily",
            cron="0 18 * * *",
        )
        reg = build_registry(
            plugins={
                "routine": _plugin(
                    tools=[atom], schedules=[s_morning, s_evening]
                )
            }
        )

        apply_schedules(reg, pg_url)

        existing = _existing_goat_jobs(pg_url)
        assert {"goat:routine.morning", "goat:routine.evening"} <= set(
            existing.keys()
        )


class TestApplySchedulesIdempotent:
    def test_re_apply_with_same_registry_keeps_rows(
        self, pg_url, clean_cron_jobs
    ):
        atom = _atom("weather_daily")
        sched = Schedule(
            name="morning",
            tool="routine.weather_daily",
            cron="0 5 * * *",
        )
        reg = build_registry(
            plugins={"routine": _plugin(tools=[atom], schedules=[sched])}
        )

        apply_schedules(reg, pg_url)
        before = _existing_goat_jobs(pg_url)
        summary = apply_schedules(reg, pg_url)
        after = _existing_goat_jobs(pg_url)

        assert set(before.keys()) == set(after.keys())
        assert summary["added"] == []
        assert summary["kept"] == ["goat:routine.morning"]
        assert summary["removed"] == []

    def test_re_apply_after_cron_change_updates_in_place(
        self, pg_url, clean_cron_jobs
    ):
        atom = _atom("weather_daily")
        s1 = Schedule(name="x", tool="routine.weather_daily", cron="0 5 * * *")
        s2 = Schedule(name="x", tool="routine.weather_daily", cron="0 6 * * *")

        reg1 = build_registry(
            plugins={"routine": _plugin(tools=[atom], schedules=[s1])}
        )
        apply_schedules(reg1, pg_url)
        existing_first = _existing_goat_jobs(pg_url)
        assert existing_first["goat:routine.x"]["schedule"] == "0 5 * * *"

        reg2 = build_registry(
            plugins={"routine": _plugin(tools=[atom], schedules=[s2])}
        )
        apply_schedules(reg2, pg_url)
        existing_second = _existing_goat_jobs(pg_url)
        # Same job name, updated cron.
        assert set(existing_second) == {"goat:routine.x"}
        assert existing_second["goat:routine.x"]["schedule"] == "0 6 * * *"


class TestApplySchedulesRemovesOrphans:
    def test_schedule_no_longer_in_registry_is_unscheduled(
        self, pg_url, clean_cron_jobs
    ):
        atom = _atom("weather_daily")
        s_a = Schedule(name="a", tool="routine.weather_daily", cron="0 5 * * *")
        s_b = Schedule(name="b", tool="routine.weather_daily", cron="0 6 * * *")

        reg_with_both = build_registry(
            plugins={"routine": _plugin(tools=[atom], schedules=[s_a, s_b])}
        )
        apply_schedules(reg_with_both, pg_url)
        assert {"goat:routine.a", "goat:routine.b"} <= set(
            _existing_goat_jobs(pg_url)
        )

        reg_with_a_only = build_registry(
            plugins={"routine": _plugin(tools=[atom], schedules=[s_a])}
        )
        summary = apply_schedules(reg_with_a_only, pg_url)

        existing = _existing_goat_jobs(pg_url)
        assert "goat:routine.a" in existing
        assert "goat:routine.b" not in existing
        assert summary["removed"] == ["goat:routine.b"]

    def test_empty_registry_clears_all_goat_entries(
        self, pg_url, clean_cron_jobs
    ):
        atom = _atom("weather_daily")
        sched = Schedule(name="x", tool="routine.weather_daily", cron="0 5 * * *")
        reg = build_registry(
            plugins={"routine": _plugin(tools=[atom], schedules=[sched])}
        )
        apply_schedules(reg, pg_url)
        assert _existing_goat_jobs(pg_url)  # non-empty

        # Build a registry with no schedules.
        reg_empty = build_registry(
            plugins={"routine": _plugin(tools=[atom])}
        )
        apply_schedules(reg_empty, pg_url)
        assert _existing_goat_jobs(pg_url) == {}


class TestApplySchedulesDryRun:
    def test_dry_run_makes_no_changes(self, pg_url, clean_cron_jobs):
        atom = _atom("weather_daily")
        sched = Schedule(
            name="morning", tool="routine.weather_daily", cron="0 5 * * *"
        )
        reg = build_registry(
            plugins={"routine": _plugin(tools=[atom], schedules=[sched])}
        )

        before = _existing_goat_jobs(pg_url)
        summary = apply_schedules(reg, pg_url, dry_run=True)
        after = _existing_goat_jobs(pg_url)

        assert before == after  # no DB changes
        assert summary["added"] == ["goat:routine.morning"]
