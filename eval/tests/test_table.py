import json

from ax_eval.table import row, usable


def run_dir(tmp_path, manifest):
    d = tmp_path / manifest.get("run_id", "r1")
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps(manifest))
    (d / "grade.json").write_text(json.dumps({"resolved": True, "f2p_passed": 1, "f2p_total": 1, "p2p_passed": 2, "p2p_total": 2, "error": None}))
    (d / "metrics.json").write_text(json.dumps({"input_tokens": 10, "output_tokens": 2, "tool_calls": 3, "tools": {"ax read": 3}, "ax_calls": {"read": 3}, "ax_outcomes": {}}))
    (d / "events.jsonl").write_text("")
    return d


def test_runner_manifest_shape(tmp_path):
    real = row(run_dir(tmp_path, {"run_id": "a", "task": "hono-9", "setup": "B", "agent": "codex", "api_base_url": "https://x.example/v1"}), {"hono-9": "heldout"})
    assert real["task_id"] == "hono-9" and real["split"] == "heldout" and not real["dry"] and usable(real)
    fake = row(run_dir(tmp_path, {"run_id": "b", "task": "hono-9", "setup": "B", "agent": "codex", "api_base_url": "http://host.docker.internal:1234/v1"}))
    stub = row(run_dir(tmp_path, {"run_id": "c", "task": "hono-9", "setup": "A", "agent": "stub"}))
    assert fake["dry"] and stub["dry"] and not usable(fake) and not usable(stub)
