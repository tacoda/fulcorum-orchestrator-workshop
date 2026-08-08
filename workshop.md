# Workshop 4 — Orchestrator (3 hours)

> Workshop 3 ran a fixed line of agents, one at a time. Now build the general
> shape: a **lead** that decides at runtime how the work splits, N **workers** that
> run that split **concurrently**, and a **synthesizer** that merges the results.
> You build it by hand on **LangGraph** — `Send` for fan-out, a reducer for fan-in
> — then collapse it into a dozen lines with **deepagents**. A harness that manages
> multiple agents at once is an orchestrator; the factory was its N=1 special case.

You'll build `src/orchestrator.py` from the lead down to the synthesizer, then
meet the deepagents shortcut in `src/shortcut.py`.

---

## The clock

| Time | Segment |
|---|---|
| 0:00–0:15 | 0. From a line to a tree: what an orchestrator adds |
| 0:15–0:55 | 1. The lead: decompose a task at runtime |
| 0:55–1:40 | 2. Fan-out: run workers concurrently, isolated |
| 1:40–1:50 | Break |
| 1:50–2:30 | 3. Fan-in: synthesize, and survive the worker that fails |
| 2:30–3:00 | 4. The shortcut (deepagents); the levers, restated |

---

## Segment 0 — From a line to a tree (0:00–0:15)

Confirm the smoke test from the README ran. Then put the two shapes on the board
side by side:

```
FACTORY (WS3):   plan → implement → review → ship        one worker at a time
ORCHESTRATOR:    decompose ─┬─ worker ─┐                 N workers at once
                            ├─ worker ─┼─ synthesize
                            └─ worker ─┘
```

The factory answered *who runs when* for a fixed line. The orchestrator answers
three questions the line never had to:

- **How many?** — the lead decides N at runtime. You don't wire it.
- **At the same time** — the workers run concurrently, and finish in any order.
- **What if one fails?** — the others still finished; the run must survive it.

The factory *is* an orchestrator in its simplest shape (N=1, fixed order). This
workshop builds the shape it left out: fan-out and concurrency, N decided at
runtime. Everything
else — the levers from WS1, the meta-harness framing from WS3 — carries over
unchanged. What's new is that the units being managed are *agents*, not tools or
stages, and they run in parallel.

> One sentence to keep: a harness manages tools, a factory manages stages, an
> orchestrator manages **agents**.

---

## Segment 1 — The lead: decompose a task at runtime (0:15–0:55)

### 1.1 — The state (10 min)

The orchestrator's memory is a LangGraph `TypedDict` — but the interesting field
is the one with a **reducer**:

```python
class OrchestratorState(TypedDict):
    task: str
    subtasks: list[dict]
    results: Annotated[list[dict], operator.add]   # fan-in happens here
    summary: str
```

`results` is annotated with `operator.add`. When N workers each return
`{"results": [one_result]}`, LangGraph *adds* the lists together instead of
overwriting — that single annotation is the entire fan-in mechanism. Point at it
now; you'll rely on it in Segment 3.

### 1.2 — The decompose node (22 min)

The LEAD is one smart-model call whose whole job is to split the work. The charter
is the contract: independent subtasks, JSON only.

```python
LEAD = """You are the lead. Break the task into INDEPENDENT subtasks that can run
in parallel WITHOUT touching the same files. Output ONLY a JSON array of objects:
{"id": "<slug>", "title": "...", "prompt": "..."}. No prose."""

def decompose(state):
    resp = chat(SMART).invoke([SystemMessage(content=LEAD),
                               HumanMessage(content=state["task"])])
    return {"subtasks": _parse_subtasks(resp.content)[:MAX_SUBTASKS]}
```

Two things to land:

- **Independence is the whole ballgame.** Parallel workers are only safe if their
  subtasks don't depend on each other. That constraint lives in the lead's charter,
  and a bad split is the orchestrator's version of a bad plan. When the workers
  collide, the fix is usually a sharper decompose prompt, not more locking.
