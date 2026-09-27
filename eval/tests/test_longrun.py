import json
import shutil

import pytest

from ax_eval import longrun
from ax_eval.images import image_labels
from ax_eval.longrun import (
    FILLER, added_norms, chain_task, fake_chain_steps, hunks, insert_filler, jolt_file, locate, norm, per_step_usage,
    run_batch, step_cmd, summarize, target_check, touched_prior,
)
from ax_eval.runner import est_from_ledger, read_ledger

SRC = """import { a } from './a'

/**
 * adds
 */
export const add = (x: number, y: number) => {
  const z = x + y
  return z
}

export function sub(x: number, y: number) {
  return x - y
}
"""

DIFF = """diff --git a/src/m.ts b/src/m.ts
index 1..2 100644
--- a/src/m.ts
+++ b/src/m.ts
@@ -7,2 +7,2 @@ export const add = (x: number, y: number) => {
-  const z = x + y
-  return z
+  const z = x + y + 0
+  return z
@@ -12,0 +13 @@ export function sub(x: number, y: number) {
+  // done
diff --git a/src/new.ts b/src/new.ts
new file mode 100644
--- /dev/null
+++ b/src/new.ts
@@ -0,0 +1,2 @@
+export const n = 1
+export const m = 2
"""


def test_hunks():
    hs = hunks(DIFF)
    assert [(h["path"], h["old_start"], h["old_len"], h["new_start"], h["new_len"]) for h in hs] == [
        ("src/m.ts", 7, 2, 7, 2), ("src/m.ts", 12, 0, 13, 1), ("src/new.ts", 0, 0, 1, 2)]
    assert hs[0]["removed"] == ["  const z = x + y", "  return z"] and hs[1]["added"] == ["  // done"]
    assert hs[2]["old"] == []
    # a removed line that looks like a file header stays a removed line
    tricky = "diff --git a/src/x.ts b/src/x.ts\n--- a/src/x.ts\n+++ b/src/x.ts\n@@ -1,2 +1,1 @@\n--- not a header\n keep\n"
    assert hunks(tricky)[0]["removed"] == ["-- not a header"]


def test_locate_survives_a_reformat():
    assert locate(["  const z = x + y", "  return z"], SRC) == (7, 8)
    wrapped = SRC.replace("export const add = (x: number, y: number) => {", "export const add = (\n  x: number,\n  y: number,\n) => {")
    assert locate(["export const add = (x: number, y: number) => {", "  const z = x + y"], wrapped) == (6, 10)
    assert locate(["nothing like this here at all"], SRC) is None
    assert norm("  foo(a, b);  // x") == "fooabx"


def test_target_check():
    gold = "--- a/src/m.ts\n+++ b/src/m.ts\n@@ -11,3 +11,3 @@\n export function sub(x: number, y: number) {\n-  return x - y\n+  return y - x\n }\n"
    pre = {"src/m.ts": SRC}
    near = "--- a/src/m.ts\n+++ b/src/m.ts\n@@ -12,1 +12,1 @@\n-  return x - y\n+  return -(x - y)\n"
    assert target_check(near, gold, pre) == {"agent_hunks": 1, "on_target": 1, "off_target": 0, "unlocated": 0}
    far = "--- a/src/m.ts\n+++ b/src/m.ts\n@@ -40,0 +41,1 @@\n+// far away\n--- a/src/other.ts\n+++ b/src/other.ts\n@@ -1,0 +2,1 @@\n+x\n"
    assert target_check(far, gold, pre, slack=5) == {"agent_hunks": 2, "on_target": 0, "off_target": 2, "unlocated": 0}
    lost = target_check(near, gold, {"src/m.ts": "totally different\n"})
    assert lost["unlocated"] == 1
    filler = "--- a/src/m.ts\n+++ b/src/m.ts\n@@ -0,0 +1,3 @@\n" + "".join(f"+{l}\n" for l in FILLER)
    assert target_check(filler, gold, pre)["agent_hunks"] == 0
    tests_only = "--- a/src/m.test.ts\n+++ b/src/m.test.ts\n@@ -1,0 +2,1 @@\n+it()\n"
    assert target_check(tests_only, gold, pre)["agent_hunks"] == 0


def test_touched_prior():
    step1 = "--- a/src/m.ts\n+++ b/src/m.ts\n@@ -3,0 +4,1 @@\n+  const cached = lookup(key)\n"
    prior = added_norms(step1)
    assert prior == {"constcachedlookupkey"}
    step2 = "--- a/src/m.ts\n+++ b/src/m.ts\n@@ -4,1 +4,1 @@\n-  const  cached = lookup( key );\n+  const cached = find(key)\n"
    assert touched_prior(step2, prior) == 1
    assert touched_prior(step2, set()) == 0


