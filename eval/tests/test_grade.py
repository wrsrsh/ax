import json
import shutil
import subprocess

import pytest

from ax_eval.grade import grade, patch_paths, summarize
from ax_eval.mine import TASKS
from ax_eval.parity import EVAL

TEST_PATCH = """diff --git a/src/a.test.ts b/src/a.test.ts
--- a/src/a.test.ts
+++ b/src/a.test.ts
@@ -1 +1,2 @@
 x
+y
diff --git a/src/new.test.ts b/src/new.test.ts
new file mode 100644
--- /dev/null
+++ b/src/new.test.ts
@@ -0,0 +1 @@
+z
"""


def test_patch_paths():
    assert patch_paths(TEST_PATCH) == ["src/a.test.ts", "src/new.test.ts"]


def test_summarize():
    task = {"id": "t", "fail_to_pass": ["a", "b"], "pass_to_pass": ["c"]}
    r = summarize(task, {"a": "passed", "b": "passed", "c": "passed"}, 1.23)
    assert r["resolved"] and r["f2p_passed"] == 2 and r["grade_seconds"] == 1.2
    r = summarize(task, {"a": "passed", "c": "failed"}, 0)
    assert not r["resolved"] and r["failing"] == ["b", "c"] and r["p2p_passed"] == 0
    r = summarize(task, "agent diff doesn't apply", 0)
    assert not r["resolved"] and r["error"] == "agent diff doesn't apply"


def _tasks(n):
    f = TASKS / "tasks.jsonl"
    return [json.loads(l) for l in f.open()][:n] if f.exists() else []


def vandal_diff(task: dict, tmp) -> str:
    """what a cheating agent would hand in: the gold fix plus a gutted test file."""
    repo = EVAL / ".cache" / "hono-full"
    wt = tmp / "wt"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(wt), task["base"]], check=True)
    try:
        subprocess.run(["git", "-C", str(wt), "apply"], input=task["gold_patch"], text=True, check=True)
        target = wt / task["test_run_files"][0]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("// all tests deleted\n")
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
        return subprocess.run(["git", "-C", str(wt), "diff", "--cached"], capture_output=True, text=True, check=True).stdout
    finally:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], check=False)


@pytest.mark.skipif(not shutil.which("docker") or not _tasks(1), reason="needs docker + validated tasks")
@pytest.mark.parametrize("task", _tasks(2), ids=lambda t: t["id"])
def test_grade_real_task(task, tmp_path):
    gold = grade(task, task["gold_patch"])
    assert gold["resolved"], gold
    assert not grade(task, "")["resolved"]
    broken = grade(task, task["gold_patch"].replace("\n+", "\n+ ) this is not code (", 1))
    assert not broken["resolved"]
    vandal = grade(task, vandal_diff(task, tmp_path))
    assert vandal["resolved"], vandal
