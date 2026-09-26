import json
import shutil
import subprocess

import pytest

from ax_eval import runner
from ax_eval.runner import Budget, BudgetExceeded, est_from_ledger, infra_reason, load_prices, plan, read_ledger, run_batch, spent

TASKS = [{"id": f"t{i}"} for i in range(3)]


def test_plan_is_complete_and_seeded():
    a = plan(TASKS, ["A", "B", "C"], 2, seed=1)
    assert len(a) == 18 and len(set(a)) == 18
    assert set(a) == {(t["id"], s, r) for t in TASKS for s in "ABC" for r in range(2)}
    assert a == plan(["t0", "t1", "t2"], ["A", "B", "C"], 2, seed=1)
    assert a != plan(TASKS, ["A", "B", "C"], 2, seed=2)
    # setups interleave instead of running in blocks
    assert [s for _, s, _ in a[:9]] != sorted(s for _, s, _ in a[:9])


def fake_run(outcomes, cost=1.0, calls=None):
    """a run_fn that fails with an infra error per `outcomes` (True = infra) and never touches docker."""
    it = iter(outcomes)

    def fn(task, setup, run_id, out_dir, **kw):
        out_dir.mkdir(parents=True)
        infra = next(it)
        if calls is not None:
            calls.append((task["id"], setup, run_id, kw))
        return {"run_id": run_id, "task": task["id"], "setup": setup, "agent": kw.get("agent"), "infra_failure": infra,
                "infra_reason": "api: 503" if infra else None, "resolved": not infra, "cost": cost, "started": "s", "ended": "e"}

    return fn


