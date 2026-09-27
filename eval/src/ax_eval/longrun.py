"""long-session runs: one chain of tasks (tasks/chains.jsonl) in one codex thread
and one container, with the world changing between tasks.

    uv run python -m ax_eval.longrun --chains all --setups A B --agent stub
    uv run python -m ax_eval.longrun --chains chain-00 --setups B --agent codex --dry-run   # fake api
    uv run python -m ax_eval.longrun --chains all --setups A B --repeats 2 --plan-only
    uv run python -m ax_eval.longrun --summarize

step 0 is `codex exec`, every later step `codex exec resume <thread>` with the
next task's instruction, so the model keeps whatever it remembers of the files.
between steps the chain's world change is applied to the checkout (insert,
fmt or upstream, see chains.py). with --jolt the harness also inserts lines
into a task file right after the agent first reads it, mid-step.

each step gets runs-long/<run-id>/step<k>/ with events.jsonl, stderr.log,
ax_log.jsonl, final.diff (everything vs the anchor), delta.diff (just this
step, world changes excluded), world.json, grade.json and metrics.json.
grading takes the cumulative diff into a fresh container (grade.grade, hidden
tests win), so nothing a later step does can touch an earlier step's grade.
at the end every earlier task is graded again on the final diff to catch
edits that got clobbered. ledger rows go to runs/ledger.jsonl (one per step,
tagged with `chain`) so the $2,000 cap covers both benchmarks.
"""

from __future__ import annotations

import argparse
import bisect
import concurrent.futures as cf
import json
import os
import re
import secrets
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from ax_eval.chains import OUT as CHAINS
from ax_eval.chains import PRINT_WIDTH, src_like
from ax_eval.fakeapi import Script, serve
from ax_eval.grade import grade, patch_paths
from ax_eval.images import agent_image
from ax_eval.parse import cost, kinds, metrics
from ax_eval.runner import (
    BUDGET, CATALOG, EFFORT, FAKE_KEY, LEDGER, MODEL, SCRIPTS, Budget, BudgetExceeded, bridge_ip, describe, docker, drive,
    est_from_ledger, image_versions, infra_reason, ledger_row, load_prices, now, plan, probe, read_ledger, spent,
    start_container, write_manifest,
)
from ax_eval.setups import SETUPS, codex_args, uses_ax
from ax_eval.util import EVAL, TASKS, jsonl

LONG = EVAL / "runs-long"
EST_STEP = 1.0  # $ per step prior until the ledger has paid chain steps
SLACK = 15
FILLER = [
    "// ----------------------------------------------------------------------",
    "// shared with the other runtime adapters, keep the exports stable.",
    "// ----------------------------------------------------------------------",
]
TOP = re.compile(r"^(export |import |const |let |var |function |async function |class |abstract class |type |interface |enum |declare |/\*\*)")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
READS = ("ax read", "cat", "head", "tail", "sed", "nl", "awk")
USAGE = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "uncached_input_tokens", "output_tokens", "reasoning_tokens")


class StepFailed(RuntimeError):
    pass


def new_run_id(chain_id: str, setup: str, rep: int) -> str:
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{chain_id}-{setup}-r{rep}-{secrets.token_hex(2)}"


# ---- pure bits


def norm(s: str) -> str:
    """what survives a reformat: letters, digits, _ and $."""
    return re.sub(r"[^A-Za-z0-9_$]", "", s)


def hunks(diff: str) -> list[dict]:
    """unified diff -> [{path, old_start, old_len, new_start, new_len, removed, added, old}]"""
    out: list[dict] = []
    old_path = path = None
    cur = None
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            old_path = path = cur = None
        elif line.startswith("--- ") and cur is None:
            old_path = line[4:].removeprefix("a/")
        elif line.startswith("+++ ") and cur is None:
            p = line[4:]
            path = old_path if p == "/dev/null" else p.removeprefix("b/")
        elif (m := HUNK.match(line)) and path:
            cur = {"path": path, "old_start": int(m[1]), "old_len": int(m[2] if m[2] is not None else 1),
                   "new_start": int(m[3]), "new_len": int(m[4] if m[4] is not None else 1), "removed": [], "added": [], "old": []}
            out.append(cur)
        elif cur is not None and line[:1] in (" ", "-", "+"):
            body = line[1:]
            if line[0] != "+":
                cur["old"].append(body)
            if line[0] == "-":
                cur["removed"].append(body)
            elif line[0] == "+":
                cur["added"].append(body)
    return out


