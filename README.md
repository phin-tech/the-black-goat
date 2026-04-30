# the-black-goat

<p align="center">
  <img src="docs/img/black-goat.png" alt="the black goat" width="320">
</p>

> An agent-building framework. Programs first, agents embedded.

`the-black-goat` builds tools that mix **deterministic programs** with **embedded agents** for decision-making and summary. Lean core, plugin-extensible via `pluggy`, functional core / imperative shell.

## Stack

- **absurd** — Postgres-backed durable task execution
- **dspy** — agent / LM programming
- **pydantic** — validation at boundaries
- **fastapi** — HTTP surface
- **pluggy** — plugin system for extras

## Quickstart

```bash
task db:up       # start Postgres (docker compose)
task test        # run the suite
task             # list everything
```

## Operating rules

See [AGENTS.md](AGENTS.md) for the rules every contributor (human or agent) works under: model/reality discipline, prediction-before-action, batch checkpointing, and TDD judged by a subagent.
