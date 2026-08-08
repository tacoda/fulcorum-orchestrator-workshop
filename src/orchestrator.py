"""The orchestrator, built by hand on LangGraph.

    task → decompose ─┬─► worker ─┐
                      ├─► worker ─┼─► synthesize → summary
                      └─► worker ─┘   (fan-in)
             (fan-out: one Send per subtask)

WS2 built a harness that manages TOOLS. WS3's factory ran a fixed LINE of agents
in sequence. An orchestrator manages multiple AGENTS that run at the SAME TIME: a
LEAD decides at runtime how the work splits, N WORKERS run that split in parallel
— each its own react agent, each isolated in its own worktree — and a SYNTHESIZER
merges what comes back. The factory is the N=1, fixed-order special case of this;
this is the general tree.

The fan-out is one LangGraph primitive: a conditional edge returns a list of
`Send` objects, and the runtime runs them concurrently, reducing each worker's
result into `results` via the `operator.add` reducer (that's the fan-in). The
hard parts aren't the Send — they're bounding N, isolating the workers, and
surviving the one that fails while its siblings succeed.
"""

from __future__ import annotations

import json
import operator
import os
import re
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from config import CHEAP, SMART, chat
from tools import make_tools
from worktree import isolated

load_dotenv()
MAX_SUBTASKS = int(os.environ.get("MAX_SUBTASKS", "5"))  # the lead can't spawn 500

LEAD = """You are the lead. Break the task into INDEPENDENT subtasks that can run
in parallel WITHOUT touching the same files. Each subtask must be self-contained.
Output ONLY a JSON array of objects: {"id": "<slug>", "title": "...", "prompt": "..."}.
No prose. `id` is a short slug of letters, digits, and hyphens."""

WORKER = """You are a worker. Do EXACTLY your one subtask, nothing more. Smallest
diff. Touch only the files your subtask names. Every behavior change ships with a
test. When done, reply with one sentence naming what you changed."""

SYNTH = """You are the synthesizer. Below are the reports from N workers that ran
in parallel. Produce ONE coherent summary: what shipped, what failed, and any
conflicts to resolve before merge. Be concrete; name files."""


class OrchestratorState(TypedDict):
    task: str
    subtasks: list[dict]
    results: Annotated[list[dict], operator.add]   # fan-in: workers append here
    summary: str


def _text(message) -> str:
    """Flatten a message's content to plain text.

    langchain-anthropic returns `content` as a list of content blocks, not a
    string, so pull the text out of each block.
    """
    c = message.content
    if isinstance(c, str):
        return c
    parts = []
    for b in c:
        if isinstance(b, dict):
            parts.append(b.get("text", ""))
        else:
            parts.append(getattr(b, "text", str(b)))
    return "".join(parts)


def _parse_subtasks(text: str) -> list[dict]:
    """Parse the lead's JSON. If it wrapped the array in prose, dig it out."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.S)
        data = json.loads(m.group(0)) if m else []
    return [t for t in data if isinstance(t, dict) and t.get("id") and t.get("prompt")]


def decompose(state: OrchestratorState) -> dict:
    """LEAD: turn one task into N independent subtasks (N decided at runtime)."""
    resp = chat(SMART).invoke(
        [SystemMessage(content=LEAD), HumanMessage(content=state["task"])]
    )
    return {"subtasks": _parse_subtasks(_text(resp))[:MAX_SUBTASKS]}


def assign_workers(state: OrchestratorState) -> list[Send]:
    """FAN-OUT: one Send per subtask; the runtime runs the workers concurrently."""
    return [Send("worker", {"subtask": st}) for st in state["subtasks"]]


def worker(state: dict) -> dict:
    """One WORKER: a react agent doing a single subtask in an isolated worktree.

    Wrapped so a worker that raises becomes an error result instead of killing the
    whole run — one worker's failure is not all workers' failure.
    """
    st = state["subtask"]
    title = st.get("title", st["id"])
    try:
        with isolated(st["id"]) as workdir:
            agent = create_agent(chat(CHEAP), make_tools(workdir), system_prompt=WORKER)
            out = agent.invoke({"messages": [HumanMessage(content=st["prompt"])]})
            report = _text(out["messages"][-1])
        return {"results": [{"id": st["id"], "title": title, "report": report, "ok": True}]}
    except Exception as e:
        return {"results": [{"id": st["id"], "title": title, "report": f"FAILED: {e}", "ok": False}]}


def synthesize(state: OrchestratorState) -> dict:
    """FAN-IN: merge N worker reports into one summary."""
    if not any(r["ok"] for r in state["results"]):
        return {"summary": "ESCALATE: every worker failed. Nothing to merge."}
    reports = "\n\n".join(
        f"[{r['id']}] {'ok' if r['ok'] else 'FAILED'} — {r['title']}\n{r['report']}"
        for r in state["results"]
    )
    resp = chat(SMART).invoke(
        [SystemMessage(content=SYNTH),
         HumanMessage(content=f"Task:\n{state['task']}\n\nReports:\n{reports}")]
    )
    return {"summary": _text(resp)}


def build_orchestrator():
    g = StateGraph(OrchestratorState)
    g.add_node("decompose", decompose)
    g.add_node("worker", worker)
    g.add_node("synthesize", synthesize)

    g.add_edge(START, "decompose")
    g.add_conditional_edges("decompose", assign_workers, ["worker"])  # fan-out
    g.add_edge("worker", "synthesize")                                # fan-in
    g.add_edge("synthesize", END)
    return g.compile()


def run(task: str) -> str:
    final = build_orchestrator().invoke({"task": task, "subtasks": [], "results": []})
    return final["summary"]


if __name__ == "__main__":
    import sys

    default = ("Write a pytest suite for the sandbox library: one test file per "
               "module (math_ops.py, str_ops.py, list_ops.py), covering every "
               "function and its edge cases — empty inputs, boundary values, and "
               "the errors each function raises. Do not modify the modules.")
    task = sys.argv[1] if len(sys.argv) > 1 else default
    print("\n=== ORCHESTRATOR SUMMARY ===\n" + run(task))
