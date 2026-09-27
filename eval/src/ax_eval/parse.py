"""codex `exec --json` or claude code `-p --output-format stream-json` events +
AX_LOG -> one metrics row per run.

codex (codex-cli 0.156.0): thread.started, turn.started,
item.started/item.completed with item.type in command_execution
(command, aggregated_output, exit_code), file_change (apply_patch),
agent_message, reasoning; turn.completed with usage; turn.failed / error.

claude code (2.1.283): system/init, then `assistant` events (one per content
block, the same message id repeated) holding tool_use / text / thinking blocks,
`user` events holding the tool_result blocks (is_error), and one `result` at the
end with usage summed over the run, num_turns, terminal_reason and
total_cost_usd. usage there is anthropic-shaped: input_tokens is the uncached
part only, cache writes and reads come separately.
"""

from __future__ import annotations

import json
import re
import shlex
from collections import Counter
from pathlib import Path

# commands that read, search or edit files; anything else (tests, git, npm) isn't a file op.
# `script` is an interpreter running inline code (python -c, node -e, a heredoc):
# the model doing the file work in python instead of any tool.
FILE_OPS = {"ax", "cat", "head", "tail", "sed", "awk", "grep", "rg", "find", "ls", "nl", "wc", "apply_patch", "script"}
# claude code's own file tools are the non-ax way to do the same work
FILE_OPS |= {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Glob", "Grep"}
INTERPRETERS = {"python", "python3", "node", "bun", "deno", "perl", "ruby"}


def unwrap(command: str) -> str:
    """`/usr/bin/bash -lc 'cat a'` -> `cat a`"""
    m = re.match(r"^\S*(?:ba|z)?sh\s+-\w*c\s+(.*)$", command.strip(), re.S)
    if not m:
        return command
    try:
        parts = shlex.split(m.group(1))
        return parts[0] if parts else command
    except ValueError:
        return m.group(1).strip("'\"")


def segments(cmd: str) -> list[list[str]]:
    """shell words per simple command; `|`, `&&`, `;` inside quotes don't split."""
    segs, cur = [], []
    for line in cmd.split("\n"):
        # `2>&1` and `&>` are redirections, not `&` separators
        line = re.sub(r"&>", ">", re.sub(r"(\d*[<>])&(\d+|-)", r"\1\2", line))
        lex = shlex.shlex(line, posix=True, punctuation_chars="|&;")
        lex.whitespace_split = True
        try:
            toks = list(lex)
        except ValueError:
            toks = line.split()
        for t in toks:
            if t and set(t) <= set("|&;"):
                segs.append(cur)
                cur = []
            else:
                cur.append(t)
        segs.append(cur)
        cur = []
    return [x for x in segs if x]


def kinds(command: str) -> list[str]:
    """every program in a shell line, `ax` tagged with its subcommand."""
    out = []
    cmd = unwrap(command)
    if "<<" in cmd:
        # a heredoc body isn't more commands
        cmd = cmd.split("\n", 1)[0]
    for words in segments(cmd):
        while words and ("=" in words[0] or words[0] in {"sudo", "env", "time", "timeout", "xargs"}):
            words = words[1:]
            if words and words[0].isdigit():
                words = words[1:]
        if not words:
            continue
        prog = words[0].rsplit("/", 1)[-1]
        if prog == "ax":
            sub = next((w for w in words[1:] if not w.startswith("-")), "")
            out.append(f"ax {sub}".strip())
        elif prog in INTERPRETERS and (set(words[1:]) & {"-c", "-e", "-"} or "<<" in " ".join(words)):
            out.append(f"script {prog}")
        else:
            out.append(prog)
    return out


CLAUDE_EDITS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _events(lines: list[str]) -> list[dict]:
    out = []
    for line in lines:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(e, dict):
            out.append(e)
    return out


def is_claude(events: list[dict]) -> bool:
    return any(e.get("type") in ("system", "assistant", "result") and "session_id" in e for e in events)


def parse_events(lines: list[str]) -> dict:
    events = _events(lines)
    return parse_claude(events) if is_claude(events) else parse_codex(events)


def parse_claude(events: list[dict]) -> dict:
    tools = Counter()
    row = {"agent": "claude", "completed": False, "error": None, "tool_calls": 0, "failed_commands": 0, "failed_patches": 0,
           "messages": 0, "turns": None, "stop": None, "reported_cost": None, "api_retries": 0}
    names: dict[str, str] = {}
    seen: set[str] = set()
    per_msg: dict[str, dict] = {}
    result = None
    for e in events:
        t = e.get("type")
        if t == "system" and e.get("subtype") == "api_retry":
            row["api_retries"] += 1
        elif t == "assistant":
            msg = e.get("message") or {}
            if msg.get("model") == "<synthetic>":
                # claude code's own "API Error: ..." text, not the model talking
                continue
            if msg.get("id") and msg.get("usage"):
                per_msg[msg["id"]] = msg["usage"]
            for b in msg.get("content") or []:
                if b.get("type") == "tool_use" and b.get("id") not in seen:
                    seen.add(b.get("id"))
                    names[b.get("id")] = name = b.get("name", "?")
                    row["tool_calls"] += 1
                    if name == "Bash":
                        for k in kinds((b.get("input") or {}).get("command", "")):
                            tools[k] += 1
                    else:
                        tools[name] += 1
                elif b.get("type") == "text" and b.get("text", "").strip():
                    row["messages"] += 1
        elif t == "user":
            for b in (e.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                    name = names.get(b.get("tool_use_id"), "")
                    if name in CLAUDE_EDITS:
                        row["failed_patches"] += 1
                    else:
                        row["failed_commands"] += 1
        elif t == "result":
            result = e
    if result is not None:
        u = result.get("usage") or {}
        row["completed"] = result.get("subtype") == "success" and not result.get("is_error")
        row["turns"] = result.get("num_turns")
        row["stop"] = result.get("terminal_reason")
        row["reported_cost"] = result.get("total_cost_usd")
        if result.get("is_error"):
            errs = result.get("errors") or []
            status = result.get("api_error_status")
            msg = "; ".join(map(str, errs)) or (result.get("result") if isinstance(result.get("result"), str) else "") or result.get("subtype")
            row["error"] = f"{status}: {msg}" if status else msg
    else:
        # killed before the end: add up what the assistant events carried. output
        # there is whatever the stream start said, so it undercounts.
        u = Counter()
        for mu in per_msg.values():
            for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"):
                u[k] += mu.get(k) or 0
    fresh, cw, cr = (u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    row.update(
        input_tokens=fresh + cw + cr,
        cached_input_tokens=cr,
        cache_write_input_tokens=cw,
        # same meaning as codex's: everything not read from cache, writes included.
        # cost_parts takes the writes back out, so they bill once at the write rate
        uncached_input_tokens=fresh + cw,
        output_tokens=u.get("output_tokens") or 0,
        reasoning_tokens=(u.get("output_tokens_details") or {}).get("thinking_tokens", 0) if result is not None else 0,
        tools=dict(tools),
    )
    return row


def parse_codex(events: list[dict]) -> dict:
    usage = Counter()
    tools = Counter()
    row = {"completed": False, "error": None, "tool_calls": 0, "failed_commands": 0, "failed_patches": 0, "messages": 0}
    for e in events:
        t = e.get("type")
        if t == "turn.completed":
            row["completed"] = True
            for k, v in (e.get("usage") or {}).items():
                usage[k] += v
        elif t in ("turn.failed", "error"):
            row["error"] = (e.get("error") or {}).get("message") or e.get("message")
        elif t == "item.completed":
            it = e.get("item", {})
            if it.get("type") == "command_execution":
                row["tool_calls"] += 1
                for k in kinds(it.get("command", "")):
                    tools[k] += 1
                if it.get("exit_code") not in (0, None):
                    row["failed_commands"] += 1
            elif it.get("type") == "file_change":
                row["tool_calls"] += 1
                tools["apply_patch"] += 1
                if it.get("status") != "completed":
                    row["failed_patches"] += 1
            elif it.get("type") == "agent_message":
                row["messages"] += 1
    row.update(
        input_tokens=usage["input_tokens"],
        cached_input_tokens=usage["cached_input_tokens"],
        cache_write_input_tokens=usage["cache_write_input_tokens"],
        uncached_input_tokens=usage["input_tokens"] - usage["cached_input_tokens"],
        output_tokens=usage["output_tokens"],
        reasoning_tokens=usage["reasoning_output_tokens"],
        tools=dict(tools),
    )
    return row


def parse_ax_log(lines: list[str]) -> dict:
    calls = Counter()
    outcomes = Counter()
    for line in lines:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        calls[e.get("cmd") or "?"] += 1
        if e.get("outcome"):
            outcomes[e["outcome"]] += 1
    return {"ax_calls": dict(calls), "ax_outcomes": dict(outcomes)}


def fallback_rate(tools: dict) -> float | None:
    """share of file operations that didn't go through ax (None: no file ops)."""
    ops = {k: v for k, v in tools.items() if k.split()[0] in FILE_OPS}
    total = sum(ops.values())
    if not total:
        return None
    return sum(v for k, v in ops.items() if not k.startswith("ax")) / total


def cost(row: dict, prices: dict) -> float:
    """prices in $ per 1M tokens: input, cached_input, cache_write, output (reasoning is billed as output).
    cache-write tokens are part of input_tokens and bill at the cache-write rate instead of the input rate."""
    return sum(cost_parts(row, prices).values())


COST_PARTS = ("cost_uncached", "cost_cached", "cost_cache_write", "cost_output")


def cost_parts(row: dict, prices: dict) -> dict:
    """cost() split by token class, same prices, sums to cost() (up to float rounding)."""
    written = row.get("cache_write_input_tokens") or 0
    return {
        "cost_uncached": max(row["uncached_input_tokens"] - written, 0) * prices["input"] / 1e6,
        "cost_cached": row["cached_input_tokens"] * prices["cached_input"] / 1e6,
        "cost_cache_write": written * prices.get("cache_write", 0) / 1e6,
        "cost_output": row["output_tokens"] * prices["output"] / 1e6,
    }


def metrics(events: Path, ax_log: Path | None = None, prices: dict | None = None, agent: str | None = None) -> dict:
    row = parse_events(events.read_text().splitlines() if events.exists() else [])
    row["agent"] = agent or row.get("agent") or "codex"
    row.update(parse_ax_log(ax_log.read_text().splitlines() if ax_log and ax_log.exists() else []))
    row["fallback_rate"] = fallback_rate(row["tools"])
    row["script_calls"] = sum(v for k, v in row["tools"].items() if k.startswith("script"))
    row["ax_rejections"] = sum(row["ax_outcomes"].get(k, 0) for k in ("stale", "ambiguous", "parse-rejected", "no-match"))
    if prices:
        row["cost"] = cost(row, prices)
        row.update(cost_parts(row, prices))
    return row
