from __future__ import annotations

from typing import Any

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class Schedule(BaseModel):
    """A cron-driven invocation of a registered tool.

    `plugin` is filled in by the registry from the registering plugin's
    name. `tool` is the qualified tool name (e.g. "routine.weather_daily").
    `cron` is a standard 5-field cron expression, validated at construction
    time via croniter. `input` is the params dict passed to the tool.
    """

    model_config = ConfigDict(frozen=True)

    plugin: str = ""
    name: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    cron: str = Field(min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)

    @field_validator("cron")
    @classmethod
    def _cron_must_be_valid(cls, v: str) -> str:
        if not croniter.is_valid(v):
            raise ValueError(f"invalid cron expression: {v!r}")
        return v

    @computed_field
    @property
    def qualified_name(self) -> str:
        return f"{self.plugin}.{self.name}" if self.plugin else self.name
