from __future__ import annotations

import pluggy
import pytest
from pydantic import BaseModel, ValidationError

from the_black_goat import (
    RoutineDefinition,
    SignalDefinition,
    SourceDefinition,
    build_registry,
    hookimpl,
)
from the_black_goat._hookspec import GoatHooks


class _CalendarConfig(BaseModel):
    calendar_id: str


def _make_pm() -> pluggy.PluginManager:
    pm = pluggy.PluginManager("the_black_goat")
    pm.add_hookspecs(GoatHooks)
    return pm


def _plugin(
    *,
    sources: list[SourceDefinition] = (),
    signals: list[SignalDefinition] = (),
    routines: list[RoutineDefinition] = (),
):
    class _P:
        @hookimpl
        def goat_register_sources(self) -> list[SourceDefinition]:
            return list(sources)

        @hookimpl
        def goat_register_signal_definitions(self) -> list[SignalDefinition]:
            return list(signals)

        @hookimpl
        def goat_register_routines(self) -> list[RoutineDefinition]:
            return list(routines)

    return _P()


class TestSourceDefinition:
    def test_constructs_with_required_fields(self):
        source = SourceDefinition(
            name="primary",
            domain="calendar",
            desc="Primary Google Calendar",
            config_schema=_CalendarConfig,
            tags=("calendar",),
        )

        assert source.name == "primary"
        assert source.domain == "calendar"
        assert source.plugin == ""
        assert source.config_schema is _CalendarConfig
        assert source.qualified_name == "primary"

    def test_prefixed_qualified_name(self):
        source = SourceDefinition(
            name="primary",
            domain="calendar",
        ).model_copy(update={"plugin": "google_calendar"})

        assert source.qualified_name == "google_calendar.primary"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            SourceDefinition(name="", domain="calendar")


class TestSignalDefinition:
    def test_constructs_with_llm_strategy(self):
        signal = SignalDefinition(
            name="prep_needed",
            domain="calendar",
            kind="prep_needed",
            title="Prep needed",
            strategy="llm",
            input_query={"domain": "calendar"},
            min_confidence=0.8,
        )

        assert signal.qualified_name == "prep_needed"
        assert signal.strategy == "llm"
        assert signal.input_query == {"domain": "calendar"}
        assert signal.min_confidence == 0.8

    def test_invalid_strategy_rejected(self):
        with pytest.raises(ValidationError):
            SignalDefinition(
                name="x",
                domain="calendar",
                kind="x",
                title="X",
                strategy="magic",
            )

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            SignalDefinition(
                name="x",
                domain="calendar",
                kind="x",
                title="X",
                min_confidence=1.1,
            )


class TestRoutineDefinition:
    def test_constructs_with_schedule_timezone_and_delivery(self):
        routine = RoutineDefinition(
            name="daily_brief",
            title="Daily brief",
            schedule="30 7 * * *",
            timezone="America/New_York",
            fact_query={"date": "today"},
            signal_query={"status": "active"},
            output_artifact_type="daily_brief",
            delivery_tool="slack.send_artifact",
        )

        assert routine.qualified_name == "daily_brief"
        assert routine.timezone == "America/New_York"
        assert routine.delivery_tool == "slack.send_artifact"

    def test_empty_artifact_type_rejected(self):
        with pytest.raises(ValidationError):
            RoutineDefinition(
                name="daily_brief",
                title="Daily brief",
                output_artifact_type="",
            )


class TestHooks:
    def test_hookspec_declares_new_registration_hooks(self):
        assert hasattr(GoatHooks, "goat_register_sources")
        assert hasattr(GoatHooks, "goat_register_signal_definitions")
        assert hasattr(GoatHooks, "goat_register_routines")

    def test_pluggy_aggregates_new_definition_hooks(self):
        source = SourceDefinition(name="primary", domain="calendar")
        signal = SignalDefinition(
            name="prep_needed",
            domain="calendar",
            kind="prep_needed",
            title="Prep needed",
        )
        routine = RoutineDefinition(
            name="daily_brief",
            title="Daily brief",
            output_artifact_type="daily_brief",
        )

        pm = _make_pm()
        pm.register(
            _plugin(sources=[source], signals=[signal], routines=[routine])
        )

        assert pm.hook.goat_register_sources() == [[source]]
        assert pm.hook.goat_register_signal_definitions() == [[signal]]
        assert pm.hook.goat_register_routines() == [[routine]]


class TestRegistryAggregation:
    def test_registry_collects_prefixed_definitions(self):
        source = SourceDefinition(name="primary", domain="calendar")
        signal = SignalDefinition(
            name="prep_needed",
            domain="calendar",
            kind="prep_needed",
            title="Prep needed",
        )
        routine = RoutineDefinition(
            name="daily_brief",
            title="Daily brief",
            output_artifact_type="daily_brief",
        )

        reg = build_registry(
            plugins={
                "google_calendar": _plugin(
                    sources=[source],
                    signals=[signal],
                    routines=[routine],
                )
            }
        )

        assert reg.sources()[0].qualified_name == "google_calendar.primary"
        assert (
            reg.signal_definitions()[0].qualified_name
            == "google_calendar.prep_needed"
        )
        assert (
            reg.routines()[0].qualified_name
            == "google_calendar.daily_brief"
        )

    def test_registry_lookup_by_qualified_name(self):
        source = SourceDefinition(name="primary", domain="calendar")
        signal = SignalDefinition(
            name="prep_needed",
            domain="calendar",
            kind="prep_needed",
            title="Prep needed",
        )
        routine = RoutineDefinition(
            name="daily_brief",
            title="Daily brief",
            output_artifact_type="daily_brief",
        )

        reg = build_registry(
            plugins={
                "ops": _plugin(
                    sources=[source],
                    signals=[signal],
                    routines=[routine],
                )
            }
        )

        assert reg.source("ops.primary") == source.model_copy(
            update={"plugin": "ops"}
        )
        assert reg.signal_definition("ops.prep_needed") == signal.model_copy(
            update={"plugin": "ops"}
        )
        assert reg.routine("ops.daily_brief") == routine.model_copy(
            update={"plugin": "ops"}
        )

    def test_duplicate_definition_qnames_raise_at_build(self):
        signal_a = SignalDefinition(
            name="prep_needed",
            domain="calendar",
            kind="prep_needed",
            title="Prep needed",
        )
        signal_b = SignalDefinition(
            name="prep_needed",
            domain="todo",
            kind="prep_needed",
            title="Prep needed",
        )

        with pytest.raises(ValueError, match=r"duplicate signal definition"):
            build_registry(
                plugins={"ops": _plugin(signals=[signal_a, signal_b])}
            )

