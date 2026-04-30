from __future__ import annotations

import inspect
from typing import Any, Callable, Iterable, Literal

from absurd_sdk import CancellationPolicy, RetryStrategy
from pydantic import BaseModel, ConfigDict, computed_field

SideEffect = Literal[
    "pure",
    "reads_external",
    "writes_external",
    "human_interaction",
    "spends_money",
]


class DurabilitySpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    retry_strategy: RetryStrategy | None = None
    max_attempts: int | None = None
    queue: str = "default"
    cancellation: CancellationPolicy | None = None


class ToolDef(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    plugin: str = ""
    name: str
    desc: str = ""
    func: Callable[..., Any]
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    config_schema: type[BaseModel] | None = None
    is_async: bool = False
    is_idempotent: bool = False
    side_effect: SideEffect = "writes_external"
    requires_confirmation: bool = False
    tags: tuple[str, ...] = ()
    durability: DurabilitySpec | None = None

    @computed_field
    @property
    def qualified_name(self) -> str:
        return f"{self.plugin}.{self.name}" if self.plugin else self.name


def tool(
    *,
    name: str,
    func: Callable[..., Any],
    input: type[BaseModel],
    output: type[BaseModel],
    desc: str | None = None,
    config: type[BaseModel] | None = None,
    is_idempotent: bool = False,
    side_effect: SideEffect = "writes_external",
    requires_confirmation: bool = False,
    tags: Iterable[str] = (),
) -> ToolDef:
    """Build a ToolDef atom from a typed callable."""
    resolved_desc = desc if desc is not None else (func.__doc__ or "").strip()
    return ToolDef(
        name=name,
        desc=resolved_desc,
        func=func,
        input_schema=input,
        output_schema=output,
        config_schema=config,
        is_async=inspect.iscoroutinefunction(func),
        is_idempotent=is_idempotent,
        side_effect=side_effect,
        requires_confirmation=requires_confirmation,
        tags=tuple(tags),
    )


def durable(
    inner: ToolDef,
    *,
    retry_strategy: RetryStrategy | None = None,
    max_attempts: int | None = None,
    queue: str = "default",
    cancellation: CancellationPolicy | None = None,
) -> ToolDef:
    """Wrap an atom ToolDef with durability metadata.

    Returns a new ToolDef sharing the inner's name, schemas, func, and
    metadata, with `durability` populated. Raises ValueError if `inner`
    already has durability set.
    """
    if inner.durability is not None:
        raise ValueError(f"tool {inner.name!r} is already durable; cannot re-wrap")
    spec = DurabilitySpec(
        retry_strategy=retry_strategy,
        max_attempts=max_attempts,
        queue=queue,
        cancellation=cancellation,
    )
    return inner.model_copy(update={"durability": spec})
