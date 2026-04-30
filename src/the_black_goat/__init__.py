from the_black_goat._hookspec import hookimpl
from the_black_goat.registry import Registry, build_registry
from the_black_goat.tools import DurabilitySpec, SideEffect, ToolDef, durable, tool

__all__ = [
    "DurabilitySpec",
    "Registry",
    "SideEffect",
    "ToolDef",
    "build_registry",
    "durable",
    "hookimpl",
    "tool",
]


def main() -> None:
    print("Hello from the-black-goat!")
