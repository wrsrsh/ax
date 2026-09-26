"""parity: does `ax find` / `ax grep` return exactly what `rg --files` / `rg` do?

clones a handful of real repos at pinned commits, runs a matrix of patterns
and flags through both tools, and diffs the result sets. writes
eval/report/parity.json + parity.md. then (optionally) times both with
hyperfine and saves hyperfine's raw json untouched.

    uv run python -m ax_eval.parity            # parity only
    uv run python -m ax_eval.parity --bench    # + hyperfine
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ax_eval.util import EVAL, REPORT, ROOT

CACHE = EVAL / ".cache" / "parity-repos"


@dataclass(frozen=True)
class Repo:
    name: str
    url: str
    commit: str  # pinned; "HEAD" means the ax repo itself as checked out


REPOS = [
    Repo("hono", "https://github.com/honojs/hono", "ee0622e14487444211942eec2f6ab7ccede4c6af"),
    Repo("ripgrep", "https://github.com/BurntSushi/ripgrep", "3fce3b5bb0236da2df6d99672afb8a719642eca7"),
    Repo("requests", "https://github.com/psf/requests", "611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60"),
    Repo("cobra", "https://github.com/spf13/cobra", "adbc8813901bba65827259daa8e22ff94ec1f30e"),
    Repo("ax", str(ROOT), "HEAD"),
]

# every case runs on every repo. patterns are generic on purpose.
GREP_CASES: list[list[str]] = [
    ["TODO"],
    ["-i", "error"],
    ["-w", "self"],
    ["-w", "c"],
    ["-F", "()"],
    ["-F", "."],
    [r"return\s+\w+"],
    [r"^\s*(pub )?fn "],
    ["-S", "Err"],
    ["-S", "err"],
    ["-g", "*.md", "the"],
    ["-g", "!*.md", "the"],
    ["-t", "rust", "impl"],
    ["-t", "py", "def"],
    ["-t", "go", "func"],
    ["-t", "ts", "export"],
    ["-C", "2", "TODO"],
    ["nothing-should-ever-match-this-zq9"],
]
LIST_CASES: list[list[str]] = [["-l", "test"], ["-c", "test"]]
FIND_GLOBS: list[str | None] = [None, "*.md", "**/*test*", "!*.md"]

# hyperfine commands (ax default output vs rg; both write to /dev/null)
BENCH: list[tuple[str, list[str], list[str]]] = [
    ("files", ["find"], ["--files"]),
    ("grep literal", ["grep", "-F", "return"], ["-F", "return"]),
    ("grep regex", ["grep", r"fn\s+\w+|def\s+\w+|func\s+\w+"], [r"fn\s+\w+|def\s+\w+|func\s+\w+"]),
    ("grep -i word", ["grep", "-i", "-w", "error"], ["-i", "-w", "error"]),
]


@dataclass
class CaseResult:
    repo: str
    tool: str
    args: list[str]
    rg_count: int
    ax_count: int
    only_rg: list[str] = field(default_factory=list)
    only_ax: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.only_rg and not self.only_ax


def sh(cmd: list[str], cwd: Path, env: dict | None = None, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        stdin=subprocess.DEVNULL,  # rg reads stdin when it isn't a tty
        capture_output=True,
        check=check,
    )


def checkout(repo: Repo) -> Path:
    if repo.commit == "HEAD":
        return Path(repo.url)
    dest = CACHE / repo.name
    if not (dest / ".git").exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        sh(["git", "clone", "-q", "--filter=blob:none", repo.url, str(dest)], CACHE, check=True)
    have = sh(["git", "rev-parse", "HEAD"], dest).stdout.decode().strip()
    if have != repo.commit:
        sh(["git", "checkout", "-q", "--detach", repo.commit], dest, check=True)
    return dest


def parse_rg_lines(out: str) -> set[str]:
    """`path:line:text` -> {"path:line"}; strips a leading ./"""
    pairs = set()
    for l in out.splitlines():
        parts = l.split(":", 2)
        if len(parts) >= 2 and parts[1].isdigit():
            pairs.add(f"{parts[0].removeprefix('./')}:{parts[1]}")
    return pairs


def parse_ax_hits(out: str) -> set[str]:
    data = json.loads(out)["data"]
    return {f"{h['path']}:{h['line']}" for h in data if not h.get("context")}


def compare(repo: str, tool: str, args: list[str], rg: set[str], ax: set[str]) -> CaseResult:
    return CaseResult(
        repo=repo,
        tool=tool,
        args=args,
        rg_count=len(rg),
        ax_count=len(ax),
        only_rg=sorted(rg - ax)[:20],
        only_ax=sorted(ax - rg)[:20],
    )


def run_parity(ax_bin: Path, repos: list[Repo]) -> list[CaseResult]:
    nocap = {"AX_NO_CAPS": "1"}
    results = []
    for repo in repos:
        d = checkout(repo)
        print(f"== {repo.name} @ {repo.commit[:10]}", file=sys.stderr)
        for g in FIND_GLOBS:
            rg_args = ["--files", "."] + (["-g", g] if g else [])
            ax_args = ["--json", "find"] + ([g] if g else [])
            rg = {l.removeprefix("./") for l in sh(["rg", *rg_args], d).stdout.decode().splitlines()}
            ax = set(json.loads(sh([str(ax_bin), *ax_args], d, nocap).stdout)["data"]["files"])
            results.append(compare(repo.name, "find", [g] if g else [], rg, ax))
        for args in GREP_CASES:
            rg_out = sh(["rg", "-n", "--no-heading", "--with-filename", "--color", "never", *args, "."], d)
            ax_out = sh([str(ax_bin), "--json", "grep", *args], d, nocap)
            if ax_out.returncode != 0:
                # e.g. a -t type that doesn't exist; rg errors too, so compare errors
                ok = rg_out.returncode == 2
                results.append(CaseResult(repo.name, "grep", args, -1, -1, [] if ok else ["ax errored"], []))
                continue
            results.append(
                compare(repo.name, "grep", args, parse_rg_lines(rg_out.stdout.decode(errors="replace")), parse_ax_hits(ax_out.stdout))
            )
        for args in LIST_CASES:
            rg = {l.removeprefix("./") for l in sh(["rg", "--color", "never", *args, "."], d).stdout.decode(errors="replace").splitlines()}
            ax_json = json.loads(sh([str(ax_bin), "--json", "grep", *args], d, nocap).stdout)["data"]
            if "-c" in args:
                ax = {f"{r['path']}:{r['count']}" for r in ax_json}
            else:
                ax = {r["path"] for r in ax_json}
            results.append(compare(repo.name, "grep", args, rg, ax))
    return results


def run_bench(ax_bin: Path, repos: list[Repo], out_dir: Path) -> list[dict]:
    hf = shutil.which("hyperfine") or str(Path.home() / ".cargo/bin/hyperfine")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for repo in repos:
        d = checkout(repo)
        for label, ax_args, rg_args in BENCH:
            slug = f"{repo.name}-{label.replace(' ', '-')}"
            export = out_dir / f"{slug}.json"
            sh(
                [
                    hf,
                    "--warmup", "3",
                    "--min-runs", "10",
                    "--style", "none",
                    "--export-json", str(export),
                    "-n", "ax", f"{ax_bin} {shlex.join(ax_args)} > /dev/null",
                    "-n", "rg", f"rg {shlex.join(rg_args)} . < /dev/null > /dev/null",
                ],
                d,
                check=True,
            )
            res = {r["command"]: r for r in json.loads(export.read_text())["results"]}
            rows.append(
                {
                    "repo": repo.name,
                    "case": label,
                    "ax_mean_ms": res["ax"]["mean"] * 1000,
                    "ax_stddev_ms": res["ax"]["stddev"] * 1000,
                    "rg_mean_ms": res["rg"]["mean"] * 1000,
                    "rg_stddev_ms": res["rg"]["stddev"] * 1000,
                    "raw": str(export.relative_to(EVAL)),
                }
            )
    return rows


def markdown(results: list[CaseResult], bench: list[dict], versions: dict) -> str:
    lines = ["# parity: ax vs rg", ""]
    lines += [f"- {k}: {v}" for k, v in versions.items()]
    bad = [r for r in results if not r.ok]
    lines += ["", f"**{len(results) - len(bad)}/{len(results)} cases identical.**", ""]
    lines += ["| repo | tool | args | rg | ax | ok |", "|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r.repo} | {r.tool} | `{' '.join(r.args) or '(all)'}` | {r.rg_count} | {r.ax_count} | {'yes' if r.ok else '**NO**'} |")
    for r in bad:
        lines += ["", f"### diff: {r.repo} {r.tool} {' '.join(r.args)}", f"only rg: {r.only_rg}", f"only ax: {r.only_ax}"]
    if bench:
        lines += ["", "## hyperfine (mean ± stddev, ms; raw json alongside)", "", "| repo | case | ax | rg |", "|---|---|---|---|"]
        for b in bench:
            lines.append(
                f"| {b['repo']} | {b['case']} | {b['ax_mean_ms']:.1f} ± {b['ax_stddev_ms']:.1f} | {b['rg_mean_ms']:.1f} ± {b['rg_stddev_ms']:.1f} |"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ax", default=str(ROOT / "ax/target/release/ax"))
    p.add_argument("--bench", action="store_true")
    p.add_argument("--repos", nargs="*", help="subset by name")
    a = p.parse_args(argv)
    ax_bin = Path(a.ax)
    repos = [r for r in REPOS if not a.repos or r.name in a.repos]
    versions = {
        "ax": sh([str(ax_bin), "--version"], ROOT).stdout.decode().strip(),
        "ax commit": sh(["git", "rev-parse", "--short", "HEAD"], ROOT).stdout.decode().strip(),
        "rg": sh(["rg", "--version"], ROOT).stdout.decode().splitlines()[0],
        "repos": ", ".join(f"{r.name}@{r.commit[:10]}" for r in repos),
    }
    results = run_parity(ax_bin, repos)
    bench = run_bench(ax_bin, repos, REPORT / "hyperfine") if a.bench else []
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "parity.json").write_text(
        json.dumps(
            {"versions": versions, "cases": [r.__dict__ | {"ok": r.ok} for r in results], "bench": bench},
            indent=2,
        )
    )
    (REPORT / "parity.md").write_text(markdown(results, bench, versions))
    bad = [r for r in results if not r.ok]
    print(f"{len(results) - len(bad)}/{len(results)} cases identical", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
