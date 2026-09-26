"""paths and the small subprocess wrappers the scripts share."""

from __future__ import annotations

import subprocess
from pathlib import Path

EVAL = Path(__file__).resolve().parents[2]
ROOT = EVAL.parent
TASKS = EVAL / "tasks"
REPORT = EVAL / "report"


def sh(*cmd: str, check: bool = True, **kw) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(cmd), capture_output=True, text=True, check=check, **kw)


def git(d: Path, *args: str) -> str:
    return sh("git", *args, cwd=d).stdout