def test_insert_filler():
    out = insert_filler(SRC, [8]).split("\n")
    assert out[:3] == FILLER
    i = out.index("/**")
    # above the declaration holding line 8, doc comment kept on its declaration
    assert out[i - 3 : i] == FILLER and out[i + 3].startswith("export const add")
    body = out[out.index("export const add = (x: number, y: number) => {") + 1 : out.index("}")]
    assert not set(FILLER) & set(body)
    mid = insert_filler(SRC, []).split("\n")
    assert mid.count(FILLER[1]) == 2 and len(mid) == len(SRC.split("\n")) + 6
    assert insert_filler("", []).split("\n")[:3] == FILLER


def test_fake_chain_steps():
    ts = [{"src_files": ["src/a.ts"]}, {"src_files": ["src/b.ts"]}]
    b = fake_chain_steps(ts, "B")
    assert [s.split(":")[0] for s in b] == ["sh", "sh", "msg", "sh", "sh", "sh", "msg"]
    assert b[0].startswith("sh:ax read src/a.ts") and "ax edit src/a.ts" in b[4] and "/tmp/.fake-read-0" in b[4]
    a = fake_chain_steps(ts, "A")
    assert "ax " not in " ".join(a) and "sed -i '3a" in a[4] and a[4].endswith("src/a.ts")


def test_per_step_usage():
    def row(i, o):
        return {"input_tokens": i, "cached_input_tokens": i // 2, "cache_write_input_tokens": 0, "uncached_input_tokens": i - i // 2,
                "output_tokens": o, "reasoning_tokens": 0}

    prices = {"input": 1e6, "cached_input": 0, "cache_write": 0, "output": 0}
    out = per_step_usage([row(100, 10), row(300, 30), row(50, 5)], prices)
    assert [r["input_tokens"] for r in out] == [100, 200, 50]  # the third isn't cumulative, left as is
    assert [r["thread_input_tokens"] for r in out] == [100, 300, 50]
    assert out[1]["output_tokens"] == 20 and out[1]["cost"] == pytest.approx(100)


def test_jolt_file():
    files = ["src/a.ts", "src/b.ts"]
    it = {"type": "command_execution", "command": "/bin/bash -lc 'ax read src/b.ts:1-40'", "exit_code": 0}
    assert jolt_file(it, files) == "src/b.ts"
    assert jolt_file({**it, "command": "sed -n 1,20p src/a.ts"}, files) == "src/a.ts"
    assert jolt_file({**it, "exit_code": 1}, files) is None
    assert jolt_file({**it, "command": "npx vitest src/a.ts"}, files) is None
    assert jolt_file({"type": "file_change"}, files) is None


def test_chain_task():
    t = {"id": "t", "base": "own", "fail_to_pass": ["x"], "pass_to_pass": ["y"]}
    step = {"fail_to_pass": ["f"], "pass_to_pass": ["p"]}
    assert chain_task(t, step, "anc") == {"id": "t", "base": "anc", "fail_to_pass": ["f"], "pass_to_pass": ["p"]}
    assert chain_task(t, step, "anc", ["f", "p"])["fail_to_pass"] == ["f", "p"]


def test_step_cmd():
    t = {"src_files": ["src/a.ts"], "instruction": "fix it"}
    cmd, stdin = step_cmd("stub", "B", "box", t, None, "K", "m", "medium", ["timeout", "9"])
    assert "STUB_FILE=src/a.ts" in cmd and stdin == ""
    first, stdin = step_cmd("codex", "B", "box", t, None, "K", "m", "medium", [])
    assert first[first.index("codex") + 1] == "exec" and "resume" not in first and stdin == "fix it"
    assert "--ephemeral" not in first and "--json" in first and first[-1] == "-"
    again, _ = step_cmd("codex", "B", "box", t, "th-1", "K", "m", "medium", [])
    i = again.index("resume")
    assert again[i + 1] == "th-1" and "-C" not in again and "--ephemeral" not in again and again[again.index("-w") + 1] == "/w"


CHAINS = {"c0": {"id": "c0", "tasks": ["t0", "t1"]}, "c1": {"id": "c1", "tasks": ["t2", "t3", "t4"]}}


