from __future__ import annotations


class GoatError(Exception):
    """Base class for the-black-goat errors."""


class ToolNotFound(GoatError):
    """Raised when a requested tool name is not registered."""


class AbsurdNotConfigured(GoatError):
    """Raised when a durable tool is registered without an absurd client."""


class ToolKindMismatch(GoatError):
    """Raised when invoke() is called on an async tool, or ainvoke() on
    something that can't be awaited as expected for the call kind."""
