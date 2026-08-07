"""Filesystem isolation for parallel workers: one git worktree each.

Context isolation has a filesystem analog. Two workers editing the same directory
at once race — one's Write clobbers the other's. A git worktree gives each worker
its own checked-out copy that shares history but not working files, so N workers
run in parallel without contention. This is the concrete answer to "N processes
hitting the same sandbox" — the hazard WS3's take-home flagged and this workshop
makes central.

The lock is the second half of that answer: git serializes on the repo's index,
so two concurrent `worktree add`s can collide on `.git`. The lock is held only
for the fast plumbing, never during the worker's model calls — so creation is
serialized while the actual work still runs in parallel.
"""

from __future__ import annotations

import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path

from config import SANDBOX

WORKTREES = SANDBOX.parent / "worktrees"
_lock = threading.Lock()


def _git(*args: str) -> None:
    with _lock:
        r = subprocess.run(["git", *args], cwd=SANDBOX,
                           capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{r.stdout}{r.stderr}")


@contextmanager
def isolated(worker_id: str):
    """Yield a fresh worktree for one worker; remove it (and its branch) on exit."""
    path = WORKTREES / worker_id
    branch = f"work/{worker_id}"
    _git("worktree", "add", "-b", branch, str(path), "HEAD")
    try:
        yield path
    finally:
        _git("worktree", "remove", "--force", str(path))
        _git("branch", "-D", branch)