- **`[:MAX_SUBTASKS]` is not a nicety.** The lead is non-deterministic; nothing
  stops it proposing thirty subtasks. The cap is the first bound, before isolation,
  before anything. Fan-out with no cap is a way to spawn thirty agents by accident.

### 1.3 — Parse the split (8 min)

`_parse_subtasks` does `json.loads`, and if the lead wrapped the array in prose,
digs the `[...]` out with a regex. Same lesson as WS3's verdict parse: when the
parse is flaky, sharpen the charter before you add parser code.

> **Checkpoint 1:** run just `decompose` on the default task and print `subtasks`.
> You should see a short JSON list — one subtask per module. No workers yet.

---

## Segment 2 — Fan-out: run workers concurrently, isolated (0:55–1:40)

This is the segment that separates an orchestrator from a `for` loop.

### 2.1 — The fan-out edge (15 min)

The fan-out is one LangGraph primitive. A conditional edge returns a *list* of
`Send` objects, and the runtime runs the targets concurrently — each with its own
slice of state:

```python
def assign_workers(state):
    return [Send("worker", {"subtask": st}) for st in state["subtasks"]]

g.add_conditional_edges("decompose", assign_workers, ["worker"])
```

`Send("worker", {"subtask": st})` invokes the `worker` node with a state that
differs from the graph's — just its one subtask. N Sends, N concurrent workers.
That's the map in map-reduce; the `operator.add` reducer from 1.1 is the reduce.

### 2.2 — Each worker is its own agent, isolated (20 min)

A worker isn't a model call — it's a whole react agent, running one subtask in its
own **git worktree** so N of them editing at once don't clobber each other:

```python
def worker(state):
    st = state["subtask"]
    with isolated(st["id"]) as workdir:                       # its own worktree
        agent = create_agent(chat(CHEAP), make_tools(workdir), system_prompt=WORKER)
        out = agent.invoke({"messages": [HumanMessage(content=st["prompt"])]})
        report = out["messages"][-1].content
    return {"results": [{"id": st["id"], "report": report, "ok": True}]}
```

Open `worktree.py` and read it together. Two ideas:

- **Isolation has a filesystem analog.** Each worker already gets its own context
  window; the worktree gives it its own working files. `git worktree add` is the
  cheap way to get N copies that share history but not the tree.
- **The shared resource still needs a lock.** git serializes on the repo index, so
  two concurrent `worktree add`s can collide on `.git`. The lock in `worktree.py`
  is held only for the fast plumbing — never during the model call — so creation is
  serialized while the *work* stays parallel.

### 2.3 — Watch it run (10 min)

Run the graph through `worker`. Watch several workers start together and finish out
of order. This is the payoff and the hazard in one: it's fast because it's
parallel, and it's only *safe* because it's bounded and isolated.

> **Checkpoint 2:** the full fan-out runs; N workers edit N worktrees
> concurrently; `results` comes back with one entry per worker. Order will vary
> run to run — that's correct.

---

## Break (1:40–1:50)

---

## Segment 3 — Fan-in: synthesize, and survive failure (1:50–2:30)

### 3.1 — One worker fails; the run must not (15 min)

The whole point of N workers is that they're independent — so one dying can't take
the rest with it. The worker body is wrapped:

```python
try:
    with isolated(st["id"]) as workdir:
        ...
    return {"results": [{..., "ok": True}]}
except Exception as e:
    return {"results": [{..., "report": f"FAILED: {e}", "ok": False}]}
```

A raised exception becomes an `ok: False` result, not a crashed graph. This is the
concurrency version of WS2's kill switch and WS3's escalate: the orchestrator
defines what happens when a worker fails, so a failure is a data point the
synthesizer reads — not a stack trace that ends the run.

### 3.2 — The synthesizer (15 min)

Fan-in is where the `operator.add` reducer pays off: every worker's result is
already collected in `results`. The synthesizer merges them, and stays honest
about the failures:

```python
def synthesize(state):
    if not any(r["ok"] for r in state["results"]):
        return {"summary": "ESCALATE: every worker failed. Nothing to merge."}
    reports = "\n\n".join(f"[{r['id']}] {'ok' if r['ok'] else 'FAILED'}\n{r['report']}"
                          for r in state["results"])
    resp = chat(SMART).invoke([SystemMessage(content=SYNTH),
                               HumanMessage(content=f"...\n{reports}")])
    return {"summary": resp.content}
```

