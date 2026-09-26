import json
import random

from ax_eval import stats
from ax_eval.stats import (
    adoption,
    guardrail,
    main,
    median_ratio,
    pass_rate,
    pass_rate_diff,
    per_task_ratio,
    ratio_report,
    summary,
    wins_losses,
)

B = 2000  # fewer resamples keeps tests fast; the code path is the same


def row(task, setup, rep=0, resolved=True, tokens=1000, cost=1.0, turns=10, wall=60.0, **kw):
    return {"task_id": task, "setup": setup, "rep": rep, "resolved": resolved,
            "input_tokens": tokens, "cached_input_tokens": tokens // 2, "output_tokens": tokens // 10,
            "cost": cost, "turns": turns, "wall_seconds": wall, "infra_failure": False, **kw}


def better_b(n=60, reps=3):
    rows = []
    for t in range(n):
        for r in range(reps):
            rows.append(row(f"t{t}", "A", r, resolved=t % 3 == 0, cost=2.0 + t, tokens=2000 + 10 * t))
            rows.append(row(f"t{t}", "B", r, resolved=t % 3 in (0, 1), cost=(2.0 + t) / 2, tokens=1000 + 5 * t))
    return rows


def test_strictly_better_setup_shows_up():
    rows = better_b()
    a, b = pass_rate(rows, "A", B), pass_rate(rows, "B", B)
    assert abs(a[0] - 1 / 3) < 1e-9 and abs(b[0] - 2 / 3) < 1e-9
    d, lo, hi = pass_rate_diff(rows, "A", "B", B)
    assert abs(d - 1 / 3) < 1e-9 and lo > 0
    g = guardrail(rows, n_boot=B)
    assert g["verdict"] == "B not worse than A: CI excludes negative" and g["n_tasks"] == 60
    med, lo, hi = median_ratio(rows, "cost", "B", "A", B)
    assert med == 0.5 and hi < 1
    med, _, hi = median_ratio(rows, "tokens", "B", "A", B)
    assert abs(med - 0.5) < 1e-3 and hi < 1


def test_worse_setup_flagged():
    rows = [dict(r, setup={"A": "B", "B": "A"}[r["setup"]]) for r in better_b()]
    assert guardrail(rows, n_boot=B)["verdict"] == "B worse"


def test_identical_setups_ratio_one():
    rng = random.Random(1)
    rows = []
    for t in range(30):
        for r in range(3):
            base = row(f"t{t}", "A", r, resolved=rng.random() < 0.5, cost=rng.uniform(0.1, 5), turns=rng.randint(1, 40))
            rows += [base, dict(base, setup="B")]
    for m in stats.METRICS:
        assert all(x == 1.0 for _, x in per_task_ratio(rows, m, "B", "A"))
        med, lo, hi = median_ratio(rows, m, "B", "A", B)
        assert med == lo == hi == 1.0
    assert pass_rate_diff(rows, "A", "B", B) == (0.0, 0.0, 0.0)


def test_same_distribution_ci_contains_one():
    rng = random.Random(7)
    rows = []
    for t in range(40):
        size = rng.uniform(1, 10)  # task difficulty shared by both setups
        for s in "AB":
            for r in range(3):
                rows.append(row(f"t{t}", s, r, resolved=rng.random() < 0.6, cost=size * rng.uniform(0.8, 1.2)))
    _, lo, hi = median_ratio(rows, "cost", "B", "A", B)
    assert lo < 1 < hi
    _, lo, hi = pass_rate_diff(rows, "A", "B", B)
    assert lo < 0 < hi
    assert guardrail(rows, n_boot=B)["verdict"] == "inconclusive"


def test_small_n_wide_ci():
    def rows_for(n):
        return [row(f"t{t}", "A", r, resolved=t % 2 == 0) for t in range(n) for r in range(3)]

    _, lo_s, hi_s = pass_rate(rows_for(4), "A", B)
    _, lo_l, hi_l = pass_rate(rows_for(200), "A", B)
    assert hi_s - lo_s > 0.5
    assert hi_l - lo_l < 0.2
    assert lo_s <= 0.5 <= hi_s and lo_l <= 0.5 <= hi_l


def test_reps_dont_shrink_task_ci():
    one = [row(f"t{t}", "A", 0, resolved=t % 2 == 0) for t in range(10)]
    ten = [row(f"t{t}", "A", r, resolved=t % 2 == 0) for t in range(10) for r in range(10)]
    assert pass_rate(one, "A", B) == pass_rate(ten, "A", B)


def test_infra_failures_excluded():
    rows = better_b(n=9)
    junk = [row("t1", "A", 9, resolved=True, cost=1e6, infra_failure=True),
            row("ghost", "A", 0, resolved=True, infra_failure=True),
            row("ghost", "B", 0, resolved=False, infra_failure=True)]
    for f in (lambda r: pass_rate(r, "A", B), lambda r: pass_rate_diff(r, "A", "B", B),
              lambda r: per_task_ratio(r, "cost", "B", "A"), lambda r: adoption(r, "A")):
        assert f(rows) == f(rows + junk)
    s = summary(rows + junk, n_boot=B)
    assert s["n_infra_excluded"] == 3 and s["tasks"]["A"] == 9


