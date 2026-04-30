# the-black-goat

<p align="center">
  <img src="docs/img/black-goat.png" alt="the black goat" width="320">
</p>

> An agent-building framework. Programs first, agents embedded.
> *Iä! Shub-Niggurath! The Black Goat of the Woods with a Thousand Young.*

`the-black-goat` builds tools that mix **deterministic programs** with **embedded agents** for decision-making and summary. Lean core, plugin-extensible via `pluggy` (the thousand young), functional core / imperative shell.

The agent is a component inside the program — a familiar bound to the circle, not the thing summoning it.

## Stack

- **absurd** — Postgres-backed durable task execution. *That is not dead which can eternal lie* — and with strange aeons, even cancelled runs may resume.
- **dspy** — agent / LM programming. All whispers to the model pass through here.
- **pydantic** — validation at every boundary. The elder sign against malformed input.
- **fastapi** — HTTP surface, when one is needed.
- **pluggy** — plugin system. Domain integrations are spawn, not core.

## Quickstart

```bash
task db:up       # wake the sleeper in R'lyeh (Postgres, via docker compose)
task test        # run the suite
task             # list every rite
```

## Operating rules

See [AGENTS.md](AGENTS.md) for the rules every contributor (human or agent) works under: model/reality discipline, prediction-before-action, batch checkpointing, and TDD judged by a subagent.

> *Reality doesn't care about your model. The gap between model and reality is where all failures live — and where the Old Ones wait.*
