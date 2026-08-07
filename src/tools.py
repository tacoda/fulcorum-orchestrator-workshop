"""Sandbox-scoped tools, built per worker.

Same three tools as WS2 — a read, a write, a shell runner — but here they're
produced by a factory bound to a specific directory. Each parallel worker gets
its own worktree (worktree.py) and its own tools pointed at it, so N workers
editing at once never touch each other's files. Filesystem isolation is the
on-disk analog of the separate context window each worker already gets: two kinds
of "don't let the workers step on each other."
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from langchain_core.tools import tool


def make_tools(workdir: Path) -> list:
    """Return read/write/run tools scoped to `workdir` and nothing outside it."""
    workdir = workdir.resolve()

    def _safe(rel: str) -> Path:
        # deepagents addresses files from a "/" root, so treat a leading slash as
        # workdir-relative rather than absolute. The containment check below still
        # rejects any real traversal (`../`).
        p = (workdir / rel.lstrip("/")).resolve()
        if not str(p).startswith(str(workdir)):
            raise ValueError(f"path {rel!r} escapes the workdir")
        return p

    @tool
    def read_file(path: str) -> str:
        """Read a file in this worker's tree. `path` is relative to its root."""
        p = _safe(path)
        return p.read_text() if p.exists() else f"ERROR: {path} does not exist"

    @tool
    def write_file(path: str, content: str) -> str:
        """Write a file in this worker's tree, creating parent dirs. Overwrites."""
        p = _safe(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {len(content)} bytes to {path}"

    @tool
    def run_command(command: str) -> str:
        """Run a shell command in this worker's tree (`pytest`, `ls`, `git diff`).

        Combined stdout+stderr, truncated. Times out at 60s — a crude kill switch
        so a runaway command can't hang a worker.
        """
        try:
            r = subprocess.run(command, shell=True, cwd=workdir,
                               capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return "ERROR: command timed out after 60s"
        out = (r.stdout + r.stderr).strip()
        return out[:4000] if out else f"(no output, exit {r.returncode})"

    return [read_file, write_file, run_command]
