from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
)


class SourceDefinition(BaseModel):
    """External source shape contributed by a plugin.

    Sources are configuration/state targets such as a Google Calendar account,
    not executable tools. Ingestor tools do the actual observation.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    plugin: str = ""
    name: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    desc: str = ""
    config_schema: type[BaseModel] | None = None
    tags: tuple[str, ...] = ()

    @computed_field
    @property
    def qualified_name(self) -> str:
        return f"{self.plugin}.{self.name}" if self.plugin else self.name


class SignalDefinition(BaseModel):
    """Plugin-declared recipe for producing user-facing signals."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    plugin: str = ""
    name: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    title: str = Field(min_length=1)
    desc: str = ""
    strategy: Literal["deterministic", "llm", "hybrid"] = "deterministic"
    input_query: dict = Field(default_factory=dict)
    generator_tool: str | None = None
    output_schema: type[BaseModel] | None = None
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    default_severity: Literal["info", "important", "urgent"] = "info"
    tags: tuple[str, ...] = ()

    @computed_field
    @property
    def qualified_name(self) -> str:
        return f"{self.plugin}.{self.name}" if self.plugin else self.name


class SignalProposal(BaseModel):
    """Validated signal candidate produced by a generator tool."""

    dedupe_key: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    severity: Literal["info", "important", "urgent"] = "info"
    status: Literal["active", "dismissed", "snoozed", "done", "expired"] = (
        "active"
    )
    relevant_at: datetime | None = None
    expires_at: datetime | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    generated_by: str = Field(min_length=1)
    payload: dict = Field(default_factory=dict)
    fact_ids: list[str] = Field(default_factory=list)


class RoutineDefinition(BaseModel):
    """Workflow definition that composes facts/signals into artifacts."""

    model_config = ConfigDict(frozen=True)

    plugin: str = ""
    name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    desc: str = ""
    schedule: str | None = None
    timezone: str = "UTC"
    fact_query: dict = Field(default_factory=dict)
    signal_query: dict = Field(default_factory=dict)
    output_artifact_type: str = Field(min_length=1)
    delivery_tool: str | None = None
    requires_confirmation: bool = False
    tags: tuple[str, ...] = ()

    @computed_field
    @property
    def qualified_name(self) -> str:
        return f"{self.plugin}.{self.name}" if self.plugin else self.name
