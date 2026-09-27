import json
from pathlib import Path

from ax_eval.parse import cost, fallback_rate, metrics, parse_events
from ax_eval.runner import infra_reason

# claude code 2.1.283 against fakeapi_anthropic (see capture.run_claude)
FX = Path(__file__).parent / "fixtures" / "claude"
# what the fake api charges per request: 200 fresh, 1000 cache write, 3000 cache read, 40 out
PER_REQ = {"fresh": 200, "cw": 1000, "cr": 3000, "out": 40}


def lines(name):
    return (FX / name).read_text().splitlines()


def test_shell_fixture():
    r = parse_events(lines("shell_and_message.jsonl"))
    assert r["agent"] == "claude" and r["completed"] and r["error"] is None and r["stop"] == "completed"
    assert r["tool_calls"] == 2 and r["tools"] == {"cat": 1, "grep": 1} and r["messages"] == 1
    # 3 requests: two tool calls and the final message
    # uncached means what it means for codex: not read from cache, so writes are in it
    assert r["uncached_input_tokens"] == 3 * (PER_REQ["fresh"] + PER_REQ["cw"])
    assert r["cache_write_input_tokens"] == 3 * PER_REQ["cw"] and r["cached_input_tokens"] == 3 * PER_REQ["cr"]
    assert r["input_tokens"] == 3 * (PER_REQ["fresh"] + PER_REQ["cw"] + PER_REQ["cr"])
    assert r["output_tokens"] == 3 * PER_REQ["out"] and r["turns"] == 3 and r["api_retries"] == 0
    assert fallback_rate(r["tools"]) == 1.0


def test_ax_fixture():
    r = parse_events(lines("ax_calls.jsonl"))
    assert r["tools"] == {"ax read": 1, "ax grep": 1, "printf": 1, "ax edit": 1}
    assert fallback_rate(r["tools"]) == 0.0
    # the ax edit got a bad op header and exited 1
    assert r["failed_commands"] == 1 and r["failed_patches"] == 0


def test_native_tools_are_their_own_kinds():
    r = parse_events(lines("native_tools.jsonl"))
    assert r["tools"] == {"Read": 1, "Grep": 1, "Glob": 1, "Edit": 2, "Write": 1, "false": 1}
    # the Edit whose old_string wasn't there is a failed patch, `false` a failed command
    assert r["failed_patches"] == 1 and r["failed_commands"] == 1
    assert fallback_rate(r["tools"]) == 1.0


def test_setup_c_refuses_edit():
    r = parse_events(lines("setup_c_edit.jsonl"))
    init = json.loads(lines("setup_c_edit.jsonl")[0])
    assert init["tools"] == ["Bash", "Glob", "Grep", "Read"]
    # the model asked for Edit anyway, got "No such tool available", then used sed
    assert r["tools"] == {"Edit": 1, "sed": 1} and r["failed_patches"] == 1 and r["completed"]


def test_max_turns():
    r = parse_events(lines("max_turns.jsonl"))
    assert not r["completed"] and r["stop"] == "max_turns"
    assert "maximum number of turns" in r["error"]
    # hitting the cap is the agent's result, not an infra failure
    assert infra_reason(1, False, lines("max_turns.jsonl"), "") is None


def test_api_error_is_infra():
    r = parse_events(lines("api_error.jsonl"))
    assert not r["completed"] and r["api_retries"] == 2 and r["messages"] == 0
    assert r["error"].startswith("529:") and r["stop"] == "api_error"
    assert infra_reason(1, False, lines("api_error.jsonl"), "").startswith("api:")


def test_truncated_stream_falls_back_to_assistant_usage():
    trunc = lines("shell_and_message.jsonl")[:4]
    r = parse_events(trunc + ['{"type": "assist'])
    assert not r["completed"] and r["tool_calls"] == 2
    # two assistant messages seen, their start-of-stream usage counts
    assert r["uncached_input_tokens"] == 2 * (PER_REQ["fresh"] + PER_REQ["cw"]) and r["cached_input_tokens"] == 2 * PER_REQ["cr"]


def test_metrics_cost_matches_claude_code():
    prices = {"input": 5.0, "cached_input": 0.5, "cache_write": 6.25, "output": 25.0}
    m = metrics(FX / "native_tools.jsonl", None, prices, agent="claude")
    assert m["agent"] == "claude"
    assert abs(m["cost"] - m["reported_cost"]) < 1e-9
    assert abs(cost(m, prices) - 8 * (200 * 5 + 1000 * 6.25 + 3000 * 0.5 + 40 * 25) / 1e6) < 1e-12


def test_cache_writes_bill_once_for_both_agents():
    """written tokens bill at the write rate only, never also at the input rate."""
    prices = {"input": 5.0, "cached_input": 0.5, "cache_write": 6.25, "output": 25.0}
    m = metrics(FX / "shell_and_message.jsonl", None, prices, agent="claude")
    assert m["cost_uncached"] == 3 * 200 * 5 / 1e6
    assert abs(m["cost_cache_write"] - 3 * 1000 * 6.25 / 1e6) < 1e-12
    assert abs(sum(m[k] for k in ("cost_uncached", "cost_cached", "cost_cache_write", "cost_output")) - m["cost"]) < 1e-12
    assert abs(m["cost"] - m["reported_cost"]) < 1e-9
    # a codex row with the same token classes costs the same
    codex = {"uncached_input_tokens": 3 * 1200, "cached_input_tokens": 3 * 3000, "cache_write_input_tokens": 3 * 1000, "output_tokens": 3 * 40}
    assert abs(cost(codex, prices) - m["cost"]) < 1e-12


def test_codex_rows_unchanged():
    r = parse_events((FX.parent / "codex" / "shell_and_message.jsonl").read_text().splitlines())
    assert "agent" not in r and "stop" not in r and r["tools"] == {"cat": 1, "grep": 1}
