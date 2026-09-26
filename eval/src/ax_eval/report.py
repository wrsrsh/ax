"""eval/runs/runs.jsonl -> eval/report/REPORT.md

    uv run python -m ax_eval.report                # re-collect runs, then render
    uv run python -m ax_eval.report --no-collect   # render the existing runs.jsonl

numbers come from ax_eval.stats.summary. the small versions below (wilson CIs
for pass rates, bootstrap over tasks for paired ratios) fill in the counts it
doesn't report, and stand in if it fails. the footer says which one was used.
"""

from __future__ import annotations

import argparse
import math
import os
import random
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, median

from ax_eval import stats
from ax_eval.setups import base_of, raw_tools
from ax_eval.table import collect, load, splits, usable
from ax_eval.util import REPORT, RUNS, TASKS

METRICS = ["tokens", "cost", "turns", "wall_seconds"]
MARGIN = 0.05  # guardrail: an ax setup may lose at most 5 pp of pass rate vs its baseline (A, or Ar for raw tools)
TOP = 3
BOOT = 2000

VERDICT_RULE = (
    "rule: a metric counts as helped or hurt only when its 95% CI excludes no change "
    "(ratio 1.0, or 0 pp for pass rate). otherwise: no measurable difference."
)
LIMITATIONS = [
    (
        "- tool-surface confound: B and C reach ax through the shell tool, while A edits with codex's native apply_patch. "
        "differences mix ax itself with the cost of going through the shell (quoting, heredocs, output formatting)."
    ),
    "- single repo: every task comes from hono (typescript). other languages, repo sizes and layouts aren't covered.",
    "- single agent and model: codex on one model at one reasoning effort. other agents may use tools very differently.",
    "- tasks are mined from merged PRs with hidden tests; rewritten instructions can still leak or under-specify the fix.",
    (
        "- CIs are over tasks with a handful of reps each; small task counts give wide intervals, so "
        '"no measurable difference" is not the same as "no difference".'
    ),
]


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0.0, c - h), min(1.0, c + h)]


def boot_ci(xs: list[float], stat, seed: int = 0) -> list[float] | None:
    if len(xs) < 2:
        return None
    rng = random.Random(seed)
    vals = sorted(stat([rng.choice(xs) for _ in xs]) for _ in range(BOOT))
    return [vals[int(0.025 * BOOT)], vals[int(0.975 * BOOT) - 1]]


def by_task(rows: list[dict], setup: str, key: str) -> dict[str, float]:
    vals = defaultdict(list)
    for r in rows:
        if r["setup"] == setup and r.get(key) is not None:
            vals[r["task_id"]].append(float(r[key]))
    return {t: mean(v) for t, v in vals.items()}


def paired(rows: list[dict], setup: str, key: str) -> list[tuple[str, float, float]]:
    a, x = by_task(rows, base_of(setup), key), by_task(rows, setup, key)
    return [(t, a[t], x[t]) for t in sorted(a.keys() & x.keys())]


def setups_of(rows: list[dict]) -> list[str]:
    return sorted({r["setup"] for r in rows if r.get("setup")})


def fallback_summary(rows: list[dict]) -> dict:
    out = {"setups": {}, "guardrail": {}, "ratios": {}, "adoption": {}}
    for s in setups_of(rows):
        rs = [r for r in rows if r["setup"] == s]
        k = sum(bool(r["resolved"]) for r in rs)
        out["setups"][s] = {"n": len(rs), "resolved": k, "pass_rate": k / len(rs), "ci": wilson(k, len(rs))}
        used = [r for r in rs if (r.get("ax_calls_total") or 0) > 0]
        fb = [r["fallback_rate"] for r in rs if r.get("fallback_rate") is not None]
        calls = Counter()
        for r in rs:
            calls.update(r.get("ax_calls") or {})
        out["adoption"][s] = {
            "runs": len(rs), "used_ax": len(used), "adoption": len(used) / len(rs),
            "fallback_rate": median(fb) if fb else None,
            "ax_rejections": sum(r.get("ax_rejections") or 0 for r in rs), "ax_calls": dict(calls),
            "script_calls": sum(r.get("script_calls") or 0 for r in rs),
        }
        if s == base_of(s):
            continue
        diffs = [x - a for _, a, x in paired(rows, s, "resolved")]
        ci = boot_ci(diffs, mean)
        out["guardrail"][s] = {
            "diff": mean(diffs) if diffs else None, "ci": ci, "margin": MARGIN, "tasks": len(diffs),
            "ok": None if ci is None else ci[0] >= -MARGIN,
        }
        out["ratios"][f"{s}/{base_of(s)}"] = {}
        for m in METRICS:
            rat = [x / a for _, a, x in paired(rows, s, m) if a > 0]
            out["ratios"][f"{s}/{base_of(s)}"][m] = {"median": median(rat) if rat else None, "ci": boot_ci(rat, median), "n": len(rat)}
    return out


