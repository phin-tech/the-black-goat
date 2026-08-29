from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import BaseModel

from the_black_goat import (
    SignalDefinition,
    SignalProposal,
    ToolDef,
    build_registry,
    hookimpl,
    tool,
)


class _GeneratorInput(BaseModel):
    definition: dict[str, Any]
    params: dict[str, Any] = {}


class _GeneratorOutput(BaseModel):
    proposals: list[SignalProposal]


class _FactGetInput(BaseModel):
    id: uuid.UUID


class _FactGetOutput(BaseModel):
    fact: dict[str, Any] | None = None


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


def _plugin_with_tools(*tools_: ToolDef):
    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return list(tools_)

    return _P()


def _calendar_plugin(generator_tool: ToolDef, signal: SignalDefinition):
    class _P:
        @hookimpl
        def goat_register_tools(self) -> list[ToolDef]:
            return [generator_tool]

        @hookimpl
        def goat_register_signal_definitions(self) -> list[SignalDefinition]:
            return [signal]

    return _P()


class TestSignalsGenerate:
    @pytest.mark.parametrize("strategy", ["deterministic", "llm", "hybrid"])
    def test_runs_generator_validates_facts_and_persists_signal(
        self, strategy
    ):
        fact_id = uuid.uuid4()
        persisted: list[dict[str, Any]] = []

        def propose(input: _GeneratorInput) -> _GeneratorOutput:
            return _GeneratorOutput(
                proposals=[
                    SignalProposal(
                        dedupe_key="prep:" + str(fact_id),
                        domain="calendar",
                        kind="prep_needed",
                        title="Prep for design review",
                        summary="No notes are attached.",
                        severity="important",
                        confidence=0.9,
                        generated_by="calendar.propose",
                        fact_ids=[str(fact_id)],
                    )
                ]
            )

        def fact_get(input: _FactGetInput) -> _FactGetOutput:
            if input.id == fact_id:
                return _FactGetOutput(fact={"id": str(fact_id)})
            return _FactGetOutput()

        def signal_put(input: _SignalPutInput) -> _SignalPutOutput:
            persisted.append(input.model_dump())
            return _SignalPutOutput(id="signal-1")

        generator = tool(
            name="propose",
            func=propose,
            input=_GeneratorInput,
            output=_GeneratorOutput,
        )
        facts_get = tool(
            name="get",
            func=fact_get,
            input=_FactGetInput,
            output=_FactGetOutput,
        )
        facts_signal_put = tool(
            name="signal_put",
            func=signal_put,
            input=_SignalPutInput,
            output=_SignalPutOutput,
        )
        definition = SignalDefinition(
            name="prep_needed",
            domain="calendar",
            kind="prep_needed",
            title="Prep needed",
            strategy=strategy,
            generator_tool="calendar.propose",
            min_confidence=0.8,
        )

        import signals_plugin

        reg = build_registry(
            plugins={
                "facts": _plugin_with_tools(facts_get, facts_signal_put),
                "calendar": _calendar_plugin(generator, definition),
                "signals": signals_plugin,
            }
        )

        result = reg.invoke("signals.generate", {})

        assert result["generated"] == [
            {"definition_name": "calendar.prep_needed", "signal_id": "signal-1"}
        ]
        assert result["rejected"] == []
        assert persisted[0]["definition_name"] == "calendar.prep_needed"
        assert persisted[0]["fact_ids"] == [str(fact_id)]

    def test_rejects_proposals_with_missing_supporting_facts(self):
        missing_fact_id = uuid.uuid4()
        persisted: list[dict[str, Any]] = []

        def propose(input: _GeneratorInput) -> _GeneratorOutput:
            return _GeneratorOutput(
                proposals=[
                    SignalProposal(
                        dedupe_key="prep:" + str(missing_fact_id),
                        domain="calendar",
                        kind="prep_needed",
                        title="Prep for design review",
                        summary="No notes are attached.",
                        confidence=0.9,
                        generated_by="calendar.propose",
                        fact_ids=[str(missing_fact_id)],
                    )
                ]
            )

        def fact_get(input: _FactGetInput) -> _FactGetOutput:
            return _FactGetOutput()

        def signal_put(input: _SignalPutInput) -> _SignalPutOutput:
            persisted.append(input.model_dump())
            return _SignalPutOutput(id="signal-1")

        import signals_plugin

        reg = build_registry(
            plugins={
                "facts": _plugin_with_tools(
                    tool(
                        name="get",
                        func=fact_get,
                        input=_FactGetInput,
                        output=_FactGetOutput,
                    ),
                    tool(
                        name="signal_put",
                        func=signal_put,
                        input=_SignalPutInput,
                        output=_SignalPutOutput,
                    ),
                ),
                "calendar": _calendar_plugin(
                    tool(
                        name="propose",
                        func=propose,
                        input=_GeneratorInput,
                        output=_GeneratorOutput,
                    ),
                    SignalDefinition(
                        name="prep_needed",
                        domain="calendar",
                        kind="prep_needed",
                        title="Prep needed",
                        generator_tool="calendar.propose",
                    ),
                ),
                "signals": signals_plugin,
            }
        )

        result = reg.invoke("signals.generate", {})

        assert result["generated"] == []
        assert result["rejected"] == [
            {
                "definition_name": "calendar.prep_needed",
                "dedupe_key": "prep:" + str(missing_fact_id),
                "reason": "missing supporting fact",
            }
        ]
        assert persisted == []
