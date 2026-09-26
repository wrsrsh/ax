"""mine SWE-bench-style task candidates from a repo's merged PRs.

a candidate is a merged PR whose diff touches 1-5 source files and at least
one test file, and nothing dependency-ish. the source part becomes the gold
patch, the test part the hidden tests.

    uv run python -m ax_eval.mine --since 2026-06-01
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from ax_eval.parity import EVAL, REPOS, checkout

TASKS = EVAL / "tasks"

TEST_RE = re.compile(r"(^|/)(tests?|__tests__|runtime-tests)/|\.(test|spec)\.[cm]?[jt]sx?$|(^|/)test_[^/]*\.py$|_test\.(py|go)$")
SOURCE_RE = re.compile(r"\.(ts|tsx|mts|cts|js|jsx|mjs|cjs|py|rs|go)$")
EXCLUDED_RE = re.compile(
    r"(^|/)(docs?|benchmarks?|perf-measures|examples?|\.github)/|(^|/)(package\.json|jsr\.json|deno\.json|pnpm-lock\.yaml|package-lock\.json|yarn\.lock|bun\.lockb?)$|\.config\.[cm]?[jt]s$|\.d\.ts$"
)
DEPENDENCY_RE = re.compile(r"(^|/)(package\.json|pnpm-lock\.yaml|package-lock\.json|yarn\.lock|bun\.lockb?|Cargo\.lock|go\.sum|uv\.lock)$")
BOTS = re.compile(r"(\[bot\]$|^app/|bot$|renovate|dependabot)", re.I)


def classify(path: str) -> str:
    """'test', 'source', 'dependency' or 'other'."""
    if DEPENDENCY_RE.search(path):
        return "dependency"
    if TEST_RE.search(path):
        return "test"
    if EXCLUDED_RE.search(path):
        return "other"
    if SOURCE_RE.search(path):
        return "source"
    return "other"


def qualifies(files: list[str]) -> tuple[bool, str]:
    kinds = [classify(f) for f in files]
    src = kinds.count("source")
    if "dependency" in kinds:
        return False, "touches dependencies"
    if kinds.count("test") == 0:
        return False, "no test changes"
    if not 1 <= src <= 5:
        return False, f"{src} source files"
    return True, ""


def gh_json(args: list[str]) -> list | dict:
    out = subprocess.run(["gh", *args], capture_output=True, check=True, text=True).stdout
    return json.loads(out)


def git(d: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=d, capture_output=True, check=True, text=True).stdout


def mine(repo_name: str, slug: str, since: str, limit: int) -> tuple[list[dict], dict[str, int]]:
    d = checkout(next(r for r in REPOS if r.name == repo_name))
    prs = gh_json(
        [
            "pr", "list", "-R", slug, "--state", "merged", "--limit", str(limit),
            "--search", f"merged:>={since}",
            "--json", "number,title,body,author,mergeCommit,mergedAt,files,closingIssuesReferences",
        ]
    )
    reasons: dict[str, int] = {}
    out = []
    for pr in sorted(prs, key=lambda p: p["mergedAt"]):
        why = ""
        author = (pr.get("author") or {}).get("login", "")
        files = [f["path"] for f in pr.get("files", [])]
        commit = (pr.get("mergeCommit") or {}).get("oid")
        if BOTS.search(author):
            why = "bot author"
        elif not commit:
            why = "no merge commit"
        else:
            ok, why = qualifies(files)
        if not why:
            try:
                base = git(d, "rev-parse", f"{commit}^").strip()
            except subprocess.CalledProcessError:
                why = "commit not in local clone"
        if why:
            reasons[why] = reasons.get(why, 0) + 1
            continue
        src = [f for f in files if classify(f) == "source"]
        tests = [f for f in files if classify(f) == "test"]
        issues = []
        for ref in pr.get("closingIssuesReferences") or []:
            try:
                i = gh_json(["issue", "view", str(ref["number"]), "-R", slug, "--json", "number,title,body"])
                issues.append(i)
            except subprocess.CalledProcessError:
                pass
        out.append(
            {
                "id": f"{repo_name}-{pr['number']}",
                "repo": slug,
                "pr": pr["number"],
                "title": pr["title"],
                "body": pr.get("body") or "",
                "issues": issues,
                "merged_at": pr["mergedAt"],
                "commit": commit,
                "base": base,
                "src_files": src,
                "test_files": tests,
                "gold_patch": git(d, "diff", "--no-color", base, commit, "--", *src),
                "test_patch": git(d, "diff", "--no-color", base, commit, "--", *tests),
            }
        )
    return out, reasons


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", default="hono")
    p.add_argument("--slug", default="honojs/hono")
    p.add_argument("--since", default="2026-06-01")
    p.add_argument("--limit", type=int, default=500)
    a = p.parse_args(argv)
    cands, reasons = mine(a.repo, a.slug, a.since, a.limit)
    TASKS.mkdir(parents=True, exist_ok=True)
    with open(TASKS / "candidates.jsonl", "w") as f:
        for c in cands:
            f.write(json.dumps(c) + "\n")
    print(json.dumps({"candidates": len(cands), "skipped": reasons}), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