def test_retry_keeps_and_marks_old_runs(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    res = run_batch([("t0", "B", 0)], TASKS, runs_dir=tmp_path, ledger=ledger, run_fn=fake_run([True, True, False]), log=lambda *_: None)
    m = res[0]
    assert not m["infra_failure"] and m["attempt"] == 3
    rows = read_ledger(ledger)
    assert [r["infra_failure"] for r in rows] == [True, True, False]
    first = json.loads((tmp_path / rows[0]["run_id"] / "manifest.json").read_text())
    second = json.loads((tmp_path / rows[1]["run_id"] / "manifest.json").read_text())
    assert first["retried_as"] == rows[1]["run_id"] and second["retried_as"] == m["run_id"]
    assert m["retry_of"] == rows[1]["run_id"] and len({r["run_id"] for r in rows}) == 3


def test_retry_gives_up_after_three(tmp_path):
    res = run_batch([("t0", "A", 0)], TASKS, runs_dir=tmp_path, ledger=tmp_path / "l.jsonl", run_fn=fake_run([True] * 9), log=lambda *_: None)
    assert res[0]["infra_failure"] and res[0]["attempt"] == 4
    assert len(read_ledger(tmp_path / "l.jsonl")) == 4


def test_crashing_run_fn_is_an_infra_failure(tmp_path):
    def boom(*a, **kw):
        raise RuntimeError("docker went away")

    res = run_batch([("t0", "A", 0)], TASKS, runs_dir=tmp_path, ledger=tmp_path / "l.jsonl", run_fn=boom, max_retries=0, log=lambda *_: None)
    assert res[0]["infra_failure"] and "docker went away" in res[0]["infra_reason"]
    assert (tmp_path / res[0]["run_id"] / "manifest.json").exists()


def test_ledger_spend_and_estimate():
    rows = [
        {"agent": "codex", "cost": 2.0},
        {"agent": "codex", "cost": 4.0},
        {"agent": "codex", "cost": 100.0, "dry": True},
        {"agent": "codex", "cost": 1.0, "infra_failure": True},
        {"agent": "stub", "cost": 0.0},
    ]
    assert spent(rows) == 7.0
    assert est_from_ledger(rows) == 3.0
    assert est_from_ledger([{"agent": "stub", "cost": 0}]) is None


def test_budget_refuses_before_running(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps({"agent": "codex", "cost": 1990.0}) + "\n")
    calls = []
    res = run_batch([("t0", "A", 0), ("t1", "B", 0)], TASKS, runs_dir=tmp_path, ledger=ledger, est=20.0, dry=False,
                    run_fn=fake_run([False] * 2, calls=calls), log=lambda *_: None)
    assert calls == [] and all("refused" in r for r in res)
    # under the cap it runs, and each run's cost counts toward the next check
    ledger.write_text(json.dumps({"agent": "codex", "cost": 1950.0}) + "\n")
    res = run_batch([("t0", "A", 0), ("t1", "B", 0), ("t2", "C", 0)], TASKS, runs_dir=tmp_path, ledger=ledger, est=20.0, dry=False,
                    run_fn=fake_run([False] * 3, cost=25.0, calls=calls), log=lambda *_: None)
    assert len(calls) == 2 and "refused" in res[2]
    assert spent(read_ledger(ledger)) == 2000.0


def test_budget_counts_in_flight_runs(tmp_path):
    b = Budget(100.0, 40.0, tmp_path / "none.jsonl")
    b.reserve()
    b.reserve()
    with pytest.raises(BudgetExceeded):
        b.reserve()
    b.release()
    b.reserve()


def test_paid_batch_needs_an_estimate(tmp_path):
    with pytest.raises(BudgetExceeded):
        run_batch([("t0", "A", 0)], TASKS, runs_dir=tmp_path, ledger=tmp_path / "l.jsonl", dry=False, run_fn=fake_run([False]))


def test_dry_runs_dont_count(tmp_path):
    ledger = tmp_path / "l.jsonl"
    ledger.write_text(json.dumps({"agent": "codex", "cost": 5000.0, "dry": True}) + "\n")
    res = run_batch([("t0", "A", 0)], TASKS, runs_dir=tmp_path, ledger=ledger, dry=True, run_fn=fake_run([False]), log=lambda *_: None)
    assert not res[0].get("refused") and read_ledger(ledger)[-1]["dry"]


def test_parallel_runs_everything_once(tmp_path):
    items = plan(TASKS, ["A", "B", "C"], 2, seed=3)
    calls = []
    res = run_batch(items, TASKS, runs_dir=tmp_path, ledger=tmp_path / "l.jsonl", parallel=4, run_fn=fake_run([False] * 18, calls=calls), seed=3, log=lambda *_: None)
    assert sorted((r["task"], r["setup"], r["rep"]) for r in res) == sorted(items)
    assert all(c[3]["seed"] == 3 for c in calls)


def test_infra_reason():
    ok = ['{"type":"turn.completed","usage":{}}']
    assert infra_reason(0, False, ok, "") is None
    assert infra_reason(124, True, [], "") is None
    api = ['{"type":"turn.started"}', '{"type":"error","message":"stream disconnected before completion: 503 Service Unavailable"}']
    assert infra_reason(1, False, api, "").startswith("api:")
    assert "no events" in infra_reason(1, False, [], "exec: codex: not found")
    # the model giving up on its own is a result, not an infra failure
    assert infra_reason(1, False, ['{"type":"turn.failed","error":{"message":"context window exceeded"}}'], "") is None


def test_prices(tmp_path, capsys):
    assert load_prices(tmp_path / "nope.json") == {"input": 0.0, "cached_input": 0.0, "cache_write": 0.0, "output": 0.0}
    assert "warning" in capsys.readouterr().err
    (tmp_path / "p.json").write_text('{"per_million": {"input": 1.25, "cached_input": 0.125, "output": 10}}')
    p = load_prices(tmp_path / "p.json")
    assert p["output"] == 10.0 and p["cache_write"] == 0.0


def test_cli_refuses_unapproved_paid_runs(capsys):
    with pytest.raises(SystemExit):
        runner.main(["--tasks", "dev", "--agent", "codex"])
    assert "--paid" in capsys.readouterr().err


def test_cli_plan_only(capsys):
    assert runner.main(["--tasks", "dev", "--setups", "A", "B", "--repeats", "2", "--plan-only"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 10 * 2 * 2


# --- docker: real containers, $0 ---

def _dev_task():
    if not shutil.which("docker"):
        return None
    have = lambda img: subprocess.run(["docker", "image", "inspect", img], capture_output=True).returncode == 0  # noqa: E731
    return next((t for t in runner.load_tasks(["dev"]) if have(t["image"])), None)


DEV = _dev_task()
needs_docker = pytest.mark.skipif(DEV is None, reason="needs docker + a built dev task image")


@pytest.mark.docker
@needs_docker
@pytest.mark.parametrize("setup", ["A", "B", "C"])
def test_stub_run_end_to_end(setup, tmp_path):
    zero = {"input": 0, "cached_input": 0, "output": 0}
    m = runner.run_one(DEV, setup, f"test-{setup}", tmp_path / "run", agent="stub", prices=zero)
    d = tmp_path / "run"
    assert not m["infra_failure"], m["infra_reason"]
    for f in ("manifest.json", "events.jsonl", "stderr.log", "ax_log.jsonl", "final.diff", "grade.json", "metrics.json", "probe.log"):
        assert (d / f).exists(), f
    assert "FAIL" not in (d / "probe.log").read_text()
    assert "+// ax-eval stub" in (d / "final.diff").read_text() and "AGENTS.md" not in (d / "final.diff").read_text()
    assert m["codex_version"].startswith("codex-cli") and m["exit_code"] == 0
    g = json.loads((d / "grade.json").read_text())
    assert g["task"] == DEV["id"] and g["error"] is None and not g["resolved"]
    mt = json.loads((d / "metrics.json").read_text())
    ax_calls = sum(mt["ax_calls"].values())
    if setup == "A":
        assert ax_calls == 0 and m["ax_commit"] is None
    else:
        assert ax_calls >= 3 and mt["tools"].get("ax edit") == 1 and m["ax_commit"]
    assert not list(d.glob("box"))


@pytest.mark.docker
@needs_docker
def test_codex_against_fake_api(tmp_path):
    zero = {"input": 0, "cached_input": 0, "output": 0}
    m = runner.with_fake_api()(DEV, "C", "test-fake", tmp_path / "run", agent="codex", prices=zero, time_cap_s=120)
    assert not m["infra_failure"], m["infra_reason"]
    mt = json.loads((tmp_path / "run" / "metrics.json").read_text())
    assert mt["completed"] and mt["tools"].get("ax read") == 1
    assert "+// ax-eval fake" in (tmp_path / "run" / "final.diff").read_text()


@pytest.mark.docker
@needs_docker
def test_probe_catches_leaks(tmp_path):
    """the probe fails when the host's codex config or an api key gets in."""
    home = tmp_path / "codex"
    home.mkdir()
    (home / "config.toml").write_text('[mcp_servers.linear]\ncommand = "x"\n')
    image = runner.agent_image(DEV["image"], False)
    r = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{home}:/root/.codex", "-v", f"{runner.SCRIPTS / 'probe.sh'}:/probe.sh:ro",
         "-e", "CODEX_HOME=/root/.codex", "-e", "LEAKED=1", "-e", "PROBE_ENV_KEY=LEAKED", "-e", "PROBE_SETUP=B",
         "-e", f"PROBE_BASE={DEV['base']}", "-e", "PROBE_AGENTS_SHA=x", "--entrypoint", "bash", image, "/probe.sh"],
        capture_output=True, text=True,
    )
    fails = [l for l in r.stdout.splitlines() if l.startswith("FAIL")]
    assert r.returncode == 1
    for bit in ("host codex config", "mcp servers", "ax missing", "AGENTS.md", "LEAKED", "mounts"):
        assert any(bit in l for l in fails), (bit, fails)
