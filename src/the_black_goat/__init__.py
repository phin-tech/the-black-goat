from the_black_goat._hookspec import hookimpl
from the_black_goat.operations import (
    RoutineDefinition,
    SignalDefinition,
    SignalProposal,
    SourceDefinition,
)
from the_black_goat.registry import Registry, build_registry, current_registry
from the_black_goat.scheduling import Schedule
from the_black_goat.tools import DurabilitySpec, SideEffect, ToolDef, durable, tool

__all__ = [
    "DurabilitySpec",
    "Registry",
    "RoutineDefinition",
    "Schedule",
    "SignalDefinition",
    "SignalProposal",
    "SideEffect",
    "SourceDefinition",
    "ToolDef",
    "build_registry",
    "current_registry",
    "durable",
    "hookimpl",
    "tool",
]


def main() -> None:
    print("Hello from the-black-goat!")
