from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from croniter import croniter
from psycopg import Connection
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

if TYPE_CHECKING:
    from the_black_goat.registry import Registry


GOAT_JOB_PREFIX = "goat:"
DOLLAR_TAG = "goatparams"  # dollar-quote tag for embedding JSON in cron commands

# pg_cron 1.4+ accepts interval syntax in addition to standard cron, e.g.
# "5 seconds", "10 minutes". croniter doesn't recognize this form, so we
# allow it through a separate regex check.
_PGCRON_INTERVAL_RE = re.compile(
    r"^\s*\d+\s+(second|seconds|minute|minutes|hour|hours|day|days)\s*$",
    re.IGNORECASE,
)


def _is_valid_schedule_expression(value: str) -> bool:
    return bool(croniter.is_valid(value) or _PGCRON_INTERVAL_RE.match(value))


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
        if not _is_valid_schedule_expression(v):
            raise ValueError(
                f"invalid cron expression {v!r}: expected a 5-field cron "
                "(e.g. '0 5 * * *') or a pg_cron interval (e.g. '5 seconds')"
            )
        return v

    @computed_field
    @property
    def qualified_name(self) -> str:
        return f"{self.plugin}.{self.name}" if self.plugin else self.name


def _build_command(schedule: Schedule, queue: str = "default") -> str:
    """Render the SQL command pg_cron will execute on tick.

    Spawns the generic `goat_run_tool` task with `{tool, input}` params.
    Uses dollar-quoting for the JSON payload to avoid SQL-injection-style
    quoting issues.
    """
    payload = json.dumps(
        {"tool": schedule.tool, "input": schedule.input}, sort_keys=True
    )
    if f"${DOLLAR_TAG}$" in payload:
        # Vanishingly unlikely with json.dumps output, but guard anyway.
        raise ValueError(
            f"schedule input contains the reserved dollar-quote tag "
            f"${DOLLAR_TAG}$; pick a different input shape"
        )
    return (
        f"SELECT absurd.spawn_task("
        f"{queue!r}, 'goat_run_tool', "
        f"${DOLLAR_TAG}${payload}${DOLLAR_TAG}$::jsonb, "
        f"'{{}}'::jsonb"
        f");"
    )


def apply_schedules(
    registry: "Registry",
    db_url: str,
    *,
    dry_run: bool = False,
    queue: str = "default",
) -> dict[str, list[str]]:
    """Reconcile pg_cron's cron.job table with the registry's Schedules.

    For each Schedule, ensures a `cron.job` row exists with:
      jobname  = f"goat:{schedule.qualified_name}"
      schedule = schedule.cron
      command  = SELECT absurd.spawn_task(<queue>, 'goat_run_tool', payload, '{}')

    Re-running with the same registry is a no-op (cron.schedule with a
    name replaces in place, so cron expression updates land cleanly).
    Existing `goat:*` jobs not present in the registry are removed via
    cron.unschedule.

    Returns a summary: {"added": [...], "kept": [...], "removed": [...]}.
    `added`/`kept` distinguish first-time inserts from updates of
    already-present jobs; `removed` lists orphan jobnames.
    """
    desired: dict[str, tuple[str, str]] = {}
    for s in registry.schedules():
        jobname = f"{GOAT_JOB_PREFIX}{s.qualified_name}"
        desired[jobname] = (s.cron, _build_command(s, queue=queue))

    summary: dict[str, list[str]] = {"added": [], "kept": [], "removed": []}

    with Connection.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT jobname FROM cron.job WHERE jobname LIKE %s",
                (f"{GOAT_JOB_PREFIX}%",),
            )
            existing = {row[0] for row in cur.fetchall()}

            for jobname, (cron_expr, command) in desired.items():
                bucket = "kept" if jobname in existing else "added"
                summary[bucket].append(jobname)
                if not dry_run:
                    cur.execute(
                        "SELECT cron.schedule(%s, %s, %s)",
                        (jobname, cron_expr, command),
                    )

            for jobname in sorted(existing - desired.keys()):
                summary["removed"].append(jobname)
                if not dry_run:
                    cur.execute("SELECT cron.unschedule(%s)", (jobname,))

    summary["added"].sort()
    summary["kept"].sort()
    return summary


def _cli() -> None:
    """`python -m the_black_goat.scheduling apply` entry point."""
    import os
    import sys

    if len(sys.argv) < 2 or sys.argv[1] != "apply":
        print(
            "usage: python -m the_black_goat.scheduling apply",
            file=sys.stderr,
        )
        sys.exit(2)

    db_url = os.environ.get(
        "ABSURD_DATABASE_URL",
        "postgresql://absurd:absurd@localhost:5432/absurd",
    )

    from the_black_goat import build_registry
    from the_black_goat.config import EnvConfigSource

    registry = build_registry(config_source=EnvConfigSource())
    summary = apply_schedules(registry, db_url)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    _cli()
