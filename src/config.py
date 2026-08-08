"""Shared config: where the sandbox is, and which model runs each role.

WS4 is back on the LangChain stack WS2 used — langchain-anthropic for the
model binding, langgraph for the orchestration graph, deepagents for the
shortcut. So auth is an `ANTHROPIC_API_KEY` in the environment (see
.env.example), not the subscription-token path WS3's stock harnesses inherited.

Model per role: the LEAD that decides the split and the SYNTHESIZER that merges N
outputs exercise judgment (SMART); the WORKERS each do one mechanical subtask and
run CHEAP — and there are N of them at once, so cheap-per-worker is what keeps a
fan-out affordable.
"""

import os
from pathlib import Path

from langchain_anthropic import ChatAnthropic

SANDBOX = Path(__file__).resolve().parent / "sandbox"

CHEAP = os.environ.get("WORKER_MODEL", "claude-haiku-4-5-20251001")
SMART = os.environ.get("LEAD_MODEL", "claude-sonnet-5")


def chat(name: str) -> ChatAnthropic:
    """One place to build a model binding, so every role builds it the same way.

    No `temperature`: the current Claude models (Sonnet 5, etc.) reject it as a
    deprecated parameter, so we leave it at the model default.
    """
    return ChatAnthropic(model=name)