def from_stats(real: dict, fb: dict) -> dict:
    """reshape ax_eval.stats.summary output into the sections the renderer reads."""
    out = {}
    pr = real.get("pass_rate") or {}
    out["setups"] = {
        s: {**fb["setups"].get(s, {}), "pass_rate": v["rate"], "ci": (v["lo"], v["hi"])}
        for s, v in pr.items() if v.get("rate") is not None
    }
    out["guardrail"] = {}
    for pair, v in (real.get("pass_rate_diff") or {}).items():
        b, a = pair.split("-")
        if v.get("diff") is None:
            continue
        if base_of(a) != base_of(b):
            out.setdefault("raw_vs_code", {}).setdefault(pair, {})["pass_rate"] = {"diff": v["diff"], "ci": (v["lo"], v["hi"])}
            continue
        if a != base_of(b):
            continue
        ci = (v["lo"], v["hi"])
        out["guardrail"][b] = {"diff": v["diff"], "ci": ci, "margin": MARGIN, "tasks": None, "ok": ci[0] >= -MARGIN}
    out["ratios"] = {}
    for metric, pairs in (real.get("ratios") or {}).items():
        for pair, v in pairs.items():
            if v.get("median") is None:
                continue
            b, a = pair.split("/")
            if a == base_of(b):
                dest = out["ratios"]
            elif base_of(a) != base_of(b):
                dest = out.setdefault("raw_vs_code", {})
            else:
                continue
            dest.setdefault(pair, {})[metric] = {"median": v["median"], "ci": (v["lo"], v["hi"]), "n": v.get("n_tasks")}
    out["adoption"] = {
        s: {**fb["adoption"].get(s, {}), "runs": v["n_runs"], "adoption": v["share_runs_with_ax"],
            "used_ax": round(v["share_runs_with_ax"] * v["n_runs"]), "fallback_rate": v.get("mean_fallback_rate")}
        for s, v in (real.get("adoption") or {}).items()
    }
    return out


def summary(rows: list[dict]) -> tuple[dict, str]:
    fb = fallback_summary(rows)
    try:
        return from_stats(stats.summary(rows), fb), "ax_eval.stats.summary"
    except Exception as e:  # a stats bug shouldn't block the report
        return fb, f"built-in fallback (ax_eval.stats.summary failed: {e!r})"


def pct(v) -> str:
    return "-" if v is None else f"{100 * v:.1f}%"


def num(v, nd: int = 0) -> str:
    return "-" if v is None else f"{v:,.{nd}f}"


def money(v) -> str:
    return "-" if v is None else f"${v:.3f}"


def ci_str(ci, f=pct) -> str:
    return "-" if not ci else f"{f(ci[0])} to {f(ci[1])}"


def ratio(v) -> str:
    return "-" if v is None else f"{v:.2f}x"


def med(rows: list[dict], key: str):
    vs = [r[key] for r in rows if r.get(key) is not None]
    return median(vs) if vs else None


def table(head: list[str], body: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(map(str, r)) + " |" for r in body]


def distinct(rows: list[dict], key: str) -> str:
    vs = sorted({str(r[key]) for r in rows if r.get(key) not in (None, "")})
    return ", ".join(vs) if vs else "unknown"


def verdict_metric(e: dict | None) -> tuple[str, str]:
    if not e or e.get("median") is None or not e.get("ci"):
        return "unknown", "not enough paired tasks"
    lo, hi = e["ci"]
    detail = f"median {ratio(e['median'])} of A, 95% CI {ratio(lo)} to {ratio(hi)}"
    if hi < 1:
        return "helped", detail
    if lo > 1:
        return "hurt", detail
    return "no measurable difference", detail


def verdict_pass(g: dict | None) -> tuple[str, str]:
    if not g or g.get("diff") is None or not g.get("ci"):
        return "unknown", "not enough paired tasks"
    lo, hi = g["ci"]
    detail = f"{100 * g['diff']:+.1f} pp vs A, 95% CI {100 * lo:+.1f} to {100 * hi:+.1f} pp"
    if lo > 0:
        return "helped", detail
    if hi < 0:
        return "hurt", detail
    return "no measurable difference", detail


