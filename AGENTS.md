# the-black-goat

An agent-building framework. Programs first, agents embedded. Lean core, plugin-extensible, functional core / imperative shell.

## What this is

`the-black-goat` builds tools that mix **deterministic programs** with **agents for decision-making and summary**. The agent is a component inside a program, not the program itself.

Contrast with openclaw / nano-claw: those are agent-first. We are program-first with agents as embedded judgment.

### Stack

- **absurd** — Postgres-backed task queue / durable execution. Long-running work and retries live here.
- **dspy** — Agent / LM programming. All model calls go through dspy modules.
- **pydantic** — Validation at every boundary.
- **fastapi** — HTTP surface when one is needed.
- **pluggy** — Plugin system. Extras are installable packages, not core code.

### Architectural principles

1. **Programs with embedded agents.** The default shape is a deterministic flow that calls an agent for a specific decision or summary. Agent-driving-everything is the exception.
2. **Lean core.** The core is a framework for building these tools plus a minimal TUI. Everything else — Twilio, Slack, vendor integrations, domain tools — is a `pluggy` plugin.
3. **Functional core / imperative shell.** Pure functions in the middle. I/O, side effects, and orchestration at the edges. Extend this to module boundaries: pure decision logic separate from durable-execution wiring.
4. **Straightforward human interfaces.** Communication with humans (Twilio, Slack, email) happens through tool-shaped interfaces. Keep them small and obvious.

## Running commands

**Always use `uv run` to execute Python.** Never call `python` / `python3` / `pytest` / project scripts directly — they will use a different interpreter or miss project dependencies.

- Run a script: `uv run python -c "..."` or `uv run script.py`
- Run tests: `uv run pytest` (or `task test`)
- Run the CLI entrypoint: `uv run the-black-goat`
- Add a dependency: `uv add <pkg>` (not `pip install`)
- Add a dev dependency: `uv add --dev <pkg>`

Anything that needs a Python interpreter or project deps goes through `uv run`. If a command fails because something isn't installed, the fix is `uv add`, not falling back to system Python.

### Common workflows go through `task`

Repeated multi-step commands belong in `Taskfile.yml` and are run via `task <name>`. Don't paste raw `docker compose ...` invocations into the transcript when a task already wraps it.

- `task` — list everything available
- `task db:up` / `task db:down` / `task db:reset` — Postgres lifecycle
- `task db:psql` / `task db:logs` — inspect the running database
- `task test` — run pytest (extra args after `--`, e.g. `task test -- -k foo`)

If you type the same multi-step command twice, add it to `Taskfile.yml`.

## The One Rule

**Reality doesn't care about your model. The gap between model and reality is where all failures live.**

When reality contradicts your model, your model is wrong. **Stop.** Fix the model before doing anything else. Don't patch around the surprise. Don't keep going and hope. Investigate.

## Make beliefs pay rent in anticipated experiences

This is the behavior change that matters most.

**BEFORE every action that could fail**, write out in the transcript:

```
DOING: [action]
EXPECT: [specific predicted outcome]
IF YES: [conclusion, next action]
IF NO: [conclusion, next action]
```

THEN the tool call.

**AFTER**, immediate comparison:

```
RESULT: [what actually happened]
MATCHES: [yes/no]
THEREFORE: [conclusion and next action, or STOP if unexpected]
```

This is not bureaucracy. This is how you catch yourself being wrong before it costs hours. This is science, not flailing.

The user cannot see your thinking block. Without explicit predictions in the transcript, your reasoning is invisible. With them, the user can follow along, catch errors in your logic, and you can look back at what you actually predicted vs. what happened.

Skip this and you're just running commands and hoping.

## Feedback loops

- **One experiment at a time.**
- **Batch size: 3. Then checkpoint.**

A checkpoint is verification that reality matches your model:

1. Run the test
2. Read the output
3. Write down what you found
4. Confirm it worked

Task lists are not checkpoints. Thinking is not a checkpoint. **Observable reality is the checkpoint.**

More than 5 actions without verification = accumulating unjustified beliefs. Stop and verify.

## Development workflow — TDD, judged

All development follows TDD:

1. **Write the test.**
2. **Show it red.** Run it. Paste the failure. Confirm it fails for the reason you expect (not an import error masquerading as a real failure).
3. **Make it green.** Minimum code to pass.
4. **Refactor.** Only with green tests.

**Tests are judged by a subagent against the plan.** Before claiming a feature complete, dispatch a subagent to evaluate whether the tests actually cover what the plan said they should. The author of the test cannot also be its judge.

### What this implies

- No "I'll add tests later." The test comes first or the change doesn't land.
- A failing test that fails for the wrong reason is a model/reality gap — apply The One Rule.
- If you cannot write a test for a behavior, the design is probably wrong. Surface that, don't paper over it.
