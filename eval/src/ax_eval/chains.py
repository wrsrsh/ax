"""task chains for the long-session eval: 2-4 tasks from final.jsonl that can
run one after another in the same checkout, plus the world change to apply
between them.

no two tasks share a base, so a chain runs at an anchor: the base of its
earliest task (by pr). a chain is kept only if, in a container of the shared
task image, at the anchor: no task's fix is already in it, every gold patch
applies on top of the ones before it (and any upstream diff in between), and
every hidden test patch applies. `--validate` then reruns the hidden tests at
the anchor with the earlier golds in place and keeps each step's own
fail-to-pass / pass-to-pass lists; chains with a step that has no
fail-to-pass test are dropped.

world changes (one per gap, rotated by chain index):
  insert    comment blocks above the agent's earlier edits, at the top and mid-file
  fmt       prettier --print-width 60 over the chain's files and whatever the agent touched
  upstream  a later hono commit's src diff touching the files done so far (falls back to insert;
            never after a fmt in the same chain)

    uv run python -m ax_eval.chains --validate --jobs 4
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ax_eval.grade import patch_paths
from ax_eval.util import TASKS, jsonl, sh
from ax_eval.validate import GOLD_RUNS, run_tests, split

KINDS = ("insert", "fmt", "upstream")
PRINT_WIDTH = 60
MAX_UPSTREAM_LINES = 80
OUT = TASKS / "chains.jsonl"


def src_like(path: str) -> bool:
    return path.startswith("src/") and path.endswith((".ts", ".tsx")) and ".test." not in path


def chain_files(tasks: list[dict]) -> list[str]:
    return sorted({f for t in tasks for f in t["src_files"] if src_like(f)})


def shared(a: list[dict], b: list[dict]) -> int:
    return len(set(chain_files(a)) & set(chain_files(b)))


def kinds_for(index: int, n_tasks: int) -> list[str]:
    ks = [KINDS[(index + g) % len(KINDS)] for g in range(n_tasks - 1)]
    if "fmt" in ks and "upstream" in ks and ks.index("fmt") < ks.index("upstream"):
        # an upstream diff can't land on a tree prettier just rewrapped
        i, j = ks.index("fmt"), ks.index("upstream")
        ks[i], ks[j] = ks[j], ks[i]
    return ks


def check_script(anchor: str, chain: list[dict], ups: dict[int, str] | None = None) -> str:
    """bash for /w: prints OK, or FAIL <step> <what>. patches are at /p/<id>.gold etc."""
    ups = ups or {}
    q = shlex.quote
    lines = ["cd /w", f"git checkout -q -f {q(anchor)} && git clean -fdq || {{ echo 'FAIL - checkout'; exit 0; }}"]
    for i, t in enumerate(chain):
        lines.append(f"git merge-base --is-ancestor {q(t['commit'])} HEAD && {{ echo 'FAIL {i} fix-in-anchor'; exit 0; }}")
    for i, t in enumerate(chain):
        for f in patch_paths(t["test_patch"]):
            lines.append(f"(git checkout -q {q(anchor)} -- {q(f)} 2>/dev/null || rm -f {q(f)})")
        lines.append(f"git apply --check /p/{t['id']}.test || {{ echo 'FAIL {i} test'; exit 0; }}")
        lines.append(f"git apply /p/{t['id']}.gold || {{ echo 'FAIL {i} gold'; exit 0; }}")
        if i in ups:
            lines.append(f"git apply /p/up-{ups[i]}.patch || {{ echo 'FAIL {i} upstream'; exit 0; }}")
    lines.append("echo OK")
    return "\n".join(lines) + "\n"


class Box:
    """a throwaway container of a task image (no network) with /p mounted from the host."""

    def __init__(self, image: str):
        self.image = image

    def __enter__(self) -> Box:
        self.tmp = Path(tempfile.mkdtemp(prefix="ax-chain-"))
        self.tmp.chmod(0o777)
        self.name = f"ax-chain-{self.tmp.name.split('-')[-1]}"
        sh("docker", "run", "-d", "--rm", "--name", self.name, "--network", "none", "-v", f"{self.tmp}:/p",
           "--entrypoint", "sleep", self.image, "infinity")
        return self

    def __exit__(self, *exc) -> None:
        sh("docker", "rm", "-f", self.name, check=False)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, name: str, text: str) -> None:
        p = self.tmp / name
        if not p.exists():
            p.write_text(text)

    def run(self, script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["docker", "exec", "-i", self.name, "bash", "-s"], input=script, capture_output=True, text=True)


def check(box: Box, chain: list[dict], ups: dict[int, str] | None = None, patches: dict[str, str] | None = None) -> str | None:
    """None if the chain works at its anchor, else why not."""
    for t in chain:
        box.put(f"{t['id']}.gold", t["gold_patch"])
        box.put(f"{t['id']}.test", t["test_patch"])
    for sha, body in (patches or {}).items():
        box.put(f"up-{sha}.patch", body)
    out = box.run(check_script(chain[0]["base"], chain, ups)).stdout.strip().splitlines()
    last = out[-1] if out else "FAIL - no output"
    return None if last == "OK" else last.removeprefix("FAIL ")


def by_pr(tasks: list[dict]) -> list[dict]:
    return sorted(tasks, key=lambda t: t["pr"])


def greedy(tasks: list[dict], ok, max_len: int = 4) -> list[list[dict]]:
    """disjoint chains, pr-ordered. `ok(chain)` says whether a candidate works.
    pairs sharing source files go first; each chain grows while it can."""
    ts = by_pr(tasks)
    pairs = [(a, b) for i, a in enumerate(ts) for b in ts[i + 1 :]]
    pairs.sort(key=lambda p: (-shared([p[0]], [p[1]]), p[1]["pr"] - p[0]["pr"]))
    good = {(a["id"], b["id"]) for a, b in pairs if ok([a, b])}
    used: set[str] = set()
    chains = []
    for a, b in pairs:
        if a["id"] in used or b["id"] in used or (a["id"], b["id"]) not in good:
            continue
        chain = [a, b]
        while len(chain) < max_len:
            cands = [c for c in ts if c["id"] not in used and c not in chain and c["pr"] > chain[0]["pr"]
                     and all(tuple(x["id"] for x in by_pr([x, c])) in good for x in chain)]
            cands.sort(key=lambda c: (-shared(chain, [c]), c["pr"] - chain[-1]["pr"]))
            for c in cands:
                trial = by_pr(chain + [c])
                if ok(trial):
                    chain = trial
                    break
            else:
                break
        used |= {t["id"] for t in chain}
        chains.append(chain)
    return chains


def upstream_candidates(box: Box, chain: list[dict], upto: int) -> list[tuple[str, list[str]]]:
    """later hono commits (not a chain fix) touching the src files of steps <= upto,
    smallest first, as (sha, src files it touches)."""
    files = chain_files(chain[: upto + 1])
    fixes = {t["commit"] for t in chain}
    script = (
        f"cd /w; git rev-list --all --no-merges ^{shlex.quote(chain[0]['base'])} -- {' '.join(map(shlex.quote, files))}"
        " | while read c; do echo \"C $c\"; git diff --numstat $c^ $c; done"
    )
    out: dict[str, list[tuple[str, int]]] = {}
    cur = None
    for line in box.run(script).stdout.splitlines():
        if line.startswith("C "):
            cur = line[2:].strip()
            out[cur] = []
        elif cur and line.count("\t") == 2:
            add, rem, path = line.split("\t")
            if add != "-" and src_like(path):
                out[cur].append((path, int(add) + int(rem)))
    cands = [(c, [p for p, _ in fs], sum(n for _, n in fs)) for c, fs in out.items() if c not in fixes and fs]
    cands = [c for c in cands if c[2] <= MAX_UPSTREAM_LINES and set(c[1]) & set(files)]
    cands.sort(key=lambda c: (-len(set(c[1]) & set(chain_files(chain[upto : upto + 1]))), c[2]))
    return [(c, fs) for c, fs, _ in cands]


def upstream_patch(box: Box, sha: str, files: list[str]) -> str:
    return box.run(f"cd /w; git diff --binary {sha}^ {sha} -- {' '.join(map(shlex.quote, files))}").stdout


def world_changes(box: Box, chain: list[dict], index: int, tries: int = 25) -> list[dict]:
    """one world change per gap; upstream picks the first candidate that keeps the chain applying."""
    files = chain_files(chain)
    out = []
    ups: dict[int, str] = {}
    patches: dict[str, str] = {}
    for g, kind in enumerate(kinds_for(index, len(chain))):
        wc: dict = {"after": g, "kind": kind, "files": files}
        if kind == "fmt":
            wc["print_width"] = PRINT_WIDTH
        if kind == "upstream":
            for sha, fs in upstream_candidates(box, chain, g)[:tries]:
                body = upstream_patch(box, sha, fs)
                if body.strip() and check(box, chain, {**ups, g: sha}, {**patches, sha: body}) is None:
                    ups[g], patches[sha] = sha, body
                    wc.update(commit=sha, touches=fs, patch=body)
                    break
            else:
                wc.update(kind="insert", fallback_from="upstream")
        out.append(wc)
    return out


def reference_patches(chain: list[dict], wcs: list[dict], k: int, golds: int, ups_before: int) -> dict[str, str]:
    """patches (in name order) for a reference state of step k: the first `golds`
    gold patches with the upstream diffs after steps < ups_before in between, then
    step k's hidden tests. insert/fmt changes are left out: they don't change behaviour.
    step k before the fix: (k, k). after: (k + 1, k). end of the chain: (n, n - 1)."""
    ups = {w["after"]: w["patch"] for w in wcs if w["kind"] == "upstream"}
    p = {}
    for i in range(golds):
        p[f"{i:02d}a-gold"] = chain[i]["gold_patch"]
        if i in ups and i < ups_before:
            p[f"{i:02d}b-upstream"] = ups[i]
    p["99-tests"] = chain[k]["test_patch"]
    return p


def validate_step(chain: list[dict], wcs: list[dict], k: int) -> dict:
    """step k's own fail-to-pass / pass-to-pass at the anchor with the earlier golds in,
    plus which of them still pass once the whole chain is in (`at_end`, what regressions are checked on)."""
    t, n = chain[k], len(chain)
    anchor = chain[0]["base"]
    reset = (patch_paths(t["test_patch"]), "99-tests")

    def run(golds: int, ups_before: int):
        return run_tests(t["image"], anchor, reference_patches(chain, wcs, k, golds, ups_before), t["test_run_files"], reset=reset)

    base = run(k, k)
    gold_runs = [run(k + 1, k) for _ in range(GOLD_RUNS)]
    end = run(n, n - 1) if k < n - 1 else None
    for r in (base, *gold_runs, end):
        if isinstance(r, str):
            return {"task": t["id"], "error": r, "fail_to_pass": [], "pass_to_pass": [], "flaky": [], "at_end": []}
    f2p, p2p, flaky = split(base, gold_runs)
    at_end = f2p + p2p if end is None else [x for x in f2p + p2p if end.get(x) == "passed"]
    return {"task": t["id"], "error": None, "fail_to_pass": f2p, "pass_to_pass": p2p, "flaky": flaky, "at_end": at_end}


def record(i: int, chain: list[dict], wcs: list[dict]) -> dict:
    return {
        "id": f"chain-{i:02d}",
        "image": chain[0]["image"],
        "anchor": chain[0]["base"],
        "tasks": [t["id"] for t in chain],
        "files": chain_files(chain),
        "shared_files": sorted(f for f in chain_files(chain) if sum(f in t["src_files"] for t in chain) > 1),
        "world_changes": wcs,
        "steps": [{"task": t["id"], "fail_to_pass": t["fail_to_pass"], "pass_to_pass": t["pass_to_pass"], "flaky": [], "at_end": []} for t in chain],
        "validated": False,
    }


def build(tasks: list[dict], max_len: int = 4, jobs: int = 4, log=print) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for t in tasks:
        groups.setdefault(t["image"], []).append(t)

    def one(image: str) -> list[list[dict]]:
        with Box(image) as box:
            chains = greedy(groups[image], lambda c: check(box, c) is None, max_len)
            log(f"{image}: {len(groups[image])} tasks -> chains of {[len(c) for c in chains]}")
            return chains

    with cf.ThreadPoolExecutor(jobs) as ex:
        found = sorted((c for cs in ex.map(one, sorted(groups)) for c in cs), key=lambda c: c[0]["pr"])

    def wc(item: tuple[int, list[dict]]) -> dict:
        i, chain = item
        with Box(chain[0]["image"]) as box:
            return record(i, chain, world_changes(box, chain, i))

    with cf.ThreadPoolExecutor(jobs) as ex:
        return list(ex.map(wc, enumerate(found)))


def validate(recs: list[dict], tasks: dict[str, dict], jobs: int = 4, log=print) -> tuple[list[dict], list[list[dict]]]:
    """(chains whose every step has fail-to-pass tests, leftovers of the rest worth retrying as a shorter chain)"""
    jobs_list = [(r, k) for r in recs for k in range(len(r["tasks"]))]

    def one(item):
        r, k = item
        return validate_step([tasks[i] for i in r["tasks"]], r["world_changes"], k)

    with cf.ThreadPoolExecutor(jobs) as ex:
        results = list(ex.map(one, jobs_list))
    kept, rest = [], []
    for r in recs:
        steps = [s for (rr, _), s in zip(jobs_list, results) if rr is r]
        r = {**r, "steps": steps, "validated": True}
        bad = [s for s in steps if s["error"] or not s["fail_to_pass"]]
        log(f"{r['id']} {r['tasks']}: " + ("ok" if not bad else "dropped: " + "; ".join(f"{s['task']} {s['error'] or 'no f2p'}" for s in bad)))
        if not bad:
            kept.append(r)
        elif len(steps) - len(bad) >= 2:
            rest.append([tasks[s["task"]] for s in steps if s not in bad])
    return kept, rest


def salvage(rest: list[list[dict]], tasks: dict[str, dict], jobs: int, log=print) -> list[dict]:
    """a chain that lost a step, minus that step, rechecked and revalidated once."""
    recs = []
    for i, chain in enumerate(rest):
        with Box(chain[0]["image"]) as box:
            if check(box, chain) is None:
                recs.append(record(100 + i, chain, world_changes(box, chain, i)))
    return validate(recs, tasks, jobs, log)[0]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--max-len", type=int, default=4)
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--validate", action="store_true", help="rerun hidden tests per step at the anchor (slow, $0)")
    p.add_argument("--out", type=Path, default=OUT)
    a = p.parse_args(argv)
    tasks = jsonl(TASKS / "final.jsonl")

    def log(s: str) -> None:
        print(s, file=sys.stderr, flush=True)

    recs = build(tasks, a.max_len, a.jobs, log)
    if a.validate:
        by_id = {t["id"]: t for t in tasks}
        recs, rest = validate(recs, by_id, a.jobs, log)
        recs += salvage(rest, by_id, a.jobs, log)
        recs.sort(key=lambda r: by_id[r["tasks"][0]]["pr"])
        recs = [{**r, "id": f"chain-{i:02d}"} for i, r in enumerate(recs)]
    with open(a.out, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    lens = [len(r["tasks"]) for r in recs]
    log(json.dumps({"chains": len(recs), "tasks": sum(lens), "lengths": {n: lens.count(n) for n in sorted(set(lens))},
                    "world_changes": {k: sum(w["kind"] == k for r in recs for w in r["world_changes"]) for k in KINDS}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
