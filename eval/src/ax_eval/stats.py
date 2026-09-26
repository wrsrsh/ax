"""run rows -> pass rates, paired diffs, cost ratios, adoption. all CIs are
percentile bootstraps over tasks (cluster bootstrap: a resampled task brings
all its reps), so rep-to-rep noise inside a task doesn't count as extra n.

a row: task_id, setup, rep, resolved, input_tokens, cached_input_tokens,
output_tokens, cost, turns, wall_seconds, infra_failure (+ parse.metrics keys).
rows with infra_failure are dropped everywhere.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from ax_eval.setups import SETUPS
from ax_eval.util import RUNS, jsonl

METRICS = ("tokens", "cost", "turns", "wall_seconds")
N_BOOT = 10_000
SEED = 0
REJECTS = ("stale", "ambiguous", "parse-rejected", "no-match")


def clean(rows: list[dict]) -> list[dict]:
    return [r for r in rows if not r.get("infra_failure")]


def value(row: dict, metric: str) -> float | None:
    if metric == "tokens":
        i, o = row.get("input_tokens"), row.get("output_tokens")
        return None if i is None or o is None else float(i + o)
    if metric == "resolved":
        return float(bool(row.get("resolved")))
    v = row.get(metric)
    if v is None and metric == "turns":
        v = row.get("tool_calls")
    return None if v is None else float(v)


def task_means(rows: list[dict], setup: str, metric: str) -> dict[str, float]:
    """per-task mean over reps (reps with a missing value are left out)."""
    acc = defaultdict(list)
    for r in clean(rows):
        if r.get("setup") == setup:
            v = value(r, metric)
            if v is not None:
                acc[r["task_id"]].append(v)
    return {t: sum(vs) / len(vs) for t, vs in sorted(acc.items())}


def _ci(values, stat, n_boot: int, seed: int) -> tuple[float, float, float]:
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        return (None, None, None)
    idx = np.random.default_rng(seed).integers(0, x.size, size=(n_boot, x.size))
    boots = stat(x[idx], axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return (float(stat(x)), float(lo), float(hi))


def pass_rate(rows, setup, n_boot=N_BOOT, seed=SEED):
    """mean of per-task pass rates (each task weighs the same even if a rep was lost), 95% CI."""
    return _ci(list(task_means(rows, setup, "resolved").values()), np.mean, n_boot, seed)


def _paired(rows, metric, a, b):
    ma, mb = task_means(rows, a, metric), task_means(rows, b, metric)
    both = sorted(ma.keys() & mb.keys())
    return both, ma, mb, len(ma.keys() ^ mb.keys())


def pass_rate_diff(rows, a, b, n_boot=N_BOOT, seed=SEED):
    """paired b - a over tasks run under both setups."""
    both, ma, mb, _ = _paired(rows, "resolved", a, b)
    return _ci([mb[t] - ma[t] for t in both], np.mean, n_boot, seed)


def guardrail(rows, a="A", b="B", margin=0.0, n_boot=N_BOOT, seed=SEED) -> dict:
    """is b worse than a on pass rate? margin allows a non-inferiority bound (0 = strict)."""
    both, _, _, unpaired = _paired(rows, "resolved", a, b)
    diff, lo, hi = pass_rate_diff(rows, a, b, n_boot, seed)
    if diff is None:
        verdict = "inconclusive"
    elif lo >= -margin:
        verdict = f"{b} not worse than {a}: CI excludes negative"
    elif hi < -margin:
        verdict = f"{b} worse"
    else:
        verdict = "inconclusive"
    return {"diff": diff, "lo": lo, "hi": hi, "margin": margin, "n_tasks": len(both),
            "skipped_unpaired": unpaired, "verdict": verdict}


def _ratios(rows, metric, num_setup, den_setup):
    both, mden, mnum, unpaired = _paired(rows, metric, den_setup, num_setup)
    out, zero_den = [], 0
    for t in both:
        n, d = mnum[t], mden[t]
        if d == 0:
            if n == 0:
                out.append((t, 1.0))
            else:
                zero_den += 1
            continue
        out.append((t, n / d))
    return out, {"missing_setup": unpaired, "zero_denominator": zero_den}


def per_task_ratio(rows, metric, num_setup, den_setup) -> list[tuple[str, float]]:
    """(task, mean_num / mean_den). tasks missing either setup or with a zero
    denominator are skipped (0/0 counts as 1); see ratio_report for the counts."""
    return _ratios(rows, metric, num_setup, den_setup)[0]


def median_ratio(rows, metric, num_setup, den_setup, n_boot=N_BOOT, seed=SEED):
    return _ci([r for _, r in per_task_ratio(rows, metric, num_setup, den_setup)], np.median, n_boot, seed)


def ratio_report(rows, metric, num_setup, den_setup, n_boot=N_BOOT, seed=SEED) -> dict:
    pairs, skipped = _ratios(rows, metric, num_setup, den_setup)
    med, lo, hi = _ci([r for _, r in pairs], np.median, n_boot, seed)
    return {"median": med, "lo": lo, "hi": hi, "n_tasks": len(pairs), "skipped": skipped}


def _ax_total(r: dict) -> int:
    calls = r.get("ax_calls")
    if isinstance(calls, dict):
        return sum(calls.values())
    if isinstance(calls, (int, float)):
        return int(calls)
    return sum(v for k, v in (r.get("tools") or {}).items() if k.split()[0] == "ax")


def _rejections(r: dict) -> int:
    if r.get("ax_rejections") is not None:
        return r["ax_rejections"]
    return sum((r.get("ax_outcomes") or {}).get(k, 0) for k in REJECTS)


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def adoption(rows, setup) -> dict:
    rs = [r for r in clean(rows) if r.get("setup") == setup]
    fb = [r["fallback_rate"] for r in rs if r.get("fallback_rate") is not None]
    calls = [_ax_total(r) for r in rs]
    return {
        "n_runs": len(rs),
        "mean_fallback_rate": _mean(fb),
        "n_runs_with_file_ops": len(fb),
        "share_runs_with_ax": _mean([c > 0 for c in calls]),
        "mean_ax_calls": _mean(calls),
        "mean_ax_rejections": _mean([_rejections(r) for r in rs]),
    }


def wins_losses(rows, metric, a, b, n=5, higher_is_better=None) -> dict:
    """biggest per-task moves from a to b. cost-like metrics rank by relative change,
    resolved (higher is better) by absolute change."""
    if higher_is_better is None:
        higher_is_better = metric == "resolved"
    both, ma, mb, _ = _paired(rows, metric, a, b)
    items = []
    for t in both:
        va, vb = ma[t], mb[t]
        if higher_is_better:
            gain = vb - va
        elif va > 0:
            gain = (va - vb) / va
        else:
            gain = 0.0 if vb == 0 else -math.inf
        if gain:
            items.append({"task_id": t, a: va, b: vb, "diff": vb - va,
                          "ratio": vb / va if va else None, "gain": gain})
    items.sort(key=lambda x: (-x["gain"], x["task_id"]))
    wins = [x for x in items if x["gain"] > 0][:n]
    losses = sorted((x for x in items if x["gain"] < 0), key=lambda x: (x["gain"], x["task_id"]))[:n]
    for x in wins + losses:
        if math.isinf(x["gain"]):
            x["gain"] = None
    return {"improvements": wins, "regressions": losses}


def summary(rows, n_boot=N_BOOT, seed=SEED) -> dict:
    kept = clean(rows)
    present = [s for s in SETUPS if any(r.get("setup") == s for r in kept)]
    pairs = [(a, b) for i, a in enumerate(present) for b in present[i + 1:]]
    tasks = {s: len({r["task_id"] for r in kept if r.get("setup") == s}) for s in present}
    return {
        "n_rows": len(rows),
        "n_infra_excluded": len(rows) - len(kept),
        "seed": seed,
        "n_boot": n_boot,
        "tasks": tasks,
        "pass_rate": {s: dict(zip(("rate", "lo", "hi"), pass_rate(kept, s, n_boot, seed))) for s in present},
        "pass_rate_diff": {f"{b}-{a}": dict(zip(("diff", "lo", "hi"), pass_rate_diff(kept, a, b, n_boot, seed)))
                           for a, b in pairs},
        "guardrail": guardrail(kept, n_boot=n_boot, seed=seed) if {"A", "B"} <= set(present) else None,
        "ratios": {m: {f"{b}/{a}": ratio_report(kept, m, b, a, n_boot, seed) for a, b in pairs} for m in METRICS},
        "adoption": {s: adoption(kept, s) for s in present},
        "wins_losses": {m: {f"{b} vs {a}": wins_losses(kept, m, a, b) for a, b in pairs}
                        for m in ("resolved",) + METRICS},
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="summary stats over runs.jsonl")
    p.add_argument("runs", nargs="?", type=Path, default=RUNS / "runs.jsonl")
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--boot", type=int, default=N_BOOT)
    a = p.parse_args(argv)
    if not a.runs.exists():
        print(f"no runs file at {a.runs}", file=sys.stderr)
        return 1
    print(json.dumps(summary(jsonl(a.runs), a.boot, a.seed), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
