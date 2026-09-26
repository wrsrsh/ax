"""grade one run: the agent's diff + the hidden tests, in a fresh container.

hidden tests always win: after the agent's diff is applied, every file the
hidden test patch touches is put back to base (or removed if it's new) and
only then is the test patch applied, so an agent can't pass by editing tests.

    uv run python -m ax_eval.grade --task hono-4987 --diff final.diff
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from ax_eval.util import TASKS
from ax_eval.validate import run_tests


def patch_paths(patch: str) -> list[str]:
    """files a unified diff touches, both sides."""
    paths = set(re.findall(r"^(?:---|\+\+\+) (?:[ab]/)?(\S+)", patch, re.M))
    return sorted(paths - {"/dev/null"})


def load_task(task_id: str) -> dict:
    for name in ("final.jsonl", "tasks.jsonl"):
        f = TASKS / name
        if f.exists():
            for line in f.open():
                t = json.loads(line)
                if t["id"] == task_id:
                    return t
    raise SystemExit(f"no task {task_id}")


def summarize(task: dict, results: dict[str, str] | str, seconds: float) -> dict:
    f2p, p2p = task["fail_to_pass"], task["pass_to_pass"]
    if isinstance(results, str):
        return {
            "task": task["id"], "resolved": False, "error": results,
            "f2p_passed": 0, "f2p_total": len(f2p), "p2p_passed": 0, "p2p_total": len(p2p),
            "failing": [], "grade_seconds": round(seconds, 1),
        }
    passed = {t for t, status in results.items() if status == "passed"}
    failing = [t for t in f2p + p2p if t not in passed]
    return {
        "task": task["id"],
        "resolved": not failing,
        "error": None,
        "f2p_passed": sum(t in passed for t in f2p),
        "f2p_total": len(f2p),
        "p2p_passed": sum(t in passed for t in p2p),
        "p2p_total": len(p2p),
        "failing": failing[:20],
        "grade_seconds": round(seconds, 1),
    }


def grade(task: dict, diff: str) -> dict:
    t0 = time.time()
    patches = {"2-tests": task["test_patch"]}
    if diff.strip():
        patches["1-agent"] = diff
    results = run_tests(
        task["image"], task["base"], patches, task["test_run_files"], reset=(patch_paths(task["test_patch"]), "2-tests")
    )
    if isinstance(results, str) and "1-agent" in results:
        results = "agent diff doesn't apply"
    return summarize(task, results, time.time() - t0)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task", required=True)
    p.add_argument("--diff", type=Path, required=True)
    a = p.parse_args(argv)
    r = grade(load_task(a.task), a.diff.read_text())
    json.dump(r, sys.stdout)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