def test_task_with_one_setup_skipped_and_counted():
    rows = better_b(n=6) + [row("solo", "A", 0, cost=100.0), row("solo", "A", 1, cost=100.0)]
    assert "solo" not in dict(per_task_ratio(rows, "cost", "B", "A"))
    rep = ratio_report(rows, "cost", "B", "A", B)
    assert rep["n_tasks"] == 6 and rep["skipped"] == {"missing_setup": 1, "zero_denominator": 0}
    assert guardrail(rows, n_boot=B)["skipped_unpaired"] == 1
    assert pass_rate_diff(rows, "A", "B", B) == pass_rate_diff(better_b(n=6), "A", "B", B)


def test_zero_denominators():
    rows = [row("z", "A", cost=0.0), row("z", "B", cost=0.0),
            row("x", "A", cost=0.0), row("x", "B", cost=3.0),
            row("y", "A", cost=2.0), row("y", "B", cost=1.0)]
    assert per_task_ratio(rows, "cost", "B", "A") == [("y", 0.5), ("z", 1.0)]
    assert ratio_report(rows, "cost", "B", "A", B)["skipped"]["zero_denominator"] == 1


def test_per_task_means_over_reps():
    rows = [row("t", "A", 0, cost=1.0), row("t", "A", 1, cost=3.0), row("t", "B", 0, cost=1.0)]
    assert per_task_ratio(rows, "cost", "B", "A") == [("t", 0.5)]
    rows = [row("t", "A", turns=None, tool_calls=4), row("t", "B", turns=2)]
    assert per_task_ratio(rows, "turns", "B", "A") == [("t", 0.5)]


def test_deterministic_given_seed():
    rng = random.Random(3)
    rows = [row(f"t{t}", s, r, resolved=rng.random() < 0.5, cost=rng.random())
            for t in range(15) for s in "AB" for r in range(2)]
    assert summary(rows, n_boot=B, seed=5) == summary(list(reversed(rows)), n_boot=B, seed=5)
    assert median_ratio(rows, "cost", "B", "A", B, seed=1) != median_ratio(rows, "cost", "B", "A", B, seed=2)


def test_adoption_tolerates_missing_keys():
    rows = [
        row("t1", "B", fallback_rate=0.25, ax_calls={"read": 3, "edit": 1}, ax_outcomes={"ok": 3, "stale": 1}),
        row("t2", "B", fallback_rate=None, ax_calls={}, ax_rejections=2),
        row("t3", "B", tools={"ax read": 2, "cat": 1}),
        row("t4", "B"),
    ]
    a = adoption(rows, "B")
    assert a["n_runs"] == 4 and a["mean_fallback_rate"] == 0.25 and a["n_runs_with_file_ops"] == 1
    assert a["share_runs_with_ax"] == 0.5
    assert a["mean_ax_calls"] == (4 + 0 + 2 + 0) / 4
    assert a["mean_ax_rejections"] == (1 + 2 + 0 + 0) / 4
    assert adoption(rows, "C")["mean_ax_calls"] is None


def test_wins_losses():
    rows = []
    for t, (ca, cb) in enumerate([(10, 1), (10, 5), (10, 10), (10, 20), (4, 40), (0, 1)]):
        rows += [row(f"t{t}", "A", cost=ca), row(f"t{t}", "B", cost=cb)]
    w = wins_losses(rows, "cost", "A", "B", n=5)
    assert [x["task_id"] for x in w["improvements"]] == ["t0", "t1"]
    assert [x["task_id"] for x in w["regressions"]] == ["t5", "t4", "t3"]
    assert w["improvements"][0]["A"] == 10 and w["improvements"][0]["B"] == 1 and w["improvements"][0]["ratio"] == 0.1
    assert len(wins_losses(rows, "cost", "A", "B", n=1)["regressions"]) == 1
    r = wins_losses(better_b(n=6), "resolved", "A", "B")
    assert [x["task_id"] for x in r["improvements"]] == ["t1", "t4"] and r["regressions"] == []


def test_summary_and_main(tmp_path, capsys):
    rows = better_b(n=12) + [dict(r, setup="C") for r in better_b(n=12) if r["setup"] == "B"]
    s = summary(rows, n_boot=B)
    assert set(s["pass_rate"]) == {"A", "B", "C"}
    assert set(s["ratios"]["cost"]) == {"B/A", "C/A", "C/B"}
    assert s["ratios"]["cost"]["C/B"]["median"] == 1.0
    assert s["guardrail"]["verdict"].startswith("B not worse")
    p = tmp_path / "runs.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert main([str(p), "--boot", str(B)]) == 0
    assert json.loads(capsys.readouterr().out) == json.loads(json.dumps(s))
    assert main([str(tmp_path / "nope.jsonl")]) == 1


def test_empty_setup():
    assert pass_rate([], "A") == (None, None, None)
    assert guardrail([row("t", "A")], n_boot=B)["verdict"] == "inconclusive"
