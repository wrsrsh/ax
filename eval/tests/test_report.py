import csv
import json

import pytest

from ax_eval import report
from ax_eval.report import fallback_summary, render, verdict_metric, wilson
from ax_eval.table import COLUMNS, collect, load, usable

TASKS = ["hono-1", "hono-2", "hono-3", "hono-4"]
# setup -> (token scale vs A, resolved tasks)
PLAN = {"A": (1.0, {"hono-1", "hono-2"}), "B": (0.7, {"hono-1", "hono-2", "hono-3"}), "C": (1.0, {"hono-1", "hono-2"})}


def write_run(root, run_id, task, setup, rep, *, resolved=True, scale=1.0, grade=True, infra=False, ax=False):
    d = root / run_id
    d.mkdir(parents=True)
    base = 10_000 * (TASKS.index(task) + 1)
    (d / "manifest.json").write_text(json.dumps({
        "run_id": run_id, "task_id": task, "setup": setup, "rep": rep, "seed": rep, "agent": "codex",
        "codex_version": "0.156.0", "model": "gpt-6-astra", "effort": "medium", "ax_commit": "abc1234",
        "image": f"ax-eval/{task}", "started": "2026-09-26T10:00:00Z",
        "ended": f"2026-09-26T10:0{1 + rep}:00Z", "exit_code": 0, "timed_out": False,
        "infra_failure": infra, "infra_reason": "docker died" if infra else None,
    }))
    (d / "events.jsonl").write_text("")
    (d / "ax_log.jsonl").write_text("")
    (d / "final.diff").write_text("")
    if grade:
        (d / "grade.json").write_text(json.dumps({
            "resolved": resolved, "error": None, "f2p_passed": int(resolved), "f2p_total": 1,
            "p2p_passed": 3, "p2p_total": 3, "failing": [] if resolved else ["t > x"], "grade_seconds": 12.0,
        }))
    inp, out = int(base * scale), int(base * scale / 10)
    (d / "metrics.json").write_text(json.dumps({
        "input_tokens": inp, "cached_input_tokens": inp // 2, "uncached_input_tokens": inp - inp // 2,
        "output_tokens": out, "reasoning_tokens": out // 2, "tool_calls": int(10 * scale), "failed_commands": 0,
        "failed_patches": 0, "tools": {"ax read": 3, "cat": 1} if ax else {"cat": 3, "apply_patch": 1},
        "ax_calls": {"read": 3, "edit": 1} if ax else {}, "ax_outcomes": {"ok": 3, "stale": 1} if ax else {},
        "fallback_rate": 0.25 if ax else 1.0, "ax_rejections": 1 if ax else 0, "cost": inp / 1e6,
        "completed": True, "error": None,
    }))


@pytest.fixture
def fake(tmp_path, monkeypatch):
    # these tests pin the built-in fallback, not ax_eval.stats
    monkeypatch.setattr(report, "summary", lambda rows: (fallback_summary(rows), "built-in fallback"))
    runs = tmp_path / "runs"
    for setup, (scale, solved) in PLAN.items():
        for task in TASKS:
            for rep in (1, 2):
                write_run(runs, f"{task}-{setup}-{rep}", task, setup, rep, resolved=task in solved, scale=scale, ax=setup != "A")
    write_run(runs, "hono-1-B-3", "hono-1", "B", 3, infra=True, grade=False)
    write_run(runs, "hono-2-C-3", "hono-2", "C", 3, grade=False)
    tasks = tmp_path / "final.jsonl"
    tasks.write_text("".join(json.dumps({"id": t, "set": "dev" if t == "hono-1" else "heldout"}) + "\n" for t in TASKS + ["hono-9"]))
    return tmp_path, runs, tasks


def test_collect_rows_and_csvs(fake):
    root, runs, tasks = fake
    rows = collect(runs, root / "report", tasks)
    assert len(rows) == 26
    by = {r["run_id"]: r for r in rows}

    r = by["hono-2-B-1"]
    assert r["setup"] == "B" and r["task_id"] == "hono-2" and r["split"] == "heldout"
    assert r["tokens"] == 14_000 + 1_400 and r["turns"] == 7 and r["wall_seconds"] == 120.0
    assert r["resolved"] is True and r["complete"] and r["missing"] == []
    assert r["ax_calls_total"] == 4 and by["hono-1-A-1"]["split"] == "dev"

    assert not by["hono-2-C-3"]["complete"] and by["hono-2-C-3"]["missing"] == ["grade.json"]
    assert by["hono-1-B-3"]["infra_failure"] and not usable(by["hono-1-B-3"])
    assert sum(map(usable, rows)) == 24

    assert [json.loads(line)["run_id"] for line in (runs / "runs.jsonl").read_text().splitlines()] == sorted(by)
    assert load(runs) == json.loads(json.dumps(rows))

    with (runs / "runs.csv").open() as f:
        got = list(csv.DictReader(f))
    assert list(got[0]) == COLUMNS and len(got) == 26
    c = next(g for g in got if g["run_id"] == "hono-2-B-1")
    assert c["tokens"] == "15400" and json.loads(c["tools"]) == {"ax read": 3, "cat": 1}

    with (root / "report" / "per_task.csv").open() as f:
        pt = list(csv.DictReader(f))
    assert len(pt) == 12  # 4 tasks x 3 setups, incomplete/infra runs dropped
    b3 = next(p for p in pt if p["task_id"] == "hono-3" and p["setup"] == "B")
    assert b3["n"] == "2" and float(b3["resolved_rate"]) == 1.0 and float(b3["wall_seconds"]) == 150.0
    a3 = next(p for p in pt if p["task_id"] == "hono-3" and p["setup"] == "A")
    assert float(a3["resolved_rate"]) == 0.0 and float(a3["tokens"]) == 33_000


