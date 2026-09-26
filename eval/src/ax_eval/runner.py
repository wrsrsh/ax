"""run the agent on tasks, one fresh container per run, and keep everything.

    uv run python -m ax_eval.runner --tasks dev --setups A B C --repeats 1 --agent stub --dry-run
    uv run python -m ax_eval.runner --tasks dev --setups B --agent codex --dry-run   # codex vs the fake api
    uv run python -m ax_eval.runner --tasks all --repeats 3 --seed 7 --plan-only

each run gets runs/<run-id>/ with manifest.json, events.jsonl, stderr.log,
ax_log.jsonl, probe.log, final.diff, grade.json and metrics.json, and a row in
runs/ledger.jsonl with its cost. run dirs are never reused and old runs are
never regraded; an infra failure is retried under a new run id and the old
dir is kept with `retried_as` set.

codex against a real api needs --paid plus --api-base-url and --env-key. the
key is only ever handed to `docker exec -e NAME`, read from this process's env.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import random
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from ax_eval.fakeapi import Script, serve
from ax_eval.grade import grade, patch_paths
from ax_eval.images import agent_image
from ax_eval.parse import metrics, parse_events
from ax_eval.setups import SETUPS, agents_md, codex_args, uses_ax, write_codex_home
from ax_eval.util import EVAL, RUNS, TASKS, jsonl, sh

LEDGER = RUNS / "ledger.jsonl"
PRICES = EVAL / "prices.json"
SCRIPTS = EVAL / "scripts"
CATALOG = Path.home() / ".codex/model-catalogs/azure-foundry.json"
MODEL, EFFORT = "gpt-6-astra", "medium"
BUDGET = 2000.0
FAKE_KEY = "AX_EVAL_FAKE_KEY"
# codex 0.156.0 has no turn or step limit (no flag, no config key); turn_cap is
# enforced here by counting tool calls in the event stream.
TOOL_ITEMS = ("command_execution", "file_change", "mcp_tool_call")
API_TROUBLE = re.compile(
    r"stream disconnected|connection (refused|reset|closed)|error sending request|dns|timed? ?out waiting|"
    r"\b(429|500|502|503|504)\b|rate.?limit|service unavailable|overloaded|unauthorized|\b401\b",
    re.I,
)
REAP = 'for p in /proc/[0-9]*; do n=${p#/proc/}; [ "$n" -gt 1 ] && [ "$n" != $$ ] && kill -%s "$n" 2>/dev/null; done; true'
KILL_TIMEOUT = 'for p in /proc/[0-9]*; do [ "$(cat $p/comm 2>/dev/null)" = timeout ] && kill -TERM ${p#/proc/}; done; true'


class BudgetExceeded(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id(task_id: str, setup: str, rep: int) -> str:
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{task_id}-{setup}-r{rep}-{secrets.token_hex(2)}"


def load_tasks(sel: list[str], path: Path = TASKS / "final.jsonl") -> list[dict]:
    """`dev`, `heldout`, `all` or task ids."""
    tasks = jsonl(path)
    out = [t for t in tasks if "all" in sel or t["set"] in sel or t["id"] in sel]
    missing = set(sel) - {"all", "dev", "heldout"} - {t["id"] for t in tasks}
    if missing:
        raise SystemExit(f"unknown tasks: {sorted(missing)}")
    return out


def plan(tasks: list, setups: list[str], repeats: int, seed: int) -> list[tuple[str, str, int]]:
    """every (task, setup, rep), shuffled by seed so setups interleave over time."""
    ids = [t["id"] if isinstance(t, dict) else t for t in tasks]
    items = [(i, s, r) for i in ids for s in setups for r in range(repeats)]
    random.Random(seed).shuffle(items)
    return items


def load_prices(path: Path = PRICES) -> dict:
    """$ per 1M tokens from prices.json; zeros (and a warning) without it."""
    keys = ("input", "cached_input", "cache_write", "output")
    if not path.exists():
        print(f"warning: no {path.name}, costs will be 0", file=sys.stderr)
        return dict.fromkeys(keys, 0.0)
    p = json.loads(path.read_text()).get("per_million", {})
    return {k: float(p.get(k, 0.0)) for k in keys}


def read_ledger(path: Path) -> list[dict]:
    return jsonl(path) if path.exists() else []


def spent(rows: list[dict]) -> float:
    return sum(r.get("cost") or 0.0 for r in rows if not r.get("dry"))


def est_from_ledger(rows: list[dict]) -> float | None:
    costs = [r["cost"] for r in rows if r.get("agent") == "codex" and not r.get("dry") and not r.get("infra_failure") and r.get("cost") is not None]
    return sum(costs) / len(costs) if costs else None


class Budget:
    """refuse a run if what's spent plus what's in flight plus one more run would pass the cap."""

    def __init__(self, cap: float, est: float, ledger: Path):
        self.cap, self.est, self.ledger = cap, est, ledger
        self.inflight = 0
        self.lock = threading.Lock()

    def reserve(self) -> None:
        with self.lock:
            s = spent(read_ledger(self.ledger))
            if s + self.est * (self.inflight + 1) > self.cap:
                raise BudgetExceeded(f"spent ${s:.2f} + {self.inflight + 1} x est ${self.est:.2f} > budget ${self.cap:.2f}")
            self.inflight += 1

    def release(self) -> None:
        with self.lock:
            self.inflight -= 1


def infra_reason(exit_code: int | None, timed_out: bool, events: list[str], stderr: str) -> str | None:
    """why a finished agent run doesn't count, or None if it does. timeouts count."""
    if timed_out:
        return None
    row = parse_events(events)
    if row["completed"]:
        return None
    if row["error"] and API_TROUBLE.search(row["error"]):
        return f"api: {row['error'][:200]}"
    if not any(l.strip() for l in events):
        tail = " ".join(stderr.strip().splitlines()[-3:])[:200]
        return f"agent printed no events (exit {exit_code}): {tail}"
    return None