def locate(block: list[str], text: str) -> tuple[int, int] | None:
    """where `block` sits in `text` (1-based lines), matching on norm() so a
    reformat doesn't lose it. whole block first, else its unique lines."""
    lines = text.split("\n")
    normed = [norm(l) for l in lines]
    starts, pos = [], 0
    for n in normed:
        starts.append(pos)
        pos += len(n)
    hay = "".join(normed)

    def line_at(off: int) -> int:
        return bisect.bisect_right(starts, off)

    whole = "".join(norm(l) for l in block)
    if len(whole) >= 12 and hay.count(whole) == 1:
        o = hay.index(whole)
        return line_at(o), line_at(o + len(whole) - 1)
    hits = [line_at(hay.index(n)) for n in map(norm, block) if len(n) >= 10 and hay.count(n) == 1]
    return (min(hits), max(hits)) if hits else None


def is_filler(h: dict) -> bool:
    """a hunk that's only the harness's own inserted lines (a --jolt lands inside a step's delta)."""
    return not h["removed"] and bool(h["added"]) and all(l in FILLER for l in h["added"])


def target_check(delta_u0: str, gold_patch: str, pre_files: dict[str, str | None], slack: int = SLACK) -> dict:
    """did this step's edits land where the gold patch changes things? gold hunks
    are located in the files as they were when the step started; an agent hunk
    is on target if it's within `slack` lines of one. src files only."""
    gold: dict[str, list[tuple[int, int] | None]] = {}
    for h in hunks(gold_patch):
        text = pre_files.get(h["path"])
        if not h["old"] or text is None:
            gold.setdefault(h["path"], []).append((1, 10**9))
        else:
            gold.setdefault(h["path"], []).append(locate(h["old"], text))
    on = off = unknown = 0
    for h in hunks(delta_u0):
        if not src_like(h["path"]) or is_filler(h):
            continue
        s = h["old_start"]
        e = s + max(h["old_len"], 1) - 1
        if h["path"] not in gold:
            off += 1
            continue
        found = [r for r in gold[h["path"]] if r]
        if not found:
            unknown += 1
        elif any(s <= r[1] + slack and e >= r[0] - slack for r in found):
            on += 1
        else:
            off += 1
    return {"agent_hunks": on + off + unknown, "on_target": on, "off_target": off, "unlocated": unknown}


def added_norms(delta: str) -> set[str]:
    return {norm(l) for h in hunks(delta) if src_like(h["path"]) for l in h["added"] if len(norm(l)) >= 8 and l not in FILLER}


def touched_prior(delta: str, prior: set[str]) -> int:
    """lines this step removed that an earlier step of the agent had added."""
    return sum(1 for h in hunks(delta) if src_like(h["path"]) for n in map(norm, h["removed"]) if len(n) >= 8 and n in prior)


