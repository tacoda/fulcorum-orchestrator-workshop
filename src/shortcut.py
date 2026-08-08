"""The shortcut: the same orchestrator in a dozen lines, with deepagents.

WS2 ended by showing deepagents collapse a hand-built harness into one call. Same
move here. `create_deep_agent` gives you a LEAD with a built-in planning tool and
a `task` tool that delegates to SUBAGENTS — which is exactly the orchestrator
pattern. You describe the worker subagent once; the lead decides at runtime how
many times to call it and fans the work out itself.

What you gain: almost no orchestration code. What you give up (the "what it costs"
half): the fan-out, the worktree isolation, and the per-worker failure handling
are now inside the library, not in front of you — here every subagent shares one
sandbox. orchestrator.py is where you SEE the mechanism; this is where you USE it
once you trust it. Pick per how much of the machine you need in your hands.
"""

from __future__ import annotations

from deepagents import create_deep_agent
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from config import CHEAP, SANDBOX, SMART, chat
from tools import make_tools

load_dotenv()

tools = make_tools(SANDBOX)   # one shared sandbox — no per-worker isolation here

worker_subagent = {
    "name": "worker",
    "description": "Do one independent subtask: edit its files and write its test. "
                   "Give it one subtask at a time.",
    "model": f"anthropic:{CHEAP}",
    "system_prompt": ("Do exactly the one subtask you're given. Smallest diff, only "
                      "in-scope files, ship a test. Report what you changed."),
    "tools": tools,
}

LEAD = ("Break the task into independent subtasks and delegate each to the `worker` "
        "subagent with the task tool. Then summarize what shipped and what failed.")


def build_agent():
    return create_deep_agent(model=chat(SMART), tools=tools,
                             system_prompt=LEAD, subagents=[worker_subagent])


def run(task: str) -> str:
    out = build_agent().invoke({"messages": [HumanMessage(content=task)]})
    return out["messages"][-1].content


if __name__ == "__main__":
    import sys

    default = ("Write a pytest suite covering every function and its edge cases in "
               "math_ops.py, str_ops.py, and list_ops.py — one test file per module.")
    print(run(sys.argv[1] if len(sys.argv) > 1 else default))