def docker(*args: str, **kw) -> subprocess.CompletedProcess[str]:
    return sh("docker", *args, **kw)


def stage_home(stage: Path, setup: str, base_url: str, env_key: str, catalog_src: Path, model: str, effort: str) -> Path:
    """generate CODEX_HOME on the host, rewritten to live at /codex-home in the container."""
    home = write_codex_home(stage / "codex-home", setup, base_url, env_key, catalog_src, model=model, effort=effort)
    cfg = home / "config.toml"
    cfg.write_text(cfg.read_text().replace(str(home), "/codex-home"))
    return home


def image_versions(name: str, image: str, with_ax: bool) -> tuple[str | None, str | None]:
    r = docker("exec", name, "codex", "--version", check=False)
    codex_v = r.stdout.strip() or None
    label = docker("image", "inspect", "-f", '{{index .Config.Labels "org.ax.commit"}}', image, check=False).stdout.strip()
    ax_v = label if label and label != "<no value>" else None
    if not ax_v and with_ax:
        ax_v = docker("exec", name, "ax", "--version", check=False).stdout.strip() or None
    return codex_v, ax_v


def run_one(
    task: dict,
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
) -> dict:
    assert agent in ("codex", "stub") and setup in SETUPS
    if agent == "codex" and not api_base_url:
        raise ValueError("codex runs need api_base_url")
    out_dir.mkdir(parents=True, exist_ok=False)
    box = out_dir / "box"
    box.mkdir()
    for f in ("events.jsonl", "stderr.log", "final.diff"):
        (out_dir / f).touch()
    m = {
        "run_id": run_id, "task": task["id"], "setup": setup, "seed": seed, "agent": agent,
        "model": model if agent == "codex" else None, "effort": effort if agent == "codex" else None,
        "codex_version": None, "ax_commit": None, "image": None, "api_base_url": api_base_url,
        "time_cap_s": time_cap_s, "turn_cap": turn_cap,
        "started": now(), "ended": None, "agent_seconds": None, "total_seconds": None,
        "exit_code": None, "timed_out": False, "turn_capped": False,
        "infra_failure": False, "infra_reason": None, "resolved": None, "cost": None,
    }
    t0 = time.time()
    name = f"ax-run-{run_id}"
    phase = "image"
    stage = Path(tempfile.mkdtemp(prefix="ax-run-"))
    try:
        image = m["image"] = agent_image(task["image"], uses_ax(setup))
        phase = "container"
        home = stage_home(stage, setup, api_base_url or "http://127.0.0.1:9/v1", env_key, catalog_src, model, effort)
        md = agents_md(setup)
        (stage / "AGENTS.md").write_text(md)
        docker(
            "run", "-d", "--name", name, "--add-host", "host.docker.internal:host-gateway",
            "-v", f"{box}:/out", "-e", "AX_LOG=/out/ax_log.jsonl", "-e", "CODEX_HOME=/codex-home",
            "-w", "/w", "--entrypoint", "sleep", image, "infinity",
        )
        docker("exec", "-e", f"BASE={task['base']}", name, "bash", "-c",
               'set -e; cd /w; git checkout -q -f "$BASE"; git clean -fdq; echo AGENTS.md >> .git/info/exclude')
        docker("cp", str(home), f"{name}:/codex-home")
        docker("cp", str(stage / "AGENTS.md"), f"{name}:/w/AGENTS.md")
        m["codex_version"], m["ax_commit"] = image_versions(name, image, uses_ax(setup))

        phase = "probe"
        docker("cp", str(SCRIPTS / "probe.sh"), f"{name}:/tmp/probe.sh")
        pr = docker(
            "exec", "-e", f"PROBE_SETUP={setup}", "-e", f"PROBE_BASE={task['base']}",
            "-e", f"PROBE_AGENTS_SHA={hashlib.sha256(md.encode()).hexdigest()}",
            "-e", f"PROBE_HIDDEN={chr(10).join(patch_paths(task['test_patch']))}", "-e", f"PROBE_ENV_KEY={env_key}",
            name, "bash", "-c", "bash /tmp/probe.sh; s=$?; rm -f /tmp/probe.sh; exit $s", check=False,
        )
        (out_dir / "probe.log").write_text(pr.stdout + pr.stderr)
        if pr.returncode != 0:
            raise RuntimeError("isolation probe failed: " + "; ".join(l for l in pr.stdout.splitlines() if l.startswith("FAIL")))

        phase = "agent"
        cap = ["timeout", "-k", "10", str(time_cap_s)]
        if agent == "stub":
            docker("cp", str(SCRIPTS / "stub_agent.sh"), f"{name}:/tmp/stub.sh")
            cmd = ["docker", "exec", "-e", f"STUB_SETUP={setup}", "-e", f"STUB_FILE={task['src_files'][0]}", name, *cap, "bash", "/tmp/stub.sh"]
            stdin = ""
        else:
            if env_key not in os.environ:
                raise RuntimeError(f"${env_key} is not set")
            args = codex_args(setup)
            args = args[1:] if args[:1] == ["exec"] else args
            cmd = ["docker", "exec", "-i", "-e", env_key, name, *cap, "codex", "exec", *args,
                   "-m", model, "-c", f'model_reasoning_effort="{effort}"', "-C", "/w", "-"]
            stdin = task["instruction"]
        m["exit_code"], m["timed_out"], m["turn_capped"], m["agent_seconds"] = drive(cmd, stdin, name, out_dir, time_cap_s, turn_cap)

        phase = "collect"
        d = docker("exec", "-e", f"BASE={task['base']}", name, "bash", "-c",
                   'cd /w && git add -A && git diff --cached --binary "$BASE" -- . ":(exclude)AGENTS.md"')
        (out_dir / "final.diff").write_text(d.stdout)
        events = (out_dir / "events.jsonl").read_text().splitlines()
        why = infra_reason(m["exit_code"], m["timed_out"], events, (out_dir / "stderr.log").read_text())
        if why:
            m["infra_failure"], m["infra_reason"] = True, why
    except Exception as e:  # any failure here is the harness's, not the agent's
        m["infra_failure"], m["infra_reason"] = True, f"{phase}: {describe(e)}"
    finally:
        docker("exec", name, "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/out", check=False)
        docker("rm", "-f", name, check=False)
        shutil.rmtree(stage, ignore_errors=True)
        log = box / "ax_log.jsonl"
        if log.exists():
            shutil.move(log, out_dir / "ax_log.jsonl")
        else:
            (out_dir / "ax_log.jsonl").touch()
        shutil.rmtree(box, ignore_errors=True)

    if not m["infra_failure"]:
        try:
            g = grade(task, (out_dir / "final.diff").read_text())
            (out_dir / "grade.json").write_text(json.dumps(g, indent=1) + "\n")
            m["resolved"] = g["resolved"]
        except Exception as e:
            m["infra_failure"], m["infra_reason"] = True, f"grade: {describe(e)}"
    mt = metrics(out_dir / "events.jsonl", out_dir / "ax_log.jsonl", prices or load_prices())
    (out_dir / "metrics.json").write_text(json.dumps(mt, indent=1) + "\n")
    m["cost"] = mt.get("cost", 0.0) if agent == "codex" else 0.0
    m["ended"] = now()
    m["total_seconds"] = round(time.time() - t0, 1)
    write_manifest(out_dir, m)
    return m