def fake_chain(outcomes, cost=1.0):
    it = iter(outcomes)

    def fn(chain, tasks, setup, run_id, out_dir, **kw):
        out_dir.mkdir(parents=True)
        infra = next(it)
        steps = [{"step": k, "task": t, "resolved": not infra, "cost": cost} for k, t in enumerate(chain["tasks"])]
        return {"run_id": run_id, "chain": chain["id"], "setup": setup, "agent": kw.get("agent"), "model": "m", "steps": steps[:1] if infra else steps,
                "infra_failure": infra, "infra_reason": "api: 503" if infra else None, "cost": cost * len(steps), "started": "s", "ended": "e"}

    return fn


def test_batch_ledger_rows_per_step_and_retries(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    res = run_batch([("c1", "B", 0)], CHAINS, {}, runs_dir=tmp_path, ledger=ledger, run_fn=fake_chain([True, False]), log=lambda *_: None)
    assert not res[0]["infra_failure"] and res[0]["attempt"] == 2
    rows = read_ledger(ledger)
    assert [(r["chain"], r["step"], r["infra_failure"]) for r in rows] == [("c1", 0, True), ("c1", 0, False), ("c1", 1, False), ("c1", 2, False)]
    assert all(r["dry"] for r in rows)
    first = json.loads((tmp_path / rows[0]["run_id"] / "manifest.json").read_text())
    assert first["retried_as"] == res[0]["run_id"]


def test_batch_budget_counts_whole_chains(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps({"agent": "codex", "cost": 95.0, "dry": False}) + "\n")
    log = []
    res = run_batch([("c1", "B", 0)], CHAINS, {}, runs_dir=tmp_path, ledger=ledger, budget=100.0, est=2.0, dry=False,
                    run_fn=fake_chain([False]), log=log.append)
    assert "refused" in res[0] and "est $6.00" in log[0]  # 95 + 2 x 3 steps > 100
    res = run_batch([("c0", "B", 0)], {"c0": CHAINS["c0"]}, {}, runs_dir=tmp_path, ledger=ledger, budget=100.0, est=2.0, dry=False,
                    agent="codex", run_fn=fake_chain([False]), log=lambda *_: None)
    assert "refused" not in res[0]
    rows = read_ledger(ledger)
    assert est_from_ledger(rows, chains=True) == pytest.approx(1.0) and est_from_ledger(rows) == pytest.approx(95.0)


def test_summarize(tmp_path):
    for i, (setup, res) in enumerate([("A", [True, False]), ("B", [True, True]), ("B", [False, True])]):
        d = tmp_path / f"r{i}"
        d.mkdir()
        steps = [{"step": k, "resolved": r, "regressed": False, "stale": k, "relocated": 1, "failed_patches": 0, "off_target": 0,
                  "wrong_place": False, "touched_prior_lines": 0, "cost": 0.5, "input_tokens": 1000} for k, r in enumerate(res)]
        (d / "manifest.json").write_text(json.dumps({"setup": setup, "agent": "codex", "dry": False, "infra_failure": False, "steps": steps}))
    rows = {(r["setup"], r["step"]): r for r in summarize(tmp_path) if not r["jolt"]}
    assert rows[("B", 0)]["n"] == 2 and rows[("B", 0)]["pass_rate"] == 0.5 and rows[("B", 1)]["stale"] == 2
    assert rows[("A", 1)]["pass_rate"] == 0.0
    assert summarize(tmp_path, include_dry=True) == summarize(tmp_path)


def test_cli_plan_only_and_paid_gate(capsys, tmp_path):
    f = tmp_path / "chains.jsonl"
    f.write_text("".join(json.dumps({**c, "validated": True}) + "\n" for c in CHAINS.values()))
    assert longrun.main(["--chains-file", str(f), "--plan-only", "--est", "1", "--repeats", "2"]) == 0
    out = capsys.readouterr()
    assert len(out.out.splitlines()) == 2 * 2 * 2 and "8 chain runs, 20 steps, ~$20" in out.err
    with pytest.raises(SystemExit):
        longrun.main(["--chains-file", str(f), "--agent", "codex", "--runs-dir", str(tmp_path / "r")])
    assert "--paid" in capsys.readouterr().err
    f.write_text(json.dumps({**CHAINS["c0"], "validated": False}) + "\n")
    with pytest.raises(SystemExit):
        longrun.main(["--chains-file", str(f), "--plan-only"])


def _chain_with_image():
    if not shutil.which("docker") or not longrun.CHAINS.exists():
        return None
    return next((c for c in longrun.load_chains(["all"]) if c["validated"] and image_labels(c["image"]) is not None), None)


CHAIN = _chain_with_image()
needs_docker = pytest.mark.skipif(CHAIN is None, reason="needs docker, tasks/chains.jsonl and a built task image")


@pytest.mark.docker
@needs_docker
@pytest.mark.parametrize("setup", ["A", "B"])
def test_stub_chain_end_to_end(setup, tmp_path):
    tasks = {t["id"]: t for t in longrun.jsonl(longrun.TASKS / "final.jsonl")}
    zero = {"input": 0, "cached_input": 0, "output": 0}
    m = longrun.run_chain(CHAIN, tasks, setup, f"test-{setup}", tmp_path / "run", agent="stub", prices=zero)
    assert not m["infra_failure"], m["infra_reason"]
    n = len(CHAIN["tasks"])
    assert [s["task"] for s in m["steps"]] == CHAIN["tasks"] and m["thread_id"] == "stub"
    for k in range(n):
        d = tmp_path / "run" / f"step{k}"
        for f in ("events.jsonl", "ax_log.jsonl", "final.diff", "delta.diff", "grade.json", "metrics.json"):
            assert (d / f).exists(), (k, f)
        g = json.loads((d / "grade.json").read_text())
        assert g["error"] is None and not g["resolved"]
        assert "AGENTS.md" not in (d / "final.diff").read_text()
        assert (d / "world.json").exists() == (k < n - 1)
    w = json.loads((tmp_path / "run" / "step0" / "world.json").read_text())
    assert w["kind"] in ("insert", "fmt", "upstream") and w["lines_changed"] > 0 and w["files"]
    last = (tmp_path / "run" / f"step{n - 1}" / "final.diff").read_text()
    assert last.count("+// ax-eval stub") == n  # every step's edit is still there
    # the world change is in the cumulative diff but not in the next step's own delta
    assert "ax-eval stub" in (tmp_path / "run" / "step1" / "delta.diff").read_text()
    s0 = m["steps"][0]
    assert s0["agent_hunks"] == 1 and s0["final_resolved"] is False and not s0["regressed"]
    assert "FAIL" not in (tmp_path / "run" / "probe.log").read_text()
    assert not list((tmp_path / "run").glob("box"))


def _chain_with(kind):
    if CHAIN is None:
        return None
    return next((c for c in longrun.load_chains(["all"]) if c["validated"] and c["world_changes"][0]["kind"] == kind
                 and image_labels(c["image"]) is not None), None)


@pytest.mark.docker
@needs_docker
@pytest.mark.parametrize("kind", ["fmt", "upstream"])
def test_world_change_end_to_end(kind, tmp_path):
    chain = _chain_with(kind)
    if chain is None:
        pytest.skip(f"no chain starting with {kind}")
    tasks = {t["id"]: t for t in longrun.jsonl(longrun.TASKS / "final.jsonl")}
    m = longrun.run_chain(chain, tasks, "A", f"test-{kind}", tmp_path / "run", agent="stub", prices={"input": 0, "cached_input": 0, "output": 0})
    assert not m["infra_failure"], m["infra_reason"]
    w = json.loads((tmp_path / "run" / "step0" / "world.json").read_text())
    assert w["planned"] == kind and w["lines_changed"] > 0
    assert w["kind"] == kind or w["note"]  # an upstream diff that conflicts falls back to insert, and says so
    g = json.loads((tmp_path / "run" / "step1" / "grade.json").read_text())
    assert g["error"] is None and g["p2p_passed"] == g["p2p_total"]  # the world change didn't break anything


@pytest.mark.docker
@needs_docker
def test_codex_chain_against_fake_api(tmp_path):
    tasks = {t["id"]: t for t in longrun.jsonl(longrun.TASKS / "final.jsonl")}
    zero = {"input": 0, "cached_input": 0, "output": 0}
    m = longrun.with_fake_api()(CHAIN, tasks, "B", "test-fake", tmp_path / "run", agent="codex", prices=zero, time_cap_s=180)
    assert not m["infra_failure"], m["infra_reason"]
    assert m["thread_id"] and m["thread_id"] != "stub"
    s0, s1 = m["steps"][:2]
    # usage per step, not per thread: step 0 is 3 fake responses, step 1 is 4 (1200 input each)
    assert s0["input_tokens"] == 3600 and s1["input_tokens"] == 4800
    # the edit made from step 0's read, after the world changed: ax relocated or refused it
    assert s1["relocated"] + s1["stale"] + s1["ambiguous"] >= 1
    mt = json.loads((tmp_path / "run" / "step1" / "metrics.json").read_text())
    assert mt["thread_input_tokens"] == 8400
