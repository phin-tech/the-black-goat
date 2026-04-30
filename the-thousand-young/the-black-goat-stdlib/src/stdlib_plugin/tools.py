from __future__ import annotations

import time
from datetime import datetime, timezone

from pydantic import BaseModel, Field


# ---------- now ----------


class NowInput(BaseModel):
    pass


class NowOutput(BaseModel):
    iso: str
    epoch: float


def now(input: NowInput) -> NowOutput:
    """Current UTC timestamp."""
    dt = datetime.now(timezone.utc)
    return NowOutput(iso=dt.isoformat(), epoch=dt.timestamp())


# ---------- sleep ----------


class SleepInput(BaseModel):
    seconds: float = Field(ge=0.0)


class SleepOutput(BaseModel):
    slept: float


def sleep(input: SleepInput) -> SleepOutput:
    """Block for N seconds and return how long was actually slept."""
    start = time.monotonic()
    time.sleep(input.seconds)
    return SleepOutput(slept=time.monotonic() - start)


# ---------- echo ----------


class EchoInput(BaseModel):
    message: str


class EchoOutput(BaseModel):
    message: str


def echo(input: EchoInput) -> EchoOutput:
    """Return the input message unchanged."""
    return EchoOutput(message=input.message)