Two design choices worth naming: it runs on the smart model (merging N outputs is
judgment, not mechanics), and it *degrades gracefully* — it merges the workers that
succeeded and reports the ones that didn't, rather than demanding all-or-nothing.
Total failure is the only escalate.

### 3.3 — Why merging is the hard half (10 min)

Discuss with the code up: fan-out is one `Send`; fan-in is where the difficulty
actually lives. N non-deterministic agents produce N outputs that may overlap,
conflict, or contradict — and something has to reconcile them into one coherent
result. Here the synthesizer merges *reports*; merging the actual diffs from N
worktrees into one branch is harder still (that's the take-home). The lesson: the
cost of parallelism isn't the spawning, it's the reconciling.

> **Checkpoint 3:** give it a task where one subtask can't succeed (name a module
> that doesn't exist). Watch that worker come back `FAILED`, the others succeed,
> and the summary report both. The run completes; it does not crash.

---

## Segment 4 — The shortcut (deepagents); the levers restated (2:30–3:00)

### 4.1 — The same thing in a dozen lines (12 min)

WS2 ended by showing deepagents collapse a hand-built harness into one call. Same
move here. `create_deep_agent` gives you a lead with a `task` tool that delegates
to **subagents** — the orchestrator pattern, built in:

```python
worker_subagent = {
    "name": "worker",
    "description": "Do one independent subtask; give it one at a time.",
    "model": f"anthropic:{CHEAP}",
    "system_prompt": "Do exactly your one subtask. Smallest diff, ship a test.",
    "tools": make_tools(SANDBOX),
}
agent = create_deep_agent(model=chat(SMART), tools=..., system_prompt=LEAD,
                          subagents=[worker_subagent])
```

Run `src/shortcut.py`. It does what your hand-built graph does — decompose,
delegate, merge — with none of the wiring visible.

### 4.2 — What the shortcut costs (10 min)

The trade is the same one WS2 named. What you gain: almost no orchestration code.
What you give up: the fan-out, the worktree isolation, and the failure handling are
now *inside* the library. In `shortcut.py` every subagent shares one sandbox —
the isolation you built by hand in Segment 2 is gone unless you rebuild it. Build
by hand when you need the mechanism in your control (isolation, bounds, custom
failure policy); reach for deepagents when you trust the defaults. Knowing which
`orchestrator.py` line disappears into the library is the point of building both.

### 4.3 — The levers, and the series (8 min)

Every Workshop 1 lever is still here, now operating on a tree of agents:

- **Narrow input** → `decompose` turns a broad task into scoped, independent
  subtasks before any worker runs.
- **Narrow output** → `synthesize` merges N outputs into one reviewed result and
  reports what failed.
- **Narrow recovery** → `MAX_SUBTASKS`, the per-worker try/except, and the
  total-failure escalate.

And the arc, closed across four workshops:

- **Charter**: the standard — prose, no code.
- **Harness**: `agent = model + harness`; one agent, one loop, built by hand.
- **Factory**: a meta-harness running a line of agent processes → PR.
- **Orchestrator**: a meta-harness running a *tree* of agents in parallel —
  lead, workers, synthesizer — the general shape the factory line was one case of.

Non-deterministic models at the center — now N of them at once. Reliability is
what survived the filters you built around them: the bound, the isolation, the
merge.

> **Final checkpoint:** an orchestrator that takes a task, decomposes it into
> independent subtasks, runs them as isolated workers in parallel, survives a
> failing one, and synthesizes one summary — plus the deepagents shortcut that does
> the same in a dozen lines.

---

## Take-home

`take-home.md` — a real concurrency cap (not just `MAX_SUBTASKS`), merging N
worktrees into one PR, an aggregate cost/step budget across the fan-out,
dependent subtasks (a DAG, not a flat split), retrying just the failed workers,
and observability across parallel runs.
