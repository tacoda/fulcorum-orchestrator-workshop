# Workshop 4 — Take-Home: Make the Orchestrator Robust

The workshop orchestrator fans out to a handful of workers, isolates them, and
merges their reports. This is the gap to something that coordinates real parallel
work over a real repo. Concurrency makes every weakness happen N times at once.

## 1. A real concurrency cap (do this first)

`MAX_SUBTASKS` bounds *how many* subtasks exist; it does not bound how many run at
*once*. Ten cheap subtasks still means ten simultaneous agents — ten budgets, ten
API rate-limit slots. Cap concurrency separately with a semaphore around the
worker body, or run workers in bounded batches. `MAX_SUBTASKS` is the how-many
bound; this is the how-many-at-once bound. You want both.

## 2. Merge the worktrees into one PR

The workshop synthesizes *reports*; the actual diffs live in N worktrees that get
discarded. The real payoff is one branch. Have each worker commit in its worktree,
then merge the branches (`git merge` / cherry-pick, or `git worktree` → a shared
integration branch) and open one PR — reusing WS3's guarded `open_pr`. Conflicts
are the honest hard part: if two workers touched the same lines, the "independent
subtasks" contract was violated, and the merge is where you find out. This is
where an orchestrator earns the "independence" it asked the lead for.

## 3. Aggregate cost + step budget across the fan-out

WS2 capped one agent; WS3 capped a line; here cap the *tree*. N parallel workers
spend N times as fast, so the aggregate budget matters more, not less. Sum tokens
(or turns) across every worker, and abort the fan-out to escalate when a per-run
budget is exceeded. LangChain surfaces usage on the response metadata; thread a
shared counter through the workers or read it off the final state.

## 4. Dependent subtasks: a DAG, not a flat split

The workshop assumes every subtask is independent. Real work has ordering: "add
the model" before "wire the endpoint that uses it." Let the lead emit a small DAG
(subtasks with `depends_on`), and run each layer as its own fan-out — parallel
within a layer, sequential across layers. This is the honest generalization of the
factory line and the flat fan-out: the line is a DAG of width 1, the fan-out is a
DAG of depth 1, and most real work is somewhere in between.

## 5. Retry just the failed workers

Right now a failed worker returns `ok: False` and the run moves on. Better: feed
the failure back and retry *only* the workers that failed — the successful ones are
done, so re-running them is wasted spend. This is WS2's bounded-retry lever and
WS3's feed-the-rejection-back lever, applied per worker instead of per run. Bound
the per-worker retries too, or a stuck subtask spins forever.

## 6. Observability across parallel runs

Sequential logs read top to bottom; parallel logs interleave into noise. Tag every
log line and every result with its worker `id` and a run id, so a failed fan-out is
a timeline per worker, not a scramble. Capture per-worker cost, turns, and
terminal reason. When five workers run at once, "it broke" is useless — you need
"worker `str-ops` broke at attempt 2, out-of-scope edit to `math_ops.py`."

## 7. Harden the decompose — a bad split is the root cause

The lead's split is load-bearing: overlapping subtasks cause the merge conflicts in
#2, and a subtask that's too big makes a worker time out. Give the lead teeth —
validate the split before fanning out (reject overlapping file scopes
mechanically), and reject a split with zero or too-many subtasks. A line is as safe
as its weakest gate; an orchestrator is as safe as its decomposition.

## The series, done

You've gone from a prose charter to four layers of machine: a harness around one
model, a factory that runs a line of agents into a PR, and an orchestrator that
runs a tree of agents in parallel — non-deterministic models at the center of
every layer and reliability engineered around them. Input narrowed at decompose,
output merged at synthesize, recovery bounded per worker and per run, and the fan-
out capped before anything else. That's harness engineering: reliable workflows
around non-deterministic agents — however many of them run at once.
