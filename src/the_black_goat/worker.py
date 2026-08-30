"""The Black Goat absurd worker.

Drains the absurd queue and runs `goat_run_tool` tasks in-process — this is what
actually performs the fact/receipt/definition/people upserts enqueued by the
ingest edge, and the tool invocations that pg_cron schedules (e.g. the daily
brief) fire. It discovers every installed plugin via entry points, so the image
it runs in must have the plugins installed.

Env:
  ABSURD_DATABASE_URL   the goat_memory Postgres (required)
  GOAT_QUEUE            queue name (default "default"), shared with the ingest
                       edge and the pg_cron schedule commands
  plus each plugin's own config (FACTS_DATABASE_URL, SLACK_*, ...), resolved at
  registry-build time via EnvConfigSource.
"""

from __future__ import annotations

import os


def main() -> None:
    from absurd_sdk import Absurd

    from the_black_goat import build_registry
    from the_black_goat.config import EnvConfigSource

    db_url = os.environ.get("ABSURD_DATABASE_URL")
    if not db_url:
        raise SystemExit("ABSURD_DATABASE_URL is required")
    queue = os.environ.get("GOAT_QUEUE", "default")

    absurd = Absurd(db_url, queue_name=queue)
    absurd.create_queue()  # idempotent
    # build_registry installs the generic goat_run_tool task on this absurd app
    # (see registry.install_runner) and discovers all installed plugins.
    build_registry(config_source=EnvConfigSource(), absurd=absurd)

    print(f"the-black-goat-worker draining queue {queue!r}", flush=True)
    absurd.start_worker()


if __name__ == "__main__":
    main()