def wins_losses(rows: list[dict], setup: str, key: str, runs_link) -> list[str]:
    pairs = paired(rows, setup, key)
    if key == "resolved":
        scored = [(x - a, t, a, x) for t, a, x in pairs]
        wins = sorted((s for s in scored if s[0] > 0), key=lambda s: -s[0])[:TOP]
        losses = sorted((s for s in scored if s[0] < 0), key=lambda s: s[0])[:TOP]
        fmt_d, fmt_v = (lambda d: f"{100 * d:+.0f} pp"), pct
    else:
        scored = [(x / a, t, a, x) for t, a, x in pairs if a > 0]
        wins = sorted((s for s in scored if s[0] < 1), key=lambda s: s[0])[:TOP]
        losses = sorted((s for s in scored if s[0] > 1), key=lambda s: -s[0])[:TOP]
        fmt_d = ratio
        fmt_v = money if key == "cost" else (lambda v: num(v, 1 if key == "wall_seconds" else 0))
    if not wins and not losses:
        return ["- no task differs from A."]
    out = []
    for label, items in (("wins", wins), ("losses", losses)):
        if not items:
            out.append(f"- {label}: none")
            continue
        out.append(f"- {label}:")
        for d, t, a, x in items:
            out.append(f"  - `{t}`: A {fmt_v(a)}, {setup} {fmt_v(x)} ({fmt_d(d)}); runs {runs_link(t, setup)}")
    return out