def insert_filler(text: str, near: list[int], block: list[str] = FILLER) -> str:
    """put `block` at the top, and above the top-level statement enclosing each
    `near` line (1-based); with nothing near, mid-file. top-level = a line that
    starts at column 0 with a declaration, so it's never inside an expression."""
    lines = text.split("\n")
    tops = [i for i, l in enumerate(lines) if TOP.match(l)]
    points = {0}
    for n in near or [len(lines) // 2 + 1]:
        above = [i for i in tops if i <= n - 1]
        if above:
            p = above[-1]
            if p and lines[p - 1].rstrip().endswith("*/"):  # keep a doc comment on its declaration
                p = next((i for i in range(p - 1, -1, -1) if lines[i].startswith("/*")), p)
            points.add(p)
    for p in sorted(points, reverse=True):
        lines[p:p] = block
    return "\n".join(lines)


def fake_chain_steps(tasks: list[dict], setup: str) -> list[str]:
    """fake-api script for a whole chain: per step a read, an edit made from
    what the previous step read (stale once the world changed) and a fresh edit."""
    steps = []
    for k, t in enumerate(tasks):
        f = t["src_files"][0]
        steps.append(f"sh:ax read {f}:1-12 | tee /tmp/.fake-read-{k}" if uses_ax(setup) else f"sh:head -12 {f} | tee /tmp/.fake-read-{k}")
        if k:
            prev = tasks[k - 1]["src_files"][0]
            if uses_ax(setup):
                steps.append(f"sh:a=$(grep -oE '^ *3:[0-9a-f]+' /tmp/.fake-read-{k - 1} | tr -d ' '); "
                             f"printf '@@ insert after %s\\n// ax-eval fake remembered\\n' \"$a\" | ax edit {prev}")
            else:
                steps.append(f"sh:sed -i '3a // ax-eval fake remembered' {prev}")
        steps.append(f"sh:sed -i -e '$a // ax-eval fake {k}' {f}")
        steps.append(f"msg:step {k} done")
    return steps


def per_step_usage(rows: list[dict], prices: dict | None = None) -> list[dict]:
    """codex 0.156.0 `exec resume` reports usage for the whole thread so far, so
    each step's usage is its total minus the step before's (the thread totals are
    kept as thread_*). a row that isn't >= the previous one is taken as is."""
    out, prev = [], None
    for r in rows:
        r = dict(r)
        cum = {k: r[k] for k in USAGE}
        if prev and all(cum[k] >= prev[k] for k in USAGE):
            r.update({k: cum[k] - prev[k] for k in USAGE})
        r.update({f"thread_{k}": v for k, v in cum.items()})
        if prices:
            r["cost"] = cost(r, prices)
        prev = cum
        out.append(r)
    return out


def thread_id(events: list[str]) -> str | None:
    for l in events:
        if '"thread.started"' in l:
            try:
                return json.loads(l).get("thread_id")
            except json.JSONDecodeError:
                pass
    return None


def jolt_file(item: dict, files: list[str]) -> str | None:
    """the task file a successful read-ish command just looked at, if any."""
    if item.get("type") != "command_execution" or item.get("exit_code") not in (0, None):
        return None
    cmd = item.get("command", "")
    if not any(k in READS for k in kinds(cmd)):
        return None
    return next((f for f in files if f in cmd), None)


def chain_task(task: dict, step: dict, anchor: str, tests: list[str] | None = None) -> dict:
    """the task as graded inside a chain: anchor as base, the chain's own test lists."""
    if tests is not None:
        return {**task, "base": anchor, "fail_to_pass": tests, "pass_to_pass": []}
    return {**task, "base": anchor, "fail_to_pass": step["fail_to_pass"], "pass_to_pass": step["pass_to_pass"]}


# ---- container bits


def bash(name: str, script: str, check: bool = True, **env: str) -> subprocess.CompletedProcess[str]:
    e = [x for k, v in env.items() for x in ("-e", f"{k}={v}")]
    return docker("exec", *e, name, "bash", "-c", script, check=check)


SNAP = """cd /w
export GIT_INDEX_FILE=/tmp/.ax-eval-idx
rm -f "$GIT_INDEX_FILE"
git read-tree "$ANCHOR" && git add -A -- . ':(exclude)AGENTS.md' >/dev/null 2>&1
t=$(git write-tree) || exit 1
rm -f "$GIT_INDEX_FILE"
GIT_AUTHOR_NAME=eval GIT_AUTHOR_EMAIL=eval@localhost GIT_COMMITTER_NAME=eval GIT_COMMITTER_EMAIL=eval@localhost git commit-tree "$t" -p "$ANCHOR" -m snapshot
"""


MERGE = """cd /w; d=$(mktemp -d); trap 'rm -rf "$d"' EXIT
i=0
for f in "$@"; do
  i=$((i+1))
  git show "$C^:$f" > "$d/base" 2>/dev/null || : > "$d/base"
  git show "$C:$f" > "$d/theirs" 2>/dev/null || exit 1
  if [ -e "$f" ]; then o="$f"; else : > "$d/ours"; o="$d/ours"; fi
  git merge-file -p "$o" "$d/base" "$d/theirs" > "$d/out.$i" || exit 1
done
i=0
for f in "$@"; do i=$((i+1)); mkdir -p "$(dirname "$f")"; cat "$d/out.$i" > "$f"; done
"""


def snapshot(name: str, anchor: str) -> str:
    """the working tree as an unreferenced commit (the agent's index and refs stay as they are)."""
    return bash(name, SNAP, ANCHOR=anchor).stdout.strip()


def git_diff(name: str, a: str, b: str, *opts: str, paths: list[str] | None = None) -> str:
    return docker("exec", name, "git", "-C", "/w", "diff", "--binary", *opts, a, b, "--", *(paths or [".", ":(exclude)AGENTS.md"])).stdout


def read_file(name: str, path: str) -> bytes | None:
    r = subprocess.run(["docker", "exec", name, "cat", f"/w/{path}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def write_file(name: str, path: str, body: bytes) -> None:
    subprocess.run(["docker", "exec", "-i", name, "bash", "-c", 'cat > "$1"', "_", f"/w/{path}"], input=body, check=True, capture_output=True)


def show(name: str, sha: str, path: str) -> str | None:
    r = docker("exec", name, "git", "-C", "/w", "show", f"{sha}:{path}", check=False)
    return r.stdout if r.returncode == 0 else None


def insert_into(name: str, path: str, near: list[int]) -> bool:
    body = read_file(name, path)
    if body is None:
        return False
    write_file(name, path, insert_filler(body.decode(), near).encode())
    return True


def apply_world_change(name: str, wc: dict, anchor: str, post: str) -> dict:
    """change the checkout under the agent. returns what was done."""
    touched = [p for p in git_diff(name, anchor, post, "--name-only").split() if src_like(p)]
    files = [f for f in sorted(set(wc["files"]) | set(touched)) if read_file(name, f) is not None]
    rec = {"after": wc["after"], "planned": wc["kind"], "kind": wc["kind"], "files": files, "note": None}
    if wc["kind"] == "upstream":
        subprocess.run(["docker", "exec", "-i", name, "bash", "-c", "cat > /tmp/.ax-eval-up.patch"], input=wc["patch"].encode(), check=True)
        r = bash(name, "cd /w; git apply /tmp/.ax-eval-up.patch; s=$?; rm -f /tmp/.ax-eval-up.patch; exit $s", check=False)
        rec["commit"] = wc.get("commit")
        if r.returncode:
            # the agent's edits sit in the diff's context: 3-way merge each file, all or nothing
            r = docker("exec", "-e", f"C={wc['commit']}", name, "bash", "-c", MERGE, "_", *wc["touches"], check=False)
            rec["note"] = "merged 3-way" if r.returncode == 0 else None
        if r.returncode:
            rec.update(kind="insert", note="upstream change conflicts with the agent's edits, used insert")
    if rec["kind"] == "fmt":
        width = int(wc.get("print_width", PRINT_WIDTH))
        r = bash(name, f"cd /w && node_modules/.bin/prettier --write --print-width {width} -- {' '.join(map(shlex.quote, files))} >/dev/null", check=False)
        if r.returncode:
            rec["note"] = "prettier: " + r.stderr.strip()[-200:]
    if rec["kind"] == "insert":
        for f in files:
            near = [h["new_start"] for h in hunks(git_diff(name, anchor, post, "-U0", paths=[f]))]
            insert_into(name, f, near)
    return rec


def step_cmd(agent: str, setup: str, name: str, task: dict, thread: str | None, env_key: str, model: str, effort: str, cap: list[str]) -> tuple[list[str], str]:
    if agent == "stub":
        return ["docker", "exec", "-e", f"STUB_SETUP={setup}", "-e", f"STUB_FILE={task['src_files'][0]}", name, *cap, "bash", "/tmp/stub.sh"], ""
    args = [a for a in codex_args(setup) if a != "--ephemeral"]  # resume needs the session on disk
    tail = [*args, "-m", model, "-c", f'model_reasoning_effort="{effort}"']
    if thread is None:
        return ["docker", "exec", "-i", "-e", env_key, name, *cap, "codex", "exec", *tail, "-C", "/w", "-"], task["instruction"]
    return ["docker", "exec", "-i", "-w", "/w", "-e", env_key, name, *cap, "codex", "exec", "resume", thread, *tail, "-"], task["instruction"]


def run_chain(
    chain: dict,
    tasks: dict[str, dict],
    setup: str,
    run_id: str,
    out_dir: Path,
    *,
    agent: str = "codex",
    api_base_url: str | None = None,
    env_key: str = FAKE_KEY,
    catalog_src: Path = CATALOG,
    time_cap_s: int = 1200,
    turn_cap: int | None = None,
    seed: int | None = None,
    model: str = MODEL,
    effort: str = EFFORT,
    prices: dict | None = None,
    jolt: bool = False,
) -> dict:
    assert agent in ("codex", "stub") and setup in SETUPS
    if agent == "codex" and not api_base_url:
        raise ValueError("codex runs need api_base_url")
    ts = [tasks[i] for i in chain["tasks"]]
    anchor, n = chain["anchor"], len(ts)
    out_dir.mkdir(parents=True, exist_ok=False)
    box = out_dir / "box"
    box.mkdir()
    m = {
        "run_id": run_id, "chain": chain["id"], "tasks": chain["tasks"], "anchor": anchor, "setup": setup, "seed": seed,
        "agent": agent, "model": model if agent == "codex" else None, "effort": effort if agent == "codex" else None,
        "codex_version": None, "ax_commit": None, "image": None, "api_base_url": api_base_url,
        "time_cap_s": time_cap_s, "turn_cap": turn_cap, "jolt": jolt and agent == "codex", "thread_id": None,
        "started": now(), "ended": None, "total_seconds": None,
        "infra_failure": False, "infra_reason": None, "steps": [], "cost": None,
    }
    t0 = time.time()
    name = f"ax-long-{run_id}"
    phase = "image"
    stage = Path(tempfile.mkdtemp(prefix="ax-long-"))
    steps: list[dict] = []
    try:
        image = m["image"] = agent_image(chain["image"], uses_ax(setup))
        phase = "container"
        md = start_container(name, image, box, stage, setup, anchor, api_base_url, env_key, catalog_src, model, effort)
        m["codex_version"], m["ax_commit"] = image_versions(name, image, uses_ax(setup))
        phase = "probe"
        hidden = sorted({p for t in ts for p in patch_paths(t["test_patch"])})
        probe(name, setup, anchor, md, hidden, env_key, out_dir / "probe.log")
        if agent == "stub":
            docker("cp", str(SCRIPTS / "stub_agent.sh"), f"{name}:/tmp/stub.sh")
        pre = snapshot(name, anchor)
        prior: set[str] = set()
        cap = ["timeout", "-k", "10", str(time_cap_s)]
        for k, t in enumerate(ts):
            phase = f"step {k} agent"
            sd = out_dir / f"step{k}"
            sd.mkdir()
            jolts: list[dict] = []

            def on_item(it: dict, t=t, jolts=jolts) -> None:
                if jolts:
                    return
                f = jolt_file(it, [x for x in t["src_files"] if src_like(x)])
                if f and insert_into(name, f, []):
                    jolts.append({"file": f, "after_item": it.get("id"), "at": round(time.time() - ts0, 1)})

            cmd, stdin = step_cmd(agent, setup, name, t, m["thread_id"], env_key, model, effort, cap)
            ts0 = time.time()
            code, timed_out, capped, secs = drive(cmd, stdin, name, sd, time_cap_s, turn_cap, on_item=on_item if m["jolt"] else None)
            docker("exec", name, "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/out", check=False)
            if (box / "ax_log.jsonl").exists():
                shutil.move(box / "ax_log.jsonl", sd / "ax_log.jsonl")
            else:
                (sd / "ax_log.jsonl").touch()
            events = (sd / "events.jsonl").read_text().splitlines()
            m["thread_id"] = m["thread_id"] or thread_id(events)
            step = {"step": k, "task": t["id"], "exit_code": code, "timed_out": timed_out, "turn_capped": capped,
                    "agent_seconds": secs, "jolt": jolts[0] if jolts else None, "world_after": None}
            steps.append(step)  # before any raise, so a failed step's tokens still reach the ledger
            why = infra_reason(code, timed_out, events, (sd / "stderr.log").read_text())
            if agent == "codex" and k == 0 and not why and not m["thread_id"]:
                why = "no thread id to resume"
            if why:
                step["infra"] = why
                raise StepFailed(f"step {k}: {why}")

            phase = f"step {k} collect"
            post = snapshot(name, anchor)
            (sd / "final.diff").write_text(git_diff(name, anchor, post))
            (sd / "delta.diff").write_text(git_diff(name, pre, post))
            delta0 = git_diff(name, pre, post, "-U0")
            paths = sorted({h["path"] for h in hunks(delta0)} | set(patch_paths(t["gold_patch"])))
            step.update(target_check(delta0, t["gold_patch"], {p: show(name, pre, p) for p in paths}))
            step["touched_prior_lines"] = touched_prior(delta0, prior)
            prior |= added_norms(delta0)
            if k < n - 1:
                phase = f"step {k} world change"
                w = apply_world_change(name, chain["world_changes"][k], anchor, post)
                pre = snapshot(name, anchor)
                w["lines_changed"] = sum(len(h["added"]) + len(h["removed"]) for h in hunks(git_diff(name, post, pre, "-U0")))
                (sd / "world.json").write_text(json.dumps(w, indent=1) + "\n")
                step["world_after"] = w["kind"]
    except Exception as e:  # the harness's fault or the api's, not the agent's
        m["infra_failure"], m["infra_reason"] = True, f"{phase}: {describe(e)}"
    finally:
        docker("exec", name, "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/out", check=False)
        docker("rm", "-f", name, check=False)
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(box, ignore_errors=True)

    prices = prices or load_prices(model=model)
    raw = [metrics(out_dir / f"step{s['step']}" / "events.jsonl", out_dir / f"step{s['step']}" / "ax_log.jsonl", agent=agent) for s in steps]
    for step, mt in zip(steps, per_step_usage(raw, prices)):
        sd = out_dir / f"step{step['step']}"
        (sd / "metrics.json").write_text(json.dumps(mt, indent=1) + "\n")
        oc = mt["ax_outcomes"]
        step.update(
            cost=mt.get("cost", 0.0) if agent == "codex" else 0.0,
            input_tokens=mt["input_tokens"], cached_input_tokens=mt["cached_input_tokens"], output_tokens=mt["output_tokens"],
            tool_calls=mt["tool_calls"], failed_patches=mt["failed_patches"], failed_commands=mt["failed_commands"],
            stale=oc.get("stale", 0), relocated=oc.get("relocated", 0), ambiguous=oc.get("ambiguous", 0),
            no_match=oc.get("no-match", 0), parse_rejected=oc.get("parse-rejected", 0),
        )
    if not m["infra_failure"]:
        try:
            grade_steps(chain, ts, steps, out_dir)
        except Exception as e:
            m["infra_failure"], m["infra_reason"] = True, f"grade: {describe(e)}"
    m["steps"] = steps
    m["cost"] = round(sum(s.get("cost") or 0.0 for s in steps), 6)
    m["ended"] = now()
    m["total_seconds"] = round(time.time() - t0, 1)
    write_manifest(out_dir, m)
    return m


def grade_steps(chain: dict, ts: list[dict], steps: list[dict], out_dir: Path) -> None:
    """each step on its own cumulative diff, then every earlier step again on the last one."""
    anchor = chain["anchor"]
    final = (out_dir / f"step{len(steps) - 1}" / "final.diff").read_text()
    for s in steps:
        k = s["step"]
        sd = out_dir / f"step{k}"
        g = grade(chain_task(ts[k], chain["steps"][k], anchor), (sd / "final.diff").read_text())
        s["resolved"] = g["resolved"]
        s["wrong_place"] = bool(s["off_target"] and not g["resolved"])
        if k < len(steps) - 1:
            at_end = chain["steps"][k].get("at_end") or []
            e = grade(chain_task(ts[k], chain["steps"][k], anchor, at_end), final) if at_end else None
            g["at_chain_end"] = e
            s["final_resolved"] = e["resolved"] if e else None
        else:
            s["final_resolved"] = g["resolved"]
        s["regressed"] = bool(s["resolved"] and s["final_resolved"] is False)
        (sd / "grade.json").write_text(json.dumps(g, indent=1) + "\n")


def with_fake_api(run_fn=run_chain):
    """a run_fn that points codex at a fresh fake api scripted for the whole chain."""

    def fn(chain: dict, tasks: dict[str, dict], setup: str, run_id: str, out_dir: Path, **kw) -> dict:
        steps = fake_chain_steps([tasks[i] for i in chain["tasks"]], setup)
        srv, port = serve(Script(steps), host=bridge_ip())
        os.environ.setdefault(FAKE_KEY, "dummy")
        try:
            return run_fn(chain, tasks, setup, run_id, out_dir, **{**kw, "api_base_url": f"http://host.docker.internal:{port}/v1", "env_key": FAKE_KEY})
        finally:
            srv.shutdown()

    return fn


def run_batch(
    items: list[tuple[str, str, int]],
    chains: dict[str, dict],
    tasks: dict[str, dict],
    *,
    runs_dir: Path = LONG,
    ledger: Path = LEDGER,
    budget: float = BUDGET,
    est: float | None = None,
    parallel: int = 1,
    max_retries: int = 2,
    dry: bool = True,
    seed: int | None = None,
    run_fn=run_chain,
    log=print,
    **kw,
) -> list[dict]:
    """runner.run_batch for chains: a chain is reserved against the budget as
    est x its longest length, retried whole on infra failure, one ledger row per step."""
    if est is None:
        est = 0.0 if dry else (est_from_ledger(read_ledger(ledger), chains=True) or EST_STEP)
    longest = max((len(chains[c]["tasks"]) for c, _, _ in items), default=1)
    gate = Budget(budget, 0.0 if dry else est * longest, ledger)
    stop = threading.Event()
    wlock = threading.Lock()

    def one(item: tuple[str, str, int]) -> dict:
        cid, setup, rep = item
        prev: dict | None = None
        m: dict = {}
        for attempt in range(1, max_retries + 2):
            if stop.is_set():
                return {"chain": cid, "setup": setup, "rep": rep, "refused": "budget"}
            try:
                gate.reserve()
            except BudgetExceeded as e:
                stop.set()
                log(f"refused {cid} {setup} r{rep}: {e}")
                return {"chain": cid, "setup": setup, "rep": rep, "refused": str(e)}
            run_id = new_run_id(cid, setup, rep)
            out = runs_dir / run_id
            if prev:
                with wlock:
                    prev["retried_as"] = run_id
                    write_manifest(runs_dir / prev["run_id"], prev)
            try:
                m = run_fn(chains[cid], tasks, setup, run_id, out, seed=seed, **kw)
            except Exception as e:
                out.mkdir(parents=True, exist_ok=True)
                m = {"run_id": run_id, "chain": cid, "setup": setup, "seed": seed, "agent": kw.get("agent"), "steps": [],
                     "infra_failure": True, "infra_reason": f"runner: {describe(e)}", "cost": 0.0, "started": now(), "ended": now()}
            finally:
                gate.release()
            m.update(rep=rep, attempt=attempt, retry_of=prev["run_id"] if prev else None, retried_as=None, dry=dry)
            with wlock:
                write_manifest(out, m)
                ledger.parent.mkdir(parents=True, exist_ok=True)
                with open(ledger, "a") as f:
                    for s in m["steps"] or [{"task": None, "cost": m.get("cost")}]:
                        row = ledger_row({**m, "task": s["task"], "resolved": s.get("resolved"), "cost": s.get("cost")}, rep, dry)
                        f.write(json.dumps({**row, "chain": m["chain"], "step": s.get("step")}) + "\n")
            log(f"{run_id}: " + (f"infra failure ({m['infra_reason']})" if m["infra_failure"]
                                 else "resolved " + "".join("1" if s.get("resolved") else "0" for s in m["steps"]) + f" {m.get('total_seconds')}s"))
            if not m["infra_failure"]:
                return m
            prev = m
        return m

    if parallel <= 1:
        return [one(i) for i in items]
    with cf.ThreadPoolExecutor(parallel) as ex:
        return list(ex.map(one, items))


def load_chains(sel: list[str], path: Path = CHAINS) -> list[dict]:
    chains = jsonl(path)
    out = [c for c in chains if "all" in sel or c["id"] in sel]
    missing = set(sel) - {"all"} - {c["id"] for c in chains}
    if missing:
        raise SystemExit(f"unknown chains: {sorted(missing)}")
    return out


def summarize(runs_dir: Path = LONG, include_dry: bool = False) -> list[dict]:
    """one row per (setup, jolt or not, position in chain) over the finished runs (paid ones unless include_dry)."""
    ms = [json.loads(p.read_text()) for p in sorted(runs_dir.glob("*/manifest.json"))] if runs_dir.exists() else []
    ms = [m for m in ms if not m.get("infra_failure") and not m.get("retried_as") and (include_dry or not m.get("dry", True))]
    groups: dict[tuple[str, bool, int], list[dict]] = {}
    for m in ms:
        for s in m["steps"]:
            groups.setdefault((m["setup"], bool(m.get("jolt")), s["step"]), []).append(s)
    rows = []
    for (setup, jolt, k), ss in sorted(groups.items()):
        rows.append({
            "setup": setup, "jolt": jolt, "step": k, "n": len(ss),
            "pass_rate": round(sum(bool(s.get("resolved")) for s in ss) / len(ss), 3),
            "regressed": sum(bool(s.get("regressed")) for s in ss),
            "stale": sum(s["stale"] for s in ss), "relocated": sum(s["relocated"] for s in ss),
            "failed_patches": sum(s["failed_patches"] for s in ss),
            "off_target_hunks": sum(s["off_target"] for s in ss), "wrong_place": sum(bool(s.get("wrong_place")) for s in ss),
            "touched_prior_lines": sum(s["touched_prior_lines"] for s in ss),
            "cost_mean": round(statistics.mean(s["cost"] for s in ss), 4),
            "input_tokens_mean": round(statistics.mean(s["input_tokens"] for s in ss)),
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--chains", nargs="+", default=["all"], help="all, or chain ids")
    p.add_argument("--chains-file", type=Path, default=CHAINS)
    p.add_argument("--setups", nargs="+", default=["A", "B"], choices=SETUPS)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--agent", choices=("stub", "codex"), default="stub")
    p.add_argument("--dry-run", action="store_true", help="$0 only: stub, or codex against a local fake api")
    p.add_argument("--paid", action="store_true", help="codex against a real api. only with the gate approved")
    p.add_argument("--plan-only", action="store_true", help="print the run order and the cost estimate, then exit")
    p.add_argument("--summarize", action="store_true", help="print per-setup, per-position numbers for finished runs")
    p.add_argument("--include-dry", action="store_true", help="with --summarize: count dry runs too")
    p.add_argument("--jolt", action="store_true", help="also change a task file right after the agent first reads it")
    p.add_argument("--parallel", type=int, default=1)
    p.add_argument("--budget", type=float, default=BUDGET)
    p.add_argument("--est", type=float, help=f"$ per step for the budget check (default: ledger mean, else {EST_STEP})")
    p.add_argument("--time-cap", type=int, default=1200, help="seconds per step")
    p.add_argument("--turn-cap", type=int, help="tool calls per step")
    p.add_argument("--api-base-url")
    p.add_argument("--env-key")
    p.add_argument("--catalog", type=Path, default=CATALOG)
    p.add_argument("--model", default=MODEL)
    p.add_argument("--effort", default=EFFORT)
    p.add_argument("--runs-dir", type=Path, default=LONG)
    p.add_argument("--ledger", type=Path, default=LEDGER)
    a = p.parse_args(argv)

    if a.summarize:
        for r in summarize(a.runs_dir, a.include_dry):
            print(json.dumps(r))
        return 0
    chains = load_chains(a.chains, a.chains_file)
    if any(not c.get("validated") for c in chains):
        p.error("chains.jsonl has unvalidated chains: rebuild with `python -m ax_eval.chains --validate`")
    items = plan([c["id"] for c in chains], a.setups, a.repeats, a.seed)
    by_id = {c["id"]: c for c in chains}
    if a.plan_only:
        for i in items:
            print(json.dumps(i))
        n_steps = sum(len(by_id[c]["tasks"]) for c, _, _ in items)
        est = a.est or est_from_ledger(read_ledger(a.ledger), chains=True) or EST_STEP
        print(f"{len(items)} chain runs, {n_steps} steps, ~${n_steps * est:.0f} at ${est:.2f}/step", file=sys.stderr)
        return 0

    dry = a.agent == "stub" or a.dry_run
    kw: dict = dict(agent=a.agent, time_cap_s=a.time_cap, turn_cap=a.turn_cap, model=a.model, effort=a.effort,
                    catalog_src=a.catalog, prices=load_prices(model=a.model), jolt=a.jolt)
    run_fn = run_chain
    if a.agent == "codex":
        if a.dry_run:
            run_fn = with_fake_api()
        elif not a.paid:
            p.error("codex without --dry-run spends money: pass --paid, and only once the gate is approved")
        elif not (a.api_base_url and a.env_key and a.env_key in os.environ):
            p.error("--paid needs --api-base-url and --env-key naming a set env var")
        else:
            kw.update(api_base_url=a.api_base_url, env_key=a.env_key)
    tasks = {t["id"]: t for t in jsonl(TASKS / "final.jsonl")}
    try:
        res = run_batch(items, by_id, tasks, runs_dir=a.runs_dir, ledger=a.ledger, budget=a.budget, est=a.est,
                        parallel=a.parallel, dry=dry, seed=a.seed, run_fn=run_fn, **kw)
    except BudgetExceeded as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    done = [r for r in res if "refused" not in r]
    summary = {
        "chain_runs": len(done),
        "infra_failures": sum(bool(r.get("infra_failure")) for r in done),
        "steps": sum(len(r.get("steps") or []) for r in done),
        "resolved_steps": sum(bool(s.get("resolved")) for r in done for s in r.get("steps") or []),
        "refused": len(res) - len(done),
        "spent": round(spent(read_ledger(a.ledger)), 2),
    }
    print(json.dumps(summary))
    return 0 if not summary["refused"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
