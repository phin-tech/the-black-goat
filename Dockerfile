# The Black Goat application image — runs both the ingest edge and the absurd
# worker (the compose file picks the command per service). Installs only the
# `deploy` dependency group, so google-calendar (and its required config) stay
# out of the deployed registry.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app
COPY . .

# --no-editable installs the workspace packages as built copies (no source
# links), --only-group deploy restricts to the runtime plugins + services.
RUN uv sync --frozen --no-dev --only-group deploy --no-editable

ENV PATH="/app/.venv/bin:$PATH"

# Overridden per service in the homelab compose:
#   ingest: ["the-black-goat-ingest", "--host", "0.0.0.0"]
#   worker: ["the-black-goat-worker"]
CMD ["the-black-goat-worker"]
