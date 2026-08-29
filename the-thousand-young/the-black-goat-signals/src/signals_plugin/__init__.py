from __future__ import annotations

from pydantic import BaseModel, Field

from the_black_goat import (
    SignalProposal,
    ToolDef,
    current_registry,
    hookimpl,
    tool,
)


class SignalGenerateInput(BaseModel):
    definitions: list[str] | None = None
    params: dict = Field(default_factory=dict)
    persist: bool = True


class GeneratedSignal(BaseModel):
    definition_name: str
    signal_id: str


class RejectedSignal(BaseModel):
    definition_name: str
    dedupe_key: str
    reason: str


class SignalGenerateOutput(BaseModel):
    generated: list[GeneratedSignal]
    rejected: list[RejectedSignal]
    skipped: list[RejectedSignal]


class _GeneratorInput(BaseModel):
    definition: dict
    params: dict = Field(default_factory=dict)


class _GeneratorOutput(BaseModel):
    proposals: list[SignalProposal]


def generate(input: SignalGenerateInput) -> SignalGenerateOutput:
    registry = current_registry()
    selected = set(input.definitions or [])
    definitions = [
        d
        for d in registry.signal_definitions()
        if not selected or d.qualified_name in selected
    ]
    generated: list[GeneratedSignal] = []
    rejected: list[RejectedSignal] = []
    skipped: list[RejectedSignal] = []

    for definition in definitions:
        qname = definition.qualified_name
        if definition.generator_tool is None:
            skipped.append(
                RejectedSignal(
                    definition_name=qname,
                    dedupe_key="",
                    reason="missing generator tool",
                )
            )
            continue

        result = registry.invoke(
            definition.generator_tool,
            {
                "definition": definition.model_dump(),
                "params": input.params,
            },
        )
        output = _GeneratorOutput.model_validate(result)

        for proposal in output.proposals:
            if proposal.confidence < definition.min_confidence:
                rejected.append(
                    RejectedSignal(
                        definition_name=qname,
                        dedupe_key=proposal.dedupe_key,
                        reason="confidence below threshold",
                    )
                )
                continue
            if not _supporting_facts_exist(registry, proposal.fact_ids):
                rejected.append(
                    RejectedSignal(
                        definition_name=qname,
                        dedupe_key=proposal.dedupe_key,
                        reason="missing supporting fact",
                    )
                )
                continue
            if not input.persist:
                generated.append(
                    GeneratedSignal(
                        definition_name=qname,
                        signal_id="",
                    )
                )
                continue

            persisted = registry.invoke(
                "facts.signal_put",
                {
                    **proposal.model_dump(),
                    "definition_name": qname,
                },
            )
            generated.append(
                GeneratedSignal(
                    definition_name=qname,
                    signal_id=str(persisted["id"]),
                )
            )

    return SignalGenerateOutput(
        generated=generated,
        rejected=rejected,
        skipped=skipped,
    )


def _supporting_facts_exist(registry, fact_ids: list[str]) -> bool:
    for fact_id in fact_ids:
        result = registry.invoke("facts.get", {"id": fact_id})
        if result.get("fact") is None:
            return False
    return True


_GENERATE = tool(
    name="generate",
    func=generate,
    input=SignalGenerateInput,
    output=SignalGenerateOutput,
    is_idempotent=False,
    side_effect="writes_external",
    tags=("signals",),
)

@hookimpl
def goat_register_tools() -> list[ToolDef]:
    return [_GENERATE]