def describe(e: Exception) -> str:
    if isinstance(e, subprocess.CalledProcessError):
        return f"{' '.join(map(str, e.cmd[:4]))}... exit {e.returncode}: {(e.stderr or '').strip()[-300:]}"
    return f"{type(e).__name__}: {e}"[:400]


def drive(cmd: list[str], stdin: str, name: str, out_dir: Path, time_cap_s: int, turn_cap: int | None) -> tuple[int, bool, bool, float]:
    """run the agent, streaming its stdout to events.jsonl. (exit code, timed out, turn capped, seconds)"""
    t0 = time.time()
    capped = False
    backstop = threading.Timer(time_cap_s + 60, lambda: docker("exec", name, "bash", "-c", REAP % "KILL", check=False))
    with open(out_dir / "events.jsonl", "w") as ev, open(out_dir / "stderr.log", "w") as err:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True)
        backstop.start()
        try:
            p.stdin.write(stdin)
            p.stdin.close()
        except BrokenPipeError:
            pass
        tools = 0
        for line in p.stdout:
            ev.write(line)
            ev.flush()
            if turn_cap and not capped and '"item.completed"' in line:
                try:
                    it = json.loads(line).get("item", {})
                except json.JSONDecodeError:
                    continue
                tools += it.get("type") in TOOL_ITEMS
                if tools >= turn_cap:
                    capped = True
                    docker("exec", name, "bash", "-c", KILL_TIMEOUT, check=False)
        code = p.wait()
        backstop.cancel()
    secs = round(time.time() - t0, 1)
    timed_out = code in (124, 137) and not capped or secs > time_cap_s
    return code, timed_out, capped, secs


