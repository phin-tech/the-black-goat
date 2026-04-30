from __future__ import annotations

import os
from typing import Any, Mapping, Protocol, runtime_checkable

from pydantic import BaseModel, ValidationError

from the_black_goat.errors import ConfigError


@runtime_checkable
class ConfigSource(Protocol):
    """Resolves a Pydantic config schema for a plugin into an instance."""

    def resolve(self, plugin: str, schema: type[BaseModel]) -> BaseModel: ...


class DictConfigSource:
    """Test-friendly config source backed by a `{plugin: {field: value}}` dict."""

    def __init__(self, data: Mapping[str, Mapping[str, Any]]) -> None:
        self._data = {k: dict(v) for k, v in data.items()}

    def resolve(self, plugin: str, schema: type[BaseModel]) -> BaseModel:
        if plugin not in self._data:
            raise ConfigError(
                f"DictConfigSource has no config for plugin {plugin!r}"
            )
        try:
            return schema.model_validate(self._data[plugin])
        except ValidationError as exc:
            raise ConfigError(
                f"config for plugin {plugin!r} failed validation: {exc}"
            ) from exc


class EnvConfigSource:
    """Resolves config from environment variables.

    For plugin `twilio` and schema field `api_key`, looks up env var
    `TWILIO_API_KEY`. Missing env vars fall back to schema defaults; a
    required field with no env var and no default raises `ConfigError`.
    """

    def resolve(self, plugin: str, schema: type[BaseModel]) -> BaseModel:
        prefix = f"{plugin.upper()}_"
        raw: dict[str, str] = {}
        for field_name in schema.model_fields:
            env_key = prefix + field_name.upper()
            value = os.environ.get(env_key)
            if value is not None:
                raw[field_name] = value
        try:
            return schema.model_validate(raw)
        except ValidationError as exc:
            raise ConfigError(
                f"env config for plugin {plugin!r} failed validation: {exc}"
            ) from exc
