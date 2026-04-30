from the_black_goat._hookspec import hookimpl
from the_black_goat.tools import DurabilitySpec, SideEffect, ToolDef, durable, tool

__all__ = [
    "DurabilitySpec",
    "SideEffect",
    "ToolDef",
    "durable",
    "hookimpl",
    "tool",
]


def main() -> None:
    print("Hello from the-black-goat!")
