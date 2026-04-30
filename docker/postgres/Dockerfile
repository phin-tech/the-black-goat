# Postgres 17 with pg_cron installed.
# pg_cron is enabled at runtime via the `shared_preload_libraries` and
# `cron.database_name` flags set in compose.yml's `command:` block.

FROM postgres:17

RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-17-cron \
 && rm -rf /var/lib/apt/lists/*
