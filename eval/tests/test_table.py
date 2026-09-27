import json

from ax_eval.table import row, usable


def run_dir(tmp_path, manifest, metrics=None):
    d = tmp_path / manifest.get("run_id", "r1")
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps(manifest))
    (d / "grade.json").write_text(json.dumps({"resolved": True, "f2p_passed": 1, "f2p_total": 1, "p2p_passed": 2, "p2p_total": 2, "error": None}))
    (d / "metrics.json").write_text(json.dumps(metrics or {"input_tokens": 10, "output_tokens": 2, "tool_calls": 3, "tools": {"ax read": 3}, "ax_calls": {"read": 3}, "ax_outcomes": {}}))
    (d / "events.jsonl").write_text("")
    return d


def test_runner_manifest_shape(tmp_path):
    real = row(run_dir(tmp_path, {"run_id": "a", "task": "hono-9", "setup": "B", "agent": "codex", "api_base_url": "https://x.example/v1"}), {"hono-9": "heldout"})
    assert real["task_id"] == "hono-9" and real["split"] == "heldout" and not real["dry"] and usable(real)
    fake = row(run_dir(tmp_path, {"run_id": "b", "task": "hono-9", "setup": "B", "agent": "codex", "api_base_url": "http://host.docker.internal:1234/v1"}))
    stub = row(run_dir(tmp_path, {"run_id": "c", "task": "hono-9", "setup": "A", "agent": "stub"}))
    assert fake["dry"] and stub["dry"] and not usable(fake) and not usable(stub)


def test_cost_parts_derived_for_old_metrics(tmp_path):
    old = {"input_tokens": 3_000_000, "cached_input_tokens": 2_000_000, "uncached_input_tokens": 1_000_000,
           "cache_write_input_tokens": 500_000, "output_tokens": 100_000, "cost": 9.9}
    prices = {"input": 10.0, "cached_input": 1.0, "cache_write": 12.5, "output": 50.0}
    r = row(run_dir(tmp_path, {"run_id": "old", "task": "hono-9", "setup": "B", "agent": "codex"}, old), prices=prices)
    assert (r["cost_uncached"], r["cost_cached"], r["cost_cache_write"], r["cost_output"]) == (10.0, 2.0, 6.25, 5.0)
    assert r["cost"] == 9.9  # the recorded total stays as it was
    new = dict(old, cost_uncached=1.0, cost_cached=2.0, cost_cache_write=3.0, cost_output=4.0)
    r = row(run_dir(tmp_path, {"run_id": "new", "task": "hono-9", "setup": "B", "agent": "codex"}, new), prices=prices)
    assert r["cost_uncached"] == 1.0 and r["cost_output"] == 4.0
    # no token counts, nothing to derive
    r = row(run_dir(tmp_path, {"run_id": "bare", "task": "hono-9", "setup": "B", "agent": "codex"}, {"tool_calls": 1}), prices=prices)
    assert r["cost_output"] is None