def write_manifest(out_dir: Path, m: dict) -> None:
    (out_dir / "manifest.json").write_text(json.dumps(m, indent=1) + "\n")


def ledger_row(m: dict, rep: int, dry: bool) -> dict:
    keys = ("run_id", "task", "setup", "agent", "model", "infra_failure", "resolved", "cost", "started", "ended", "attempt", "retry_of")
    return {**{k: m.get(k) for k in keys}, "rep": rep, "dry": dry}


def run_batch(
    items: list[tuple[str, str, int]],
    tasks: list[dict],
    *,
    runs_dir: Path = RUNS,
    ledger: Path = LEDGER,
    budget: float = BUDGET,
    est: float | None = None,
    parallel: int = 1,
    max_retries: int = 3,
    dry: bool = True,
    seed: int | None = None,
    run_fn=run_one,
    log=print,
    **kw,
) -> list[dict]:
    """run every item, retrying infra failures under new run ids. returns the
    last manifest per item, or {"refused": reason} once the budget is hit."""
    by_id = {t["id"]: t for t in tasks}
    if est is None:
        est = 0.0 if dry else est_from_ledger(read_ledger(ledger))
        if est is None:
            raise BudgetExceeded("no paid runs in the ledger yet; pass --est")
    gate = Budget(budget, 0.0 if dry else est, ledger)
    stop = threading.Event()
    wlock = threading.Lock()

    def one(item: tuple[str, str, int]) -> dict:
        task_id, setup, rep = item
        prev: dict | None = None
        m: dict = {}
        for attempt in range(1, max_retries + 2):
            if stop.is_set():
                return {"task": task_id, "setup": setup, "rep": rep, "refused": "budget"}
            try:
                gate.reserve()
            except BudgetExceeded as e:
                stop.set()
                log(f"refused {task_id} {setup} r{rep}: {e}")
                return {"task": task_id, "setup": setup, "rep": rep, "refused": str(e)}
            run_id = new_run_id(task_id, setup, rep)
            out = runs_dir / run_id
            if prev:
                with wlock:
                    prev["retried_as"] = run_id
                    write_manifest(runs_dir / prev["run_id"], prev)
            try:
                m = run_fn(by_id[task_id], setup, run_id, out, seed=seed, **kw)
            except Exception as e:
                out.mkdir(parents=True, exist_ok=True)
                m = {"run_id": run_id, "task": task_id, "setup": setup, "seed": seed, "agent": kw.get("agent"),
                     "infra_failure": True, "infra_reason": f"runner: {describe(e)}", "cost": 0.0, "started": now(), "ended": now()}
            finally:
                gate.release()
            m.update(rep=rep, attempt=attempt, retry_of=prev["run_id"] if prev else None, retried_as=None)
            with wlock:
                write_manifest(out, m)
                ledger.parent.mkdir(parents=True, exist_ok=True)
                with open(ledger, "a") as f:
                    f.write(json.dumps(ledger_row(m, rep, dry)) + "\n")
            log(f"{run_id}: " + (f"infra failure ({m['infra_reason']})" if m["infra_failure"] else f"resolved={m.get('resolved')} {m.get('total_seconds')}s"))
            if not m["infra_failure"]:
                return m
            prev = m
        return m

    if parallel <= 1:
        return [one(i) for i in items]
    with cf.ThreadPoolExecutor(parallel) as ex:
        return list(ex.map(one, items))


def bridge_ip() -> str:
    r = docker("network", "inspect", "bridge", "-f", "{{(index .IPAM.Config 0).Gateway}}", check=False)
    return r.stdout.strip() or "0.0.0.0"


def fake_steps(task: dict, setup: str) -> list[str]:
    f = task["src_files"][0]
    read = f"sh:ax read {f}:1-20" if uses_ax(setup) else f"sh:head -20 {f}"
    return [read, f"sh:sed -i -e '$a // ax-eval fake' {f}", "msg:done"]


def with_fake_api(run_fn=run_one):
    """a run_fn that points codex at a fresh fake api per run (bound to the
    docker bridge, reached as host.docker.internal via host-gateway)."""

    def fn(task: dict, setup: str, run_id: str, out_dir: Path, **kw) -> dict:
        srv, port = serve(Script(fake_steps(task, setup)), host=bridge_ip())
        os.environ.setdefault(FAKE_KEY, "dummy")
        try:
            return run_fn(task, setup, run_id, out_dir, **{**kw, "api_base_url": f"http://host.docker.internal:{port}/v1", "env_key": FAKE_KEY})
        finally:
            srv.shutdown()

    return fn


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tasks", nargs="+", default=["dev"], help="dev, heldout, all, or task ids")
    p.add_argument("--setups", nargs="+", default=list(SETUPS), choices=SETUPS)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--agent", choices=("stub", "codex"), default="stub")
    p.add_argument("--dry-run", action="store_true", help="$0 only: stub, or codex against a local fake api")
    p.add_argument("--paid", action="store_true", help="codex against a real api. only with the gate approved")
    p.add_argument("--plan-only", action="store_true", help="print the run order and exit")
    p.add_argument("--parallel", type=int, default=1)
    p.add_argument("--budget", type=float, default=BUDGET)
    p.add_argument("--est", type=float, help="$ per run for the budget check (default: ledger mean)")
    p.add_argument("--time-cap", type=int, default=1200)
    p.add_argument("--turn-cap", type=int, help="stop the agent after this many tool calls")
    p.add_argument("--api-base-url")
    p.add_argument("--env-key", help="name of the env var holding the api key")
    p.add_argument("--catalog", type=Path, default=CATALOG)
    p.add_argument("--model", default=MODEL)
    p.add_argument("--effort", default=EFFORT)
    p.add_argument("--runs-dir", type=Path, default=RUNS)
    a = p.parse_args(argv)

    tasks = load_tasks(a.tasks)
    items = plan(tasks, a.setups, a.repeats, a.seed)
    if a.plan_only:
        for i in items:
            print(json.dumps(i))
        print(f"{len(items)} runs", file=sys.stderr)
        return 0

    dry = a.agent == "stub" or a.dry_run
    kw: dict = dict(agent=a.agent, time_cap_s=a.time_cap, turn_cap=a.turn_cap, model=a.model, effort=a.effort,
                    catalog_src=a.catalog, prices=load_prices())
    run_fn = run_one
    if a.agent == "codex":
        if a.dry_run:
            run_fn = with_fake_api()
        elif not a.paid:
            p.error("codex without --dry-run spends money: pass --paid, and only once the gate is approved")
        elif not (a.api_base_url and a.env_key and a.env_key in os.environ):
            p.error("--paid needs --api-base-url and --env-key naming a set env var")
        else:
            kw.update(api_base_url=a.api_base_url, env_key=a.env_key)
    ledger = a.runs_dir / "ledger.jsonl"
    try:
        res = run_batch(items, tasks, runs_dir=a.runs_dir, ledger=ledger, budget=a.budget, est=a.est,
                        parallel=a.parallel, dry=dry, seed=a.seed, run_fn=run_fn, **kw)
    except BudgetExceeded as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    done = [r for r in res if "refused" not in r]
    summary = {
        "runs": len(done),
        "infra_failures": sum(bool(r.get("infra_failure")) for r in done),
        "resolved": sum(bool(r.get("resolved")) for r in done),
        "refused": len(res) - len(done),
        "spent": round(spent(read_ledger(ledger)), 2),
    }
    print(json.dumps(summary))
    return 0 if not summary["refused"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
