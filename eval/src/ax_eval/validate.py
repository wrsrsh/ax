"""validate candidates in docker: which hidden tests fail before and pass after.

per task: base + hidden tests once, gold + hidden tests three times (network
off, deps preinstalled in an image per lockfile). fail-to-pass = not passing
at base, passing in every gold run. pass-to-pass = passing everywhere. tasks
with no fail-to-pass tests (or only flaky ones) are dropped with a reason.

    uv run python -m ax_eval.validate --jobs 4
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ax_eval.mine import TASKS
from ax_eval.parity import EVAL

NODE_IMAGE = "node:24-bookworm"
GOLD_RUNS = 3


def sh(*cmd: str, check: bool = True, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True, check=check, **kw)


def lockfile(repo: Path, commit: str) -> tuple[str, bytes]:
    for name in ("pnpm-lock.yaml", "bun.lock"):
        b = subprocess.run(["git", "show", f"{commit}:{name}"], cwd=repo, capture_output=True).stdout
        if b:
            return name, b
    raise RuntimeError(f"no lockfile at {commit}")


def package_manager(repo: Path, commit: str) -> str:
    pj = json.loads(sh("git", "show", f"{commit}:package.json", cwd=repo).stdout)
    return pj.get("packageManager", "")


def ensure_image(repo: Path, commit: str) -> str:
    """an image with the repo cloned at /w and deps installed for `commit`.
    hono moved from bun to pnpm in 2026-09, so both are handled."""
    name, body = lockfile(repo, commit)
    tag = f"ax-hono-deps:{hashlib.sha256(body).hexdigest()[:12]}"
    if sh("docker", "image", "inspect", tag, check=False).returncode == 0:
        return tag
    pm = package_manager(repo, commit)
    if name == "bun.lock":
        version = pm.split("@", 1)[1] if pm.startswith("bun@") else "latest"
        install = f"npm i -g bun@{version} >/dev/null 2>&1 && bun install --frozen-lockfile >/dev/null"
    else:
        install = "corepack enable >/dev/null && CI=1 pnpm install --frozen-lockfile >/dev/null"
    box = f"ax-build-{tag.split(':')[1]}"
    sh("docker", "rm", "-f", box, check=False)
    sh(
        "docker", "run", "--name", box, "-v", f"{repo}:/src:ro", NODE_IMAGE, "bash", "-c",
        f"git config --global --add safe.directory '*' && git clone -q /src /w && cd /w && git checkout -q {commit} && {install}",
    )
    sh("docker", "commit", box, tag)
    sh("docker", "rm", box)
    return tag


def full_clone() -> Path:
    """docker needs a plain clone (the parity cache is blobless)."""
    d = EVAL / ".cache" / "hono-full"
    if not (d / ".git").exists():
        sh("git", "clone", "-q", "https://github.com/honojs/hono", str(d))
    return d


def runnable(test_files: list[str]) -> list[str]:
    return [f for f in test_files if f.startswith("src/") and ".test." in f]


def run_tests(
    image: str,
    base: str,
    patches: dict[str, str],
    files: list[str],
    reset: tuple[list[str], str] | None = None,
) -> dict[str, str] | str:
    """{test id: status}, or an error string if a patch didn't apply.
    patches apply in name order. `reset=(paths, before)` puts `paths` back to
    how they are at base (or removes them) right before patch `before`."""
    with tempfile.TemporaryDirectory() as tmp:
        for name, body in patches.items():
            Path(tmp, f"{name}.patch").write_text(body)
        steps = []
        for name in sorted(patches):
            if reset and name == reset[1]:
                for f in reset[0]:
                    q = shlex.quote(f)
                    steps.append(f"(git checkout -q {base} -- {q} 2>/dev/null || rm -f {q})")
            steps.append(f"git apply --whitespace=nowarn /p/{name}.patch || {{ echo 'APPLY_FAIL {name}'; exit 3; }}")
        script = (
            f"cd /w && git checkout -q -f {base} && git clean -fdq && "
            + " && ".join(steps or ["true"])
            + "; runner=node_modules/.bin/vitest; [ -x node_modules/.bin/vp ] && runner='node_modules/.bin/vp test'; "
            f"$runner --run --coverage.enabled=false --reporter=json --outputFile=/p/out.json {' '.join(map(shlex.quote, files))} >/dev/null 2>&1; true"
        )
        r = sh("docker", "run", "--rm", "--network", "none", "-v", f"{tmp}:/p", image, "bash", "-c", script, check=False)
        if r.returncode == 3:
            return "patch doesn't apply: " + r.stdout.strip().removeprefix("APPLY_FAIL ")
        out = Path(tmp, "out.json")
        if not out.exists():
            return "test run produced no report"
        return parse_report(json.loads(out.read_text()))


def parse_report(rep: dict) -> dict[str, str]:
    res: dict[str, str] = {}
    for f in rep.get("testResults", []):
        rel = f["name"].removeprefix("/w/")
        if not f.get("assertionResults"):
            res[f"{rel}::<file>"] = f.get("status", "failed")
        for a in f.get("assertionResults", []):
            res[f"{rel}::{a['fullName']}"] = a["status"]
    return res


def split(base: dict[str, str], golds: list[dict[str, str]]) -> tuple[list[str], list[str], list[str]]:
    """(fail_to_pass, pass_to_pass, flaky)"""
    ids = set(base) | set().union(*golds)
    f2p, p2p, flaky = [], [], []
    for t in sorted(ids):
        g = [x.get(t) for x in golds]
        if len(set(g)) > 1:
            flaky.append(t)
        elif g[0] == "passed":
            (p2p if base.get(t) == "passed" else f2p).append(t)
    return f2p, p2p, flaky


def validate(task: dict, repo: Path) -> dict:
    t0 = time.time()
    files = runnable(task["test_files"])
    if not files:
        return {**task, "dropped": "no vitest test files"}
    image = ensure_image(repo, task["base"])
    base = run_tests(image, task["base"], {"1-tests": task["test_patch"]}, files)
    if isinstance(base, str):
        return {**task, "dropped": base}
    golds = []
    for _ in range(GOLD_RUNS):
        g = run_tests(image, task["base"], {"1-gold": task["gold_patch"], "2-tests": task["test_patch"]}, files)
        if isinstance(g, str):
            return {**task, "dropped": g}
        golds.append(g)
    f2p, p2p, flaky = split(base, golds)
    out = {**task, "image": image, "test_run_files": files, "fail_to_pass": f2p, "pass_to_pass": p2p, "flaky": flaky, "validate_s": round(time.time() - t0, 1)}
    if not f2p:
        out["dropped"] = "no fail-to-pass tests" + (" (only flaky ones)" if flaky else "")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--only", nargs="*")
    a = p.parse_args(argv)
    repo = full_clone()
    cands = [json.loads(l) for l in open(TASKS / "candidates.jsonl")]
    if a.only:
        cands = [c for c in cands if c["id"] in a.only]
    # build images up front, serially; a base we can't build for drops its tasks
    broken = {}
    for base in {c["base"] for c in cands}:
        try:
            ensure_image(repo, base)
        except (RuntimeError, subprocess.CalledProcessError) as e:
            broken[base] = f"no image: {e}"[:200]

    def one(c: dict) -> dict:
        if c["base"] in broken:
            return {**c, "dropped": broken[c["base"]]}
        try:
            return validate(c, repo)
        except (RuntimeError, subprocess.CalledProcessError) as e:
            return {**c, "dropped": f"error: {e}"[:200]}

    done = []
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for i, r in enumerate(ex.map(one, cands), 1):
            print(f"[{i}/{len(cands)}] {r['id']}: {r.get('dropped') or f'ok f2p={len(r['fail_to_pass'])} p2p={len(r['pass_to_pass'])}'}", file=sys.stderr, flush=True)
            done.append(r)
    ok = [r for r in done if "dropped" not in r]
    bad = [r for r in done if "dropped" in r]
    with open(TASKS / "tasks.jsonl", "w") as f:
        for r in ok:
            f.write(json.dumps(r) + "\n")
    with open(TASKS / "dropped.jsonl", "w") as f:
        for r in bad:
            f.write(json.dumps({"id": r["id"], "reason": r["dropped"]}) + "\n")
    reasons: dict[str, int] = {}
    for r in bad:
        k = r["dropped"].split(":")[0]
        reasons[k] = reasons.get(k, 0) + 1
    print(json.dumps({"validated": len(ok), "dropped": reasons}), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