def test_missing_everything(tmp_path):
    (tmp_path / "runs" / "empty-run").mkdir(parents=True)
    rows = collect(tmp_path / "runs", tmp_path / "report", tmp_path / "nope.jsonl")
    assert rows[0]["run_id"] == "empty-run" and not rows[0]["complete"]
    assert rows[0]["missing"] == ["manifest.json", "grade.json", "metrics.json", "events.jsonl"]
    assert rows[0]["tokens"] is None


def test_report_renders(fake):
    root, runs, tasks = fake
    rows = collect(runs, root / "report", tasks)
    out = root / "report" / "REPORT.md"
    md = render(rows, runs, out, tasks)
    assert out.read_text() == md
    for h in ["# ax eval report", "## summary", "## guardrail", "## ratios vs A", "## adoption",
              "## wins and losses", "## verdict", "## limitations"]:
        assert h in md, h
    assert "codex 0.156.0" in md and "gpt-6-astra, effort medium" in md and "abc1234" in md
    assert "5 in final.jsonl (1 dev, 4 held-out); 4 with usable runs here" in md
    assert "26 total, 24 usable, 1 infra failures, 1 incomplete" in md
    assert "| A | 8 | 4 | 50.0% |" in md and "| B | 8 | 4 | 75.0% |" in md
    assert "| B/A | tokens | 0.70x |" in md and "| C/A | tokens | 1.00x |" in md
    assert "| B | 8 | 8 (100.0%) | 25.0% | 8 |" in md
    assert "tool-surface confound" in md and "single repo" in md and "single agent and model" in md
    assert "[A1](../runs/hono-3-A-1/events.jsonl)" in md and "[B2](../runs/hono-3-B-2/events.jsonl)" in md
    verdict = md.split("## verdict")[1].split("## limitations")[0]
    assert "tokens: helped" in verdict and "cost: helped" in verdict
    assert verdict.count("no measurable difference") >= 5  # every C metric + B pass rate
    assert "stats: built-in fallback." in md


def test_cli(fake, monkeypatch):
    root, runs, tasks = fake
    out = root / "report" / "REPORT.md"
    assert report.main(["--runs", str(runs), "--out", str(out), "--tasks", str(tasks)]) == 0
    assert "## verdict" in out.read_text() and (root / "report" / "per_task.csv").exists()


def test_helpers():
    lo, hi = wilson(5, 10)
    assert 0.23 < lo < 0.24 and 0.76 < hi < 0.77
    assert wilson(0, 0) is None
    assert verdict_metric({"median": 0.8, "ci": [0.7, 0.9]})[0] == "helped"
    assert verdict_metric({"median": 1.2, "ci": [1.1, 1.3]})[0] == "hurt"
    assert verdict_metric({"median": 1.0, "ci": [0.9, 1.1]})[0] == "no measurable difference"
    assert verdict_metric(None)[0] == "unknown"


def test_summary_uses_the_real_stats_module():
    rows = []
    for t in ("t1", "t2", "t3"):
        for setup, tok in (("A", 100), ("B", 70)):
            rows.append({"task_id": t, "setup": setup, "rep": 0, "resolved": True, "input_tokens": tok, "cached_input_tokens": 0,
                         "output_tokens": 0, "tokens": tok, "cost": tok / 100, "turns": 4, "wall_seconds": 8.0, "infra_failure": False})
    s, src = report.summary(rows)
    assert src == "ax_eval.stats.summary", src
    assert s["setups"]["B"]["pass_rate"] == 1.0 and s["setups"]["B"]["ci"] == (1.0, 1.0)
    assert abs(s["ratios"]["B/A"]["tokens"]["median"] - 0.7) < 1e-9
    assert s["guardrail"]["B"]["ok"] is True
    assert s["adoption"]["A"]["runs"] == 3