# Workshop 4 — Orchestrator

**Build the harness that manages multiple agents: one lead, N workers, run in parallel.**

> Workshop 3's factory ran a fixed *line* — plan, implement, review — one worker
> per stage, in sequence. An orchestrator is the general shape: a **lead** agent
> that decides at runtime how the work splits, N **worker** agents that run that
> split **concurrently**, and a **synthesizer** that merges what comes back. The
> factory is the N=1, fixed-order special case; this is the tree. You build it by
> hand on **LangGraph** (the same stack WS2 used), then collapse it into a
> dozen lines with **deepagents** — build the mechanism, then see the shortcut.

## What an orchestrator is (and how it differs from the factory)

Both are meta-harnesses — layers *above* harnesses that route work to them and
govern them. The difference is shape:

- A **factory** is a **line**: stages in a fixed order, one worker running at a
  time, state flowing forward with one feedback loop. WS3 built that.
- An **orchestrator** is a **tree**: a lead decomposes a task into subtasks that
  don't depend on each other, fans them out to workers that run **at the same
  time**, and merges the results. The order and the count of workers are decided
  at runtime, not wired in advance.

The factory *is* an orchestrator in its simplest useful shape. This workshop
builds the shape the factory left out: **concurrency, and a fan-out whose width the
lead picks at runtime**.

## Duration

3 hours, five segments. See `workshop.md`.

## Prerequisites

- **WS2's stack in your hands.** You've built a LangGraph graph before —
  nodes, edges, a `TypedDict` state. WS4 adds the fan-out primitive (`Send`) and a
  reducer for fan-in.
- Comfortable with the idea that N things run at once and finish in any order, and
  that one of them can fail while the others succeed.
- You understand why "spawn a worker per subtask" needs a bound before it needs
  anything else.

## Dependencies

Back on the LangChain stack WS2 used — no Claude Agent SDK here (that was WS3).

| Need | Why |
|---|---|
| [`uv`](https://docs.astral.sh/uv/) + Python 3.11+ | Builds the env and runs the code: `uv sync`, `uv run`. |
| `langchain` + `langchain-anthropic` | The model binding for every role. |
| `langgraph` | The orchestration graph: `Send` for fan-out, a reducer for fan-in. |
| `deepagents` | The shortcut — a lead with a `task` tool that delegates to subagents. |
| `pytest` (sandbox group) | The worker agents run the seeded sandbox's tests; `uv sync` installs it. Not an orchestrator dep. |
| `ANTHROPIC_API_KEY` | The models are billed per token. No subscription-token path here. |
| `git` | Each parallel worker gets its own **worktree** so they don't collide. |

**Auth, the short version.** WS4 calls the Anthropic API through
langchain-anthropic, so it needs a key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # or put it in .env
```

Budget a few dollars — a fan-out is N workers at once, so watch `MAX_SUBTASKS`.

## Setup (BEFORE the workshop)

```bash
cd 04-orchestrator
uv sync                       # creates .venv and installs from pyproject.toml
cp .env.example .env          # set ANTHROPIC_API_KEY; leave MAX_SUBTASKS=5

# The sandbox library (three independent modules) ships in src/sandbox/. Make it
# its own git repo so each worker can branch a worktree from a clean HEAD.
git -C src/sandbox init -q
git -C src/sandbox add -A && git -C src/sandbox commit -qm seed

uv run python src/orchestrator.py   # decompose → parallel workers → one summary
```

You should see the lead split the task into a few subtasks, several workers run,
and one synthesized summary at the end. The seed commit matters: worktrees branch
from `HEAD`, so the sandbox must have at least one commit.

## What you'll build

`src/orchestrator.py` — a LangGraph graph that fans out and back in:

```
                 ┌─► worker (worktree 1) ─┐
START → decompose ┼─► worker (worktree 2) ─┼─► synthesize → END
                 └─► worker (worktree N) ─┘
        (LEAD decides N)   (run concurrently)   (fan-in merges)
```

- **`decompose`** — the LEAD node. One smart-model call turns the task into a JSON
  list of *independent* subtasks. N is decided here, at runtime — not wired in.
- **`assign_workers`** — the fan-out. A conditional edge returns one
  `Send("worker", …)` per subtask; LangGraph runs them concurrently.
- **`worker`** — each worker is its own `create_agent` react agent, running one subtask
  in its own **git worktree** (`worktree.py`) with tools scoped to it, so N
  workers editing at once never collide. Wrapped so one failure isn't total.
- **`synthesize`** — the fan-in. The `operator.add` reducer collects every
  worker's result into one list; a smart-model call merges them into a summary and
  is honest about what failed.
- **`shortcut.py`** — the same orchestration with `deepagents.create_deep_agent`
  and a worker *subagent*: a dozen lines, the mechanism hidden. Build first, then
  see what the shortcut costs you (isolation and failure handling go into the
  library).

## Learning objectives

By the end you can:

1. Say what an orchestrator adds over a factory — fan-out and concurrency, with N
   decided at runtime — and why the factory is its N=1, fixed-order special case.
2. Fan out to N workers with LangGraph's `Send`, and fan back in with a reducer
   (`Annotated[list, operator.add]`), passing per-worker state that differs from
   the graph's.
3. Isolate parallel workers so they don't corrupt each other — a worktree per
   worker, tools scoped to it, git access serialized by a lock.
4. Survive partial failure: one worker fails, its siblings succeed, and the
   synthesizer merges what it has instead of the whole run dying.
5. Reach for the deepagents shortcut when you don't need the mechanism in your
   hands — and name what you gave up to get it.

## The bound comes first

A single agent that loops forever wastes one budget. An orchestrator that fans out
with no bound spawns N of them at once — the failure mode is multiplied, not
added. So the first line of defense is `MAX_SUBTASKS`: the lead proposes the
split, the orchestrator caps it. Everything else (per-worker isolation, partial-
failure handling, an aggregate cost budget in the take-home) sits on top of that
one cap. Fan-out earns its speed only if it's bounded first.

## The whole series, closed

Charter (the standard) → Harness (applies it to one run) → Factory (a line of
agent processes → PR) → **Orchestrator** (a lead fanning work out to parallel
workers). Every Workshop 1 lever is still here — narrow input at `decompose`,
narrow output at `synthesize`, narrow recovery in the bound and the partial-
failure handling. You started with prose. You're ending with a tree of agents you
can supervise.

## Checkpoints

Five, one per segment. `src/orchestrator.py` is the assembled reference;
`src/shortcut.py` is the deepagents version from the final segment.
