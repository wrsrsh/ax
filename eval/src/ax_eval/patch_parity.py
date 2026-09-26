"""replay real commits through `ax patch` and check the tree matches.

for each of the last N non-merge commits of a repo: check out the parent,
feed `git diff parent commit` to `ax patch` (as a unified diff, and again
converted to Codex `*** Begin Patch` format), and compare the result with
the commit's tree. `git apply` on the same diff is the control.

    uv run python -m ax_eval.patch_parity --n 40
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from ax_eval.parity import REPOS, checkout
from ax_eval.util import REPORT, ROOT


# bytes on purpose: diffs go to git apply and ax patch exactly as git printed them
def git(d: Path, *args: str, input: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=d, input=input, capture_output=True, check=check)


def to_codex(diff: str) -> str:
    """unified diff (as git prints it) -> Codex apply_patch format."""
    out = ["*** Begin Patch"]
    files = diff.split("\ndiff --git ")
    for i, f in enumerate(files):
        body = f if i == 0 else "diff --git " + f
        src = dst = None
        rename_from = rename_to = None
        hunks: list[str] = []
        in_hunk = False
        for l in body.splitlines():
            if l.startswith("rename from "):
                rename_from = l[12:]
            elif l.startswith("rename to "):
                rename_to = l[10:]
            elif l.startswith("--- ") and not in_hunk:
                src = None if l[4:] == "/dev/null" else l[6:]
            elif l.startswith("+++ ") and not in_hunk:
                dst = None if l[4:] == "/dev/null" else l[6:]
            elif l.startswith("@@"):
                in_hunk = True
                hunks.append("@@")
            elif in_hunk and l[:1] in (" ", "+", "-"):
                hunks.append(l)
        if src is None and dst is not None:
            out.append(f"*** Add File: {dst}")
            out += [h for h in hunks if h.startswith("+")]
        elif dst is None and src is not None:
            out.append(f"*** Delete File: {src}")
        elif src or rename_from:
            path = src or rename_from
            out.append(f"*** Update File: {path}")
            target = rename_to or (dst if dst != path else None)
            if target:
                out.append(f"*** Move to: {target}")
            out += hunks
    out.append("*** End Patch")
    return "\n".join(out) + "\n"


def tree_matches(d: Path, commit: str) -> bool:
    git(d, "add", "-A")
    return git(d, "diff", "--cached", "--quiet", commit, check=False).returncode == 0


def reset(d: Path, rev: str) -> None:
    git(d, "reset", "-q", "--hard", rev)
    git(d, "clean", "-qfdx")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ax", default=str(ROOT / "ax/target/release/ax"))
    p.add_argument("--repo", default="hono")
    p.add_argument("--n", type=int, default=40)
    a = p.parse_args(argv)
    repo = next(r for r in REPOS if r.name == a.repo)
    d = checkout(repo)
    head = git(d, "rev-parse", "HEAD").stdout.decode().strip()
    commits = git(d, "rev-list", "--no-merges", f"--max-count={a.n * 2}", head).stdout.decode().split()
    rows = []
    for c in commits:
        if len(rows) >= a.n:
            break
        parent = f"{c}^"
        diff = git(d, "diff", "-M", "--no-color", parent, c).stdout
        if b"Binary files" in diff or b"GIT binary patch" in diff or not diff.strip():
            continue
        row = {"commit": c[:10], "bytes": len(diff)}
        for mode, payload in [("git-apply", diff), ("ax-unified", diff), ("ax-codex", to_codex(diff.decode()).encode())]:
            reset(d, parent)
            if mode == "git-apply":
                r = git(d, "apply", "--whitespace=nowarn", "-", input=payload, check=False)
            else:
                r = subprocess.run([a.ax, "patch"], cwd=d, input=payload, capture_output=True)
            ok = r.returncode == 0 and tree_matches(d, c)
            row[mode] = ok
            if not ok:
                row[f"{mode}-err"] = r.stderr.decode(errors="replace")[:300]
        rows.append(row)
    reset(d, head)
    summary = {m: sum(r[m] for r in rows) for m in ("git-apply", "ax-unified", "ax-codex")}
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "patch_parity.json").write_text(json.dumps({"repo": repo.name, "n": len(rows), "ok": summary, "rows": rows}, indent=2))
    print(json.dumps({"n": len(rows), "ok": summary}), file=sys.stderr)
    for r in rows:
        for m in ("ax-unified", "ax-codex"):
            if not r[m]:
                print(f"FAIL {m} {r['commit']}: {r.get(m + '-err', '')!r}", file=sys.stderr)
    return 0 if summary["ax-unified"] == summary["git-apply"] == summary["ax-codex"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
