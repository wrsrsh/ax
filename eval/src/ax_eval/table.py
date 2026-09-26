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

from ax_eval.mine import TASKS
from ax_eval.parity import EVAL

RUNS = EVAL / "runs"
REPORT = EVAL / "report"

MANIFEST = [
    "run_id", "task_id", "setup", "rep", "seed", "agent", "codex_version", "model", "effort",
    "ax_commit", "image", "started", "ended", "exit_code", "timed_out", "infra_failure", "infra_reason",
]
GRADE = ["resolved", "f2p_passed", "f2p_total", "p2p_passed", "p2p_total", "grade_seconds"]
METRICS = [
    "input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens", "reasoning_tokens",
    "tool_calls", "failed_commands", "failed_patches", "fallback_rate", "ax_rejections", "cost", "completed",
]
DICTS = ["tools", "ax_calls", "ax_outcomes"]
COLUMNS = MANIFEST + ["split"] + GRADE + ["grade_error", "failing"] + METRICS + [
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
    if not tasks.exists():
        return {}
    out = {}
    for line in tasks.read_text().splitlines():
        if line.strip():
            t = json.loads(line)
            out[t["id"]] = t.get("set")
    return out


def row(run: Path, split: dict[str, str] | None = None) -> dict:
    m, g, x = (_load(run / f) for f in ("manifest.json", "grade.json", "metrics.json"))
    missing = [f for f, d in (("manifest.json", m), ("grade.json", g), ("metrics.json", x)) if d is None]
    missing += [f for f in ("events.jsonl",) if not (run / f).exists()]
    m, g, x = m or {}, g or {}, x or {}

    r = {k: m.get(k) for k in MANIFEST}
    r["run_id"] = r["run_id"] or run.name
    r["timed_out"] = bool(r["timed_out"])
    r["infra_failure"] = bool(r["infra_failure"])
    r["split"] = (split or {}).get(r["task_id"])
    r.update({k: g.get(k) for k in GRADE})
    r["grade_error"] = g.get("error")
    r["failing"] = g.get("failing") or []
    r.update({k: x.get(k) for k in METRICS})
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
    """rows that count toward results: all files there, no infra failure."""
    return bool(r.get("complete")) and not r.get("infra_failure")


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
    rows = [row(d, split) for d in dirs]

    runs_dir.mkdir(parents=True, exist_ok=True)
    with (runs_dir / "runs.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    _csv(runs_dir / "runs.csv", rows, COLUMNS)
    _csv(report_dir / "per_task.csv", per_task(rows), PER_TASK)
    return rows


def load(runs_dir: Path = RUNS) -> list[dict]:
    f = Path(runs_dir) / "runs.jsonl"
    return [json.loads(line) for line in f.read_text().splitlines() if line.strip()] if f.exists() else []


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