def render(rows: list[dict], runs_dir: Path = RUNS, out: Path = REPORT / "REPORT.md", tasks: Path = TASKS / "final.jsonl", subset: str | None = "heldout") -> str:
    """`subset` picks the rows the numbers are computed from (default held-out only;
    None for everything). dry runs (stub, fake api) never count."""
    real = [r for r in rows if not r.get("dry")]
    allgood = [r for r in rows if usable(r)]
    good = [r for r in allgood if subset is None or r.get("split") == subset]
    infra = [r for r in real if r.get("infra_failure")]
    incomplete = [r for r in real if not r.get("complete") and not r.get("infra_failure")]
    s, source = summary(good)
    setups = setups_of(good)
    others = [x for x in setups if x != base_of(x)]
    split = Counter(splits(tasks).values())

    def link(run_id: str) -> str:
        return os.path.relpath(Path(runs_dir) / run_id / "events.jsonl", Path(out).parent)

    def runs_link(task: str, setup: str) -> str:
        rs = sorted((r for r in good if r["task_id"] == task and r["setup"] in (base_of(setup), setup)), key=lambda r: (r["setup"], r.get("rep") or 0))
        return " ".join(f"[{r['setup']}{r.get('rep') if r.get('rep') is not None else ''}]({link(r['run_id'])})" for r in rs)

    L = ["# ax eval report", ""]
    L += [
        f"generated {date.today().isoformat()} from `{Path(runs_dir).name}/runs.jsonl`.", "",
        f"- agent: {distinct(good, 'agent')}, codex {distinct(good, 'codex_version')}",
        f"- model: {distinct(good, 'model')}, effort {distinct(good, 'effort')}",
        f"- ax commit: {distinct(good, 'ax_commit')}",
        (
            f"- tasks: {sum(split.values())} in final.jsonl ({split.get('dev', 0)} dev, {split.get('heldout', 0)} held-out); "
            f"{len({r['task_id'] for r in good})} with usable runs here"
        ),
        (
            f"- runs: {len(real)} real ({len(rows) - len(real)} dry runs ignored), {len(allgood)} usable, "
            f"{len(good)} in this report ({subset or 'all'} split), {len(infra)} infra failures, {len(incomplete)} incomplete, "
            f"{sum(bool(r.get('timed_out')) for r in good)} timed out (counted as unresolved)"
        ),
        f"- setups: {', '.join(setups) or 'none'}. A is the baseline (Ar for the raw-tools family); ratios and deltas are paired by task against it.",
        "",
    ]

    L += ["## summary", ""]
    body = []
    for x in setups:
        e = s["setups"].get(x, {})
        rs = [r for r in good if r["setup"] == x]
        body.append([
            x, len(rs), len({r["task_id"] for r in rs}), pct(e.get("pass_rate")), ci_str(e.get("ci")),
            num(med(rs, "tokens")), money(med(rs, "cost")), num(med(rs, "turns"), 1), num(med(rs, "wall_seconds"), 1),
        ])
    L += table(["setup", "runs", "tasks", "pass rate", "95% CI", "median tokens", "median cost", "median turns", "median wall s"], body)
    L += ["", "pass rate by split:", ""]
    body = []
    for x in setups:
        cells = [x]
        for sp in ("dev", "heldout"):
            rs = [r for r in allgood if r["setup"] == x and r.get("split") == sp]
            k = sum(bool(r["resolved"]) for r in rs)
            cells.append(f"{pct(k / len(rs))} ({k}/{len(rs)})" if rs else "-")
        body.append(cells)
    L += table(["setup", "dev", "held-out"], body) + [""]

    L += ["## guardrail", ""]
    g = s["guardrail"]
    for x, e in sorted(g.items()):
        status = {True: "ok", False: "FAILED", None: "not enough data"}[e["ok"]]
        _, detail = verdict_pass(e)
        L.append(f"- {x}: {status}. pass rate {detail}; allowed loss {100 * e['margin']:.0f} pp.")
    if not g:
        L.append("no ax setup to compare against its baseline.")
    L.append("")

    L += ["## ratios vs baseline", "", "median over tasks of (setup mean / baseline mean); below 1 means the ax setup used less.", ""]
    body = []
    for comp, ms in sorted(s["ratios"].items()):
        for m in METRICS:
            e = ms.get(m) or {}
            body.append([comp, m, ratio(e.get("median")), ci_str(e.get("ci"), ratio), e.get("n", "-")])
    L += (table(["comparison", "metric", "median ratio", "95% CI", "tasks"], body) if body else ["no paired tasks."]) + [""]

    if s.get("raw_vs_code"):
        L += ["## code mode vs raw tools", "",
              "same letter, codex's code mode (one `exec` js tool) vs plain function tools. paired by task; pass-rate delta and median ratios.", ""]
        body = []
        for comp, ms in sorted(s["raw_vs_code"].items()):
            for m, e in ms.items():
                if m == "pass_rate":
                    body.append([comp, m, f"{e['diff']:+.3f}", ci_str(e.get("ci"), lambda v: f"{v:+.3f}"), "-"])
                else:
                    body.append([comp, m, ratio(e.get("median")), ci_str(e.get("ci"), ratio), e.get("n", "-")])
        L += table(["comparison", "metric", "value", "95% CI", "tasks"], body) + [""]

    L += ["## adoption", "", "fallback rate = share of file reads/searches/edits that didn't go through ax; script calls = inline python/node doing that work.", ""]
    body = []
    for x in setups:
        e = s["adoption"].get(x) or {}
        top = ", ".join(f"{k} {v}" for k, v in Counter(e.get("ax_calls") or {}).most_common(4)) or "-"
        body.append([x, e.get("runs", "-"), f"{e.get('used_ax', '-')} ({pct(e.get('adoption'))})", pct(e.get("fallback_rate")),
                     e.get("script_calls", "-"), e.get("ax_rejections", "-"), top])
    L += table(["setup", "runs", "runs using ax", "median fallback rate", "script calls", "ax rejections", "top ax commands"], body) + [""]

    L += ["## wins and losses", "", f"top {TOP} tasks per metric, by per-task ratio (or pass-rate delta) against the baseline.", ""]
    for x in others:
        for m in ["resolved"] + METRICS:
            L += [f"### {x} vs {base_of(x)}: {m}", ""] + wins_losses(good, x, m, runs_link) + [""]

    L += ["## verdict", "", VERDICT_RULE, ""]
    rates = [e.get("pass_rate") for e in s["setups"].values() if e.get("pass_rate") is not None]
    if rates and min(rates) >= 0.95:
        L += ["- pass rate is at the ceiling (95%+ in every setup), so it can't separate the setups here; the comparison rests on tokens, cost, turns and wall time.", ""]
    if not others:
        L.append("- no ax setup runs yet.")
    for x in others:
        v, d = verdict_pass(g.get(x))
        parts = [f"pass rate: {v}. {d}"]
        for m in METRICS:
            v, d = verdict_metric((s["ratios"].get(f"{x}/{base_of(x)}") or {}).get(m))
            parts.append(f"{m}: {v}. {d}")
        L.append(f"- **{x} vs {base_of(x)}**")
        L += [f"  - {p}" for p in parts]
    L.append("")

    L += ["## limitations", "", *LIMITATIONS, "", f"stats: {source}.", ""]
    text = "\n".join(L)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(text)
    return text


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", type=Path, default=RUNS)
    p.add_argument("--out", type=Path, default=REPORT / "REPORT.md")
    p.add_argument("--tasks", type=Path, default=TASKS / "final.jsonl")
    p.add_argument("--no-collect", action="store_true", help="use the existing runs.jsonl as is")
    p.add_argument("--split", default="heldout", choices=("heldout", "dev", "all"))
    a = p.parse_args(argv)
    if not a.no_collect:
        collect(a.runs, a.out.parent, a.tasks)
    rows = load(a.runs)
    render(rows, a.runs, a.out, a.tasks, None if a.split == "all" else a.split)
    print(f"wrote {a.out} ({len(rows)} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
