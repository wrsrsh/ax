"""eval/runs/<run-id>/{manifest,grade,metrics}.json -> one flat row per run.

writes eval/runs/runs.jsonl, eval/runs/runs.csv and eval/report/per_task.csv
(per task x setup means over reps). missing or broken files don't stop it:
the row gets complete=False and `missing` says what wasn't there.

    uv run python -m ax_eval.table
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

from ax_eval.parse import COST_PARTS, cost_parts
from ax_eval.runner import load_prices
from ax_eval.util import RUNS, TASKS, jsonl

MANIFEST = [
    "run_id", "task_id", "setup", "rep", "seed", "agent", "codex_version", "claude_version", "model", "effort",
    "ax_commit", "image", "started", "ended", "exit_code", "timed_out", "infra_failure", "infra_reason",
]
GRADE = ["resolved", "f2p_passed", "f2p_total", "p2p_passed", "p2p_total", "grade_seconds"]
METRICS = [
    "input_tokens", "cached_input_tokens", "cache_write_input_tokens", "uncached_input_tokens", "output_tokens", "reasoning_tokens",
    "tool_calls", "failed_commands", "failed_patches", "fallback_rate", "script_calls", "ax_rejections", "cost", *COST_PARTS, "completed",
]
DICTS = ["tools", "ax_calls", "ax_outcomes"]
COLUMNS = MANIFEST + ["split", "dry"] + GRADE + ["grade_error", "failing"] + METRICS + [
    "agent_error", "wall_seconds", "tokens", "turns", "ax_calls_total",
] + DICTS + ["complete", "missing"]

PER_TASK = ["task_id", "setup", "split", "n", "resolved_rate", "tokens", "cost", "turns", "wall_seconds"]


def _load(path: Path) -> dict | None:
    try:
        d = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def _time(v) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v).timestamp()
        except ValueError:
            return None
    return None


def splits(tasks: Path = TASKS / "final.jsonl") -> dict[str, str]:
    """task id -> "dev" / "heldout"."""
    return {t["id"]: t.get("set") for t in jsonl(tasks)} if tasks.exists() else {}


def row(run: Path, split: dict[str, str] | None = None, prices: dict | None = None) -> dict:
    m, g, x = (_load(run / f) for f in ("manifest.json", "grade.json", "metrics.json"))
    missing = [f for f, d in (("manifest.json", m), ("grade.json", g), ("metrics.json", x)) if d is None]
    if not (run / "events.jsonl").exists():
        missing.append("events.jsonl")
    m, g, x = m or {}, g or {}, x or {}

    r = {k: m.get(k) for k in MANIFEST}
    r["run_id"] = r["run_id"] or run.name
    # the runner writes the task under "task"
    r["task_id"] = m.get("task_id") or m.get("task")
    # stub runs and codex / claude against a fake api cost nothing and prove nothing
    r["dry"] = m.get("agent") not in ("codex", "claude") or any(h in (m.get("api_base_url") or "") for h in ("host.docker.internal", "127.0.0.1", "localhost"))
    r["timed_out"] = bool(r["timed_out"])
    r["infra_failure"] = bool(r["infra_failure"])
    r["split"] = (split or {}).get(r["task_id"])
    r.update({k: g.get(k) for k in GRADE})
    r["grade_error"] = g.get("error")
    r["failing"] = g.get("failing") or []
    r.update({k: x.get(k) for k in METRICS})
    if any(r[k] is None for k in COST_PARTS) and None not in (r["uncached_input_tokens"], r["cached_input_tokens"], r["output_tokens"]):
        # metrics.json from before the split: same formula as parse.cost, today's prices.json
        r.update(cost_parts(r, load_prices() if prices is None else prices))
    r["agent_error"] = x.get("error")
    for k in DICTS:
        r[k] = x.get(k) or {}

    t0, t1 = _time(r["started"]), _time(r["ended"])
    r["wall_seconds"] = round(t1 - t0, 1) if t0 is not None and t1 is not None else None
    r["tokens"] = (r["input_tokens"] or 0) + (r["output_tokens"] or 0) if x else None
    r["turns"] = r["tool_calls"]
    r["ax_calls_total"] = sum(r["ax_calls"].values()) if x else None
    r["complete"] = not missing and r["resolved"] is not None and r["setup"] is not None
    r["missing"] = missing
    return r


def usable(r: dict) -> bool:
    """rows that count toward results: all files there, no infra failure, a real model."""
    return bool(r.get("complete")) and not r.get("infra_failure") and not r.get("dry")


def _avg(rs: list[dict], k: str) -> float | None:
    vs = [r[k] for r in rs if r.get(k) is not None]
    return round(mean(vs), 4) if vs else None


def per_task(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for r in rows:
        if usable(r):
            groups[(r["task_id"], r["setup"])].append(r)
    return [
        {"task_id": task, "setup": setup, "split": rs[0].get("split"), "n": len(rs), "resolved_rate": _avg(rs, "resolved")}
        | {k: _avg(rs, k) for k in ("tokens", "cost", "turns", "wall_seconds")}
        for (task, setup), rs in sorted(groups.items())
    ]


def _cell(v):
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True)
    return "" if v is None else v


def _csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: _cell(r.get(k)) for k in cols})


def collect(runs_dir: Path = RUNS, report_dir: Path | None = None, tasks: Path = TASKS / "final.jsonl") -> list[dict]:
    runs_dir = Path(runs_dir)
    report_dir = Path(report_dir) if report_dir else runs_dir.parent / "report"
    split = splits(tasks)
    dirs = sorted(d for d in runs_dir.iterdir() if d.is_dir() and not d.name.startswith(".")) if runs_dir.exists() else []
    prices: dict[str, dict] = {}

    def priced(d: Path) -> dict:
        m = _load(d / "manifest.json") or {}
        model = m.get("model") or "gpt-6-astra"
        if model not in prices:
            prices[model] = load_prices(model=model)
        return row(d, split, prices[model])

    rows = [priced(d) for d in dirs]

    runs_dir.mkdir(parents=True, exist_ok=True)
    with (runs_dir / "runs.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    _csv(runs_dir / "runs.csv", rows, COLUMNS)
    _csv(report_dir / "per_task.csv", per_task(rows), PER_TASK)
    return rows


def load(runs_dir: Path = RUNS) -> list[dict]:
    f = Path(runs_dir) / "runs.jsonl"
    return jsonl(f) if f.exists() else []


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", type=Path, default=RUNS)
    p.add_argument("--report", type=Path, default=None)
    a = p.parse_args(argv)
    rows = collect(a.runs, a.report)
    print(f"{len(rows)} runs, {sum(map(usable, rows))} usable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
