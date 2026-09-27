"""which ax calls actually failed, and how.

a codex command_execution only has one exit code for the whole shell line, and
the agent often chains `ax edit ... && bun x vitest ...`. so a non-zero exit
counts against ax only when the ax segment is the last one, or the output
starts with an ax-style error line (`error:`, `ax:`, `<path>: stale anchor`,
`... isn't`, `no such path`, `unexpected argument`, `nothing written (...)`).
otherwise it goes to the later command (vitest, tsc, prettier).

reads the non-dry held-out runs listed in runs.jsonl and writes
report/ax_audit.md + ax_audit.json.

    uv run python -m ax_eval.audit                 # eval/runs -> eval/report
    uv run python -m ax_eval.audit path/to/runs --out /tmp/ax_audit.md
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

from ax_eval.parse import segments, unwrap
from ax_eval.util import REPORT, RUNS, jsonl

KINDS = ("usage error", "stale anchor", "no match", "parse-rejected", "missing path", "other")
PREFIXES = {"sudo", "env", "time", "timeout", "xargs"}
RUNNERS = {"bun", "bunx", "npx", "npm", "pnpm", "yarn"}
LINES_FOR = ("edit", "read", "diff", "map")
EXAMPLES = 3
TRIM = 120

# `<<<` is a here-string, not a heredoc
HEREDOC = re.compile(r"(?<!<)<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")

# first output line that says ax refused or errored; bare `error:` only counts when ax ran first
LEADING = re.compile(
    r"^(ax: |error: |\S+: stale anchor|\S+: find text|\S+: this change doesn't parse|nothing written \()"
    r"|isn't|no such path|unexpected argument"
)
# lines only ax prints when it fails: clap usage errors (followed by `Usage: ax`; bun's
# `error: "vitest" exited with code 1` isn't one), `ax: <why>`, edit/write refusals, a missing
# file in `ax read` (lowercase, unlike cat and rg)
AX_ERROR = re.compile(
    r"^(error: (?=[\s\S]{0,400}?^Usage: ax )|ax: |\S+: (stale anchor|find text|this change doesn't parse|no such file or directory|is a directory)"
    r"|anchor \S+ moved and now matches|nothing written \(|\S+ already exists\. read it first)",
    re.M,
)

KIND_RULES = [
    ("parse-rejected", r"parse-rejected|this change doesn't parse"),
    ("stale anchor", r"stale anchor|moved and now matches|changed since you read it|nothing written \((stale|ambiguous)\)"),
    ("no match", r"isn't in the file|find text not found|occurs \d+ times|nothing written \(no-match\)"),
    ("missing path", r"no such path|no such file or directory|doesn't exist"),
    ("usage error", r"unexpected argument|Usage: ax|^error: |nothing written \(error\)|bad pattern|bad glob|bad patch|is a directory|already exists|refusing to"),
]


def strip_heredocs(cmd: str) -> str:
    """drop heredoc bodies but keep whatever runs after the terminator."""
    lines, out, i = cmd.split("\n"), [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        for m in HEREDOC.finditer(line):
            dash, tag = m.group(1), m.group(3)
            while i < len(lines) and (lines[i].lstrip("\t") if dash else lines[i]).strip() != tag:
                i += 1
            i += 1
    return "\n".join(out)


def program(words: list[str]) -> list[str]:
    """drop `FOO=1`, `timeout 30` and friends in front of the real program."""
    while words and ("=" in words[0] or words[0] in PREFIXES):
        words = words[1:]
        if words and words[0].isdigit():
            words = words[1:]
    return words


def calls(command: str) -> list[list[str]]:
    segs = (program(w) for w in segments(strip_heredocs(unwrap(command))))
    return [s for s in segs if s]


def prog(words: list[str]) -> str:
    return words[0].rsplit("/", 1)[-1]


def sub(words: list[str]) -> str:
    return next((w for w in words[1:] if not w.startswith("-")), "")


def label(words: list[str]) -> str:
    """`bun x vitest --run a.ts` -> `bun x vitest`, `git diff` -> `git`."""
    p = prog(words)
    if p not in RUNNERS:
        return p
    rest = [w for w in words[1:] if not w.startswith("-") and "/" not in w and "." not in w]
    n = 2 if p != "bunx" and rest[:1] and rest[0] in ("run", "x", "exec") else 1
    return " ".join([p, *rest[:n]])


def first_line(output: str) -> str:
    return next((line for line in output.splitlines() if line.strip()), "")


def kind(output: str) -> str:
    for k, pat in KIND_RULES:
        if re.search(pat, output, re.M):
            return k
    return "other"


def blame(command: str, output: str, exit_code) -> dict | None:
    """None when the command doesn't invoke ax. otherwise which segment a
    non-zero exit belongs to and why."""
    segs = calls(command)
    ax = [i for i, s in enumerate(segs) if prog(s) == "ax"]
    if not ax:
        return None
    if exit_code in (0, None):
        return {"failed": False, "segments": segs}
    out = output or ""
    head = first_line(out)
    m = AX_ERROR.search(out)
    others = [s for s in segs if prog(s) != "ax"]
    if ax[-1] == len(segs) - 1 and (m or not others):
        who, why, at = _named(segs, ax, _line(out, m), ax[-1]), "ax is the last segment", m.start() if m else 0
    elif LEADING.search(head) and not (head.startswith("error: ") and ax[0] != 0):
        who, why, at = _named(segs, ax, head, ax[0]), "output starts with an ax error", 0
    elif m:
        # `ax read a && ax edit b <<EOF && bun test`: the edit refused and the chain stopped there
        who, why, at = _named(segs, ax, _line(out, m), ax[0]), "ax error line later in the output", m.start()
    else:
        # ax is last but printed no failure: an earlier command in the `&&` chain is what exited
        where = "before ax" if ax[-1] == len(segs) - 1 else "after ax"
        return {"failed": True, "ax": False, "segments": segs, "later": label(others[-1]), "where": where}
    return {"failed": True, "ax": True, "segments": segs, "sub": sub(segs[who]), "why": why, "kind": kind(out[at:]), "line": first_line(out[at:])}


def _line(out: str, m) -> str:
    return out[m.start():].split("\n", 1)[0] if m else ""


def _named(segs, ax, line: str, default: int) -> int:
    """the ax segment whose arguments show up in the error line as a whole path
    (`src/jsx` doesn't match `src/jsx/context.test.tsx`)."""
    for i in ax:
        if any(len(w) > 2 and re.search(rf"(?<![\w/.-]){re.escape(w)}(?![\w/.-])", line) for w in segs[i][2:]):
            return i
    return default


def trim(command: str) -> str:
    s = " ⏎ ".join(x.strip() for x in unwrap(command).strip().splitlines())
    return s if len(s) <= TRIM else s[: TRIM - 1] + "…"


def runs_of(runs_dir: Path) -> list[dict]:
    """non-dry held-out rows from runs.jsonl."""
    f = Path(runs_dir) / "runs.jsonl"
    if not f.exists():
        raise SystemExit(f"no runs.jsonl in {runs_dir}; run `python -m ax_eval.table` first")
    return [r for r in jsonl(f) if not r.get("dry") and r.get("split") == "heldout"]


def commands(run: Path):
    f = run / "events.jsonl"
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        it = e.get("item") or {}
        if e.get("type") == "item.completed" and it.get("type") == "command_execution":
            yield it


def _ax_log(f: Path, tally: Counter):
    """ax's own per-call log. lines from parallel calls can interleave; those get counted, not parsed."""
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        tally["lines"] += 1
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            tally["corrupt"] += 1
            continue
        if isinstance(e, dict):
            yield e


def audit(runs_dir: Path = RUNS) -> dict:
    rows = runs_of(runs_dir)
    table = defaultdict(Counter)
    examples = defaultdict(list)
    why, later, where, by_setup = Counter(), Counter(), Counter(), Counter()
    sizes = defaultdict(list)
    n_cmds = n_ax = n_failed = 0
    per_setup = Counter(r.get("setup") for r in rows)
    map_first, map_first_ax, find_agents = Counter(), Counter(), Counter()
    log, log_cmds, log_outcomes = Counter(), Counter(), Counter()

    for r in rows:
        first, first_ax, agents = None, None, False
        for it in commands(Path(runs_dir) / r["run_id"]):
            n_cmds += 1
            cmd, out = it.get("command", ""), it.get("aggregated_output") or ""
            segs = calls(cmd)
            if first is None:
                first = segs[0] if segs else []
            axs = [s for s in segs if prog(s) == "ax"]
            if first_ax is None and axs:
                first_ax = axs[0]
            agents |= any(sub(s) == "find" and any(w.endswith("AGENTS.md") for w in s[2:]) for s in axs)
            b = blame(cmd, out, it.get("exit_code"))
            if b is None:
                continue
            n_ax += 1
            if not b["failed"]:
                if len(segs) == 1 and sub(segs[0]) in LINES_FOR:
                    sizes[sub(segs[0])].append(len(out.splitlines()))
                continue
            n_failed += 1
            if not b["ax"]:
                later[b["later"]] += 1
                where[b["where"]] += 1
                continue
            why[b["why"]] += 1
            by_setup[r.get("setup")] += 1
            table[f"ax {b['sub']}".strip()][b["kind"]] += 1
            if len(examples[b["kind"]]) < EXAMPLES:
                examples[b["kind"]].append({"run_id": r["run_id"], "command": trim(cmd), "output": b["line"][:TRIM]})
        for e in _ax_log(Path(runs_dir) / r["run_id"] / "ax_log.jsonl", log):
            if e.get("exit"):
                log["nonzero"] += 1
                log_cmds[e.get("cmd") or "?"] += 1
                log_outcomes[e.get("outcome") or "none"] += 1
        s = r.get("setup")
        map_first[s] += bool(first) and prog(first) == "ax" and sub(first) == "map"
        map_first_ax[s] += bool(first_ax) and sub(first_ax) == "map"
        find_agents[s] += agents

    setups = sorted(per_setup)
    return {
        "runs": len(rows),
        "runs_by_setup": dict(sorted(per_setup.items())),
        "commands": n_cmds,
        "ax_commands": n_ax,
        "ax_commands_nonzero": n_failed,
        "blamed_on_ax": sum(why.values()),
        "blamed_on_ax_by": dict(why.most_common()),
        "blamed_on_ax_by_setup": dict(sorted(by_setup.items())),
        "blamed_on_later": sum(later.values()),
        "blamed_on_later_where": dict(where.most_common()),
        "later_commands": dict(later.most_common()),
        "failures": {k: {kd: v[kd] for kd in KINDS if v[kd]} for k, v in sorted(table.items(), key=lambda kv: -sum(kv[1].values()))},
        "examples": {k: examples[k] for k in KINDS if examples[k]},
        "first_command_ax_map": {s: map_first[s] for s in setups},
        "first_ax_command_ax_map": {s: map_first_ax[s] for s in setups},
        "runs_with_ax_find_agents_md": {s: find_agents[s] for s in setups},
        "ax_log": {"lines": log["lines"], "corrupt": log["corrupt"], "nonzero": log["nonzero"],
                   "nonzero_by_cmd": dict(log_cmds.most_common()), "nonzero_by_outcome": dict(log_outcomes.most_common())},
        "output_lines": {
            k: {"calls": len(v), "median": median(v), "mean": round(mean(v), 1)} if v else {"calls": 0, "median": None, "mean": None}
            for k, v in ((k, sizes[k]) for k in LINES_FOR)
        },
    }


def _cells(d: dict, runs: dict) -> str:
    return ", ".join(f"{s} {v}/{runs.get(s, 0)}" for s, v in d.items()) or "-"


def render(a: dict, runs_dir: Path) -> str:
    runs = a["runs_by_setup"]
    L = [
        "# ax exit audit", "",
        f"from `{Path(runs_dir).name}/runs.jsonl`: {a['runs']} non-dry held-out runs "
        f"({', '.join(f'{s} {n}' for s, n in runs.items())}), {a['commands']:,} shell commands, {a['ax_commands']:,} of them invoke ax.",
        "",
        ("a non-zero exit counts against ax only when the ax segment is the last one in the shell line, or the output "
         "starts with an ax-style error (`error:`, `ax:`, `<path>: stale anchor`, `... isn't`, `no such path`, "
         "`unexpected argument`, `nothing written (...)`), or an unambiguous ax refusal line shows up later in the output "
         "(the `&&` chain stopped there). two tweaks: an ax that's last but printed no ax error didn't fail (an earlier "
         "`&&` link did), and the subcommand is the ax segment the error line names. everything else is the other "
         "command's exit (tests, tsc, prettier). heredoc bodies aren't commands; what runs after the terminator is."),
        "",
        "## non-zero exits", "",
        f"- {a['ax_commands_nonzero']} commands that invoke ax exited non-zero.",
        f"- {a['blamed_on_ax']} are ax's: " + (", ".join(f"{v} {k}" for k, v in a["blamed_on_ax_by"].items()) or "none") + ".",
        f"- by setup: {', '.join(f'{s} {v}' for s, v in a['blamed_on_ax_by_setup'].items()) or '-'}.",
        f"- {a['blamed_on_later']} belong to another command ("
        + (", ".join(f"{v} {k}" for k, v in a["blamed_on_later_where"].items()) or "none") + "): "
        + (", ".join(f"`{k}` {v}" for k, v in a["later_commands"].items()) or "none") + ".",
        "",
        "## ax failures by subcommand and kind", "",
    ]
    if a["failures"]:
        head = ["subcommand", *KINDS, "total"]
        body = [[f"`{k}`", *[v.get(kd, 0) or "" for kd in KINDS], sum(v.values())] for k, v in a["failures"].items()]
        body.append(["**total**", *[sum(v.get(kd, 0) for v in a["failures"].values()) or "" for kd in KINDS], a["blamed_on_ax"]])
        L += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(map(str, b)) + " |" for b in body]
    else:
        L.append("no ax failures.")
    L.append("")

    L += ["## examples", ""]
    for kd, xs in a["examples"].items():
        L += [f"### {kd}", ""]
        for x in xs:
            L.append(f"- `{x['command']}`  ")
            L.append(f"  -> `{x['output']}` ({x['run_id']})")
        L.append("")

    g = a["ax_log"]
    L += [
        "## cross-check with ax's own log", "",
        ("`ax_log.jsonl` records every ax call that got past argument parsing (clap usage errors exit before it), "
         "including ones hidden inside a shell line that still exited 0 (`ax read missing; ax grep x`)."), "",
        f"- {g['nonzero']} ax calls exited non-zero: " + (", ".join(f"{k} {v}" for k, v in g["nonzero_by_cmd"].items()) or "none")
        + "; outcomes " + (", ".join(f"{k} {v}" for k, v in g["nonzero_by_outcome"].items()) or "none") + ".",
        f"- {g['corrupt']} of {g['lines']:,} log lines don't parse (parallel ax calls interleaving their appends).",
        "",
        "## habits", "",
        f"- first command of the run is `ax map`: {_cells(a['first_command_ax_map'], runs)}.",
        f"- first ax command of the run is `ax map`: {_cells(a['first_ax_command_ax_map'], runs)}.",
        f"- runs that call `ax find AGENTS.md`: {_cells(a['runs_with_ax_find_agents_md'], runs)}.",
        "",
        "## output size of successful calls", "",
        "lines of output for exit-0 calls where ax is the only command on the line.", "",
        "| subcommand | calls | median lines | mean lines |", "|---|---|---|---|",
    ]
    for k, v in a["output_lines"].items():
        L.append(f"| `ax {k}` | {v['calls']} | {'-' if v['median'] is None else v['median']} | {'-' if v['mean'] is None else v['mean']} |")
    L.append("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("runs", nargs="?", type=Path, default=RUNS)
    p.add_argument("--out", type=Path, default=REPORT / "ax_audit.md")
    a = p.parse_args(argv)
    res = audit(a.runs)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(render(res, a.runs))
    a.out.with_suffix(".json").write_text(json.dumps(res, indent=2) + "\n")
    print(f"wrote {a.out} ({res['runs']} runs, {res['blamed_on_ax']} ax failures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
