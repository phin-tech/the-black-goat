from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from the_black_goat import (
    Schedule,
    ToolDef,
    build_registry,
    hookimpl,
    tool,
)
from the_black_goat.errors import ToolNotFound


class _Input(BaseModel):
    location: str = "PDX"


class _Output(BaseModel):
    ok: bool = True


def _impl(input: _Input) -> _Output:
    """Sample tool body."""
    return _Output()


def _atom(name: str = "weather_daily") -> ToolDef:
    return tool(name=name, func=_impl, input=_Input, output=_Output)


def _plugin(*, tools: list[ToolDef] = (), schedules: list[Schedule] = ()):
    """Build a plugin object that exposes both hooks."""

    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return list(tools)

        @hookimpl
        def goat_register_schedules(self) -> list[Schedule]:
            return list(schedules)

    return _P()


# ---------- Schedule model ----------


class TestScheduleModel:
    def test_constructs_with_required_fields(self):
        s = Schedule(name="daily", tool="routine.weather", cron="0 5 * * *")
        assert s.name == "daily"
        assert s.tool == "routine.weather"
        assert s.cron == "0 5 * * *"
        assert s.input == {}
        assert s.plugin == ""

    def test_input_defaults_to_empty_dict(self):
        s = Schedule(name="x", tool="t.x", cron="* * * * *")
        assert s.input == {}

    def test_qualified_name_falls_back_to_short_name_without_plugin(self):
        s = Schedule(name="x", tool="t.x", cron="* * * * *")
        assert s.qualified_name == "x"

    def test_qualified_name_combines_plugin_and_name(self):
        s = Schedule(
            name="daily",
            tool="routine.weather",
            cron="0 5 * * *",
        ).model_copy(update={"plugin": "routine"})
        assert s.qualified_name == "routine.daily"

    def test_frozen(self):
        s = Schedule(name="x", tool="t.x", cron="* * * * *")
        with pytest.raises(ValidationError):
            s.cron = "bad"  # type: ignore[misc]

    def test_invalid_cron_rejected(self):
        with pytest.raises(ValidationError):
            Schedule(name="x", tool="t.x", cron="not a cron")

    def test_pg_cron_interval_syntax_accepted(self):
        # pg_cron 1.4+ accepts "N seconds/minutes/hours/days"; the registry's
        # validator must let these through alongside standard cron.
        for expr in ("5 seconds", "10 minutes", "1 hour", "2 days"):
            s = Schedule(name="x", tool="t.x", cron=expr)
            assert s.cron == expr

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            Schedule(name="", tool="t.x", cron="* * * * *")

    def test_empty_tool_rejected(self):
        with pytest.raises(ValidationError):
            Schedule(name="x", tool="", cron="* * * * *")


# ---------- Registry aggregation ----------


def _registry_with(plugin_map: dict):
    return build_registry(plugins=plugin_map)


class TestRegistryAggregation:
    def test_no_schedules_yields_empty_list(self):
        reg = _registry_with({"demo": _plugin(tools=[_atom("x")])})
        assert reg.schedules() == []

    def test_single_plugin_schedule(self):
        atom = _atom("weather_daily")
        sched = Schedule(
            name="morning",
            tool="routine.weather_daily",
            cron="0 5 * * *",
            input={"location": "PDX"},
        )
        reg = _registry_with(
            {"routine": _plugin(tools=[atom], schedules=[sched])}
        )

        scheds = reg.schedules()
        assert len(scheds) == 1
        assert scheds[0].plugin == "routine"
        assert scheds[0].qualified_name == "routine.morning"

    def test_two_plugins_aggregate(self):
        atom_a = _atom("weather_daily")
        atom_b = _atom("summary")

        reg = _registry_with(
            {
                "routine": _plugin(
                    tools=[atom_a],
                    schedules=[
                        Schedule(
                            name="morning",
                            tool="routine.weather_daily",
                            cron="0 5 * * *",
                        )
                    ],
                ),
                "digest": _plugin(
                    tools=[atom_b],
                    schedules=[
                        Schedule(
                            name="afternoon",
                            tool="digest.summary",
                            cron="0 17 * * *",
                        )
                    ],
                ),
            }
        )
        names = sorted(s.qualified_name for s in reg.schedules())
        assert names == ["digest.afternoon", "routine.morning"]


class TestRegistryLookup:
    def test_schedule_get_by_qname(self):
        atom = _atom("weather_daily")
        sched = Schedule(
            name="morning",
            tool="routine.weather_daily",
            cron="0 5 * * *",
        )
        reg = _registry_with(
            {"routine": _plugin(tools=[atom], schedules=[sched])}
        )
        got = reg.schedule("routine.morning")
        assert got.tool == "routine.weather_daily"

    def test_schedule_unknown_qname_raises(self):
        reg = _registry_with({"demo": _plugin(tools=[_atom("x")])})
        with pytest.raises(KeyError):
            reg.schedule("demo.nope")

    def test_schedules_by_plugin(self):
        atom = _atom("weather_daily")
        reg = _registry_with(
            {
                "routine": _plugin(
                    tools=[atom],
                    schedules=[
                        Schedule(
                            name="m",
                            tool="routine.weather_daily",
                            cron="0 5 * * *",
                        ),
                        Schedule(
                            name="e",
                            tool="routine.weather_daily",
                            cron="0 18 * * *",
                        ),
                    ],
                )
            }
        )
        scheds = reg.schedules_by_plugin("routine")
        assert sorted(s.name for s in scheds) == ["e", "m"]


class TestRegistryValidation:
    def test_schedule_referencing_unknown_tool_raises_at_build(self):
        sched = Schedule(
            name="morning",
            tool="routine.does_not_exist",
            cron="0 5 * * *",
        )
        with pytest.raises(ToolNotFound, match=r"routine.does_not_exist"):
            _registry_with({"routine": _plugin(schedules=[sched])})

    def test_duplicate_schedule_qname_raises_at_build(self):
        atom = _atom("x")
        s1 = Schedule(name="dup", tool="routine.x", cron="0 5 * * *")
        s2 = Schedule(name="dup", tool="routine.x", cron="0 6 * * *")
        with pytest.raises(ValueError, match=r"duplicate"):
            _registry_with(
                {"routine": _plugin(tools=[atom], schedules=[s1, s2])}
            )
