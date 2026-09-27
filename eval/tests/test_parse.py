import json
from pathlib import Path

from ax_eval.parse import COST_PARTS, cost, cost_parts, fallback_rate, kinds, metrics, parse_ax_log, parse_events, unwrap

FX = Path(__file__).parent / "fixtures" / "codex"


def lines(name):
    return (FX / name).read_text().splitlines()


def test_unwrap_and_kinds():
    assert unwrap("/usr/bin/bash -lc 'cat a.txt'") == "cat a.txt"
    assert kinds("/usr/bin/bash -lc 'cat a.txt | grep x && ax read b.ts'") == ["cat", "grep", "ax read"]
    assert kinds("bash -lc \"printf 'x' | ax edit a.txt\"") == ["printf", "ax edit"]
    assert kinds("FOO=1 timeout 30 rg -n x src") == ["rg"]
    assert kinds("ax --json grep foo") == ["ax grep"]
    assert kinds("rg -n 'writeSSE|retry' src && cat a.ts") == ["rg", "cat"]
    assert kinds('/bin/bash -lc "rg -n \'a|b\' src; echo done"') == ["rg", "echo"]
    assert kinds("bun run test 2>&1 | tail -5") == ["bun", "tail"]
    assert kinds("ax diff &> out.txt && cat out.txt") == ["ax diff", "cat"]


def test_scripts_count_as_file_ops():
    assert kinds("python3 -c 'print(open(\"a\").read())'") == ["script python3"]
    assert kinds("bash -lc \"python3 - <<'EOF'\nimport re\nEOF\"") == ["script python3"]
    assert kinds("node -e 'console.log(1)' && cat a") == ["script node", "cat"]
    assert kinds("python3 scripts/check.py") == ["python3"]
    assert kinds("node dist/index.js") == ["node"]
    assert fallback_rate({"script python3": 2, "ax read": 2}) == 0.5
    assert fallback_rate({"python3": 3}) is None


def test_shell_fixture():
    r = parse_events(lines("shell_and_message.jsonl"))
    assert r["completed"] and r["error"] is None
    assert r["tool_calls"] == 2 and r["tools"] == {"cat": 1, "grep": 1}
    assert r["input_tokens"] == 3600 and r["cached_input_tokens"] == 3000 and r["uncached_input_tokens"] == 600
    assert r["output_tokens"] == 120 and r["reasoning_tokens"] == 48
    assert fallback_rate(r["tools"]) == 1.0


def test_ax_fixture():
    r = parse_events(lines("ax_calls.jsonl"))
    assert r["tools"] == {"ax read": 1, "ax grep": 1, "printf": 1, "ax edit": 1}
    assert fallback_rate(r["tools"]) == 0.0


def test_apply_patch_and_failures():
    r = parse_events(lines("apply_patch.jsonl"))
    assert r["tools"] == {"apply_patch": 1} and r["failed_patches"] == 0
    r = parse_events(lines("failed_command.jsonl"))
    assert r["failed_commands"] == 2


def test_truncated_and_error_streams():
    trunc = lines("shell_and_message.jsonl")[:4]
    r = parse_events(trunc + ['{"type": "item.comp'])
    assert not r["completed"] and r["input_tokens"] == 0 and r["tool_calls"] == 1
    err = [
        json.dumps({"type": "turn.started"}),
        json.dumps({"type": "error", "message": "rate limited"}),
        json.dumps({"type": "turn.failed", "error": {"message": "rate limited"}}),
    ]
    r = parse_events(err)
    assert r["error"] == "rate limited" and not r["completed"]


def test_ax_log_and_metrics(tmp_path):
    log = tmp_path / "ax.jsonl"
    log.write_text(
        "\n".join(
            json.dumps(x)
            for x in [
                {"cmd": "read", "exit": 0, "outcome": None},
                {"cmd": "edit", "exit": 1, "outcome": "stale"},
                {"cmd": "edit", "exit": 0, "outcome": "ok"},
            ]
        )
    )
    assert parse_ax_log(log.read_text().splitlines()) == {"ax_calls": {"read": 1, "edit": 2}, "ax_outcomes": {"stale": 1, "ok": 1}}
    m = metrics(FX / "ax_calls.jsonl", log, {"input": 2.0, "cached_input": 0.5, "output": 8.0})
    assert m["ax_rejections"] == 1
    assert m["script_calls"] == 0
    assert abs(m["cost"] - (800 * 2.0 + 4000 * 0.5 + 160 * 8.0) / 1e6) < 1e-12
    assert abs(m["cost_uncached"] - 800 * 2.0 / 1e6) < 1e-12 and abs(m["cost_output"] - 160 * 8.0 / 1e6) < 1e-12
    assert abs(sum(m[k] for k in COST_PARTS) - m["cost"]) < 1e-12


def test_cost_formula():
    row = {"uncached_input_tokens": 1_000_000, "cached_input_tokens": 1_000_000, "output_tokens": 1_000_000}
    assert cost(row, {"input": 1, "cached_input": 0.1, "output": 4}) == 5.1
    row["cache_write_input_tokens"] = 1_000_000
    assert cost(row, {"input": 1, "cached_input": 0.1, "cache_write": 1.25, "output": 4}) == 5.35  # written tokens bill at 1.25, not 1 + 1.25


def test_cost_parts_sum_to_cost():
    row = {"uncached_input_tokens": 1_000_000, "cached_input_tokens": 2_000_000, "cache_write_input_tokens": 1_000_000, "output_tokens": 3_000_000}
    prices = {"input": 1, "cached_input": 0.1, "cache_write": 1.25, "output": 4}
    parts = cost_parts(row, prices)
    # every uncached token was a cache write here, so nothing bills at the plain input rate
    assert parts == {"cost_uncached": 0.0, "cost_cached": 0.2, "cost_cache_write": 1.25, "cost_output": 12.0}
    assert abs(sum(parts.values()) - cost(row, prices)) < 1e-12
    # old rows without cache writes, and prices without a cache_write rate
    assert cost_parts({"uncached_input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 0}, {"input": 1e6, "cached_input": 0, "output": 0})["cost_cache_write"] == 0
