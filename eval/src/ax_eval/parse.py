"""codex `exec --json` events + AX_LOG -> one metrics row per run.

event shape (codex-cli 0.156.0): thread.started, turn.started,
item.started/item.completed with item.type in command_execution
(command, aggregated_output, exit_code), file_change (apply_patch),
agent_message, reasoning; turn.completed with usage; turn.failed / error.
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


def parse_events(lines: list[str]) -> dict:
    usage = Counter()
    tools = Counter()
    row = {"completed": False, "error": None, "tool_calls": 0, "failed_commands": 0, "failed_patches": 0, "messages": 0}
    for line in lines:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
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
    """prices in $ per 1M tokens: input, cached_input, cache_write, output (reasoning is billed as output)."""
    return (
        row["uncached_input_tokens"] * prices["input"]
        + row["cached_input_tokens"] * prices["cached_input"]
        + row.get("cache_write_input_tokens", 0) * prices.get("cache_write", 0)
        + row["output_tokens"] * prices["output"]
    ) / 1e6


def metrics(events: Path, ax_log: Path | None = None, prices: dict | None = None) -> dict:
    row = parse_events(events.read_text().splitlines() if events.exists() else [])
    row.update(parse_ax_log(ax_log.read_text().splitlines() if ax_log and ax_log.exists() else []))
    row["fallback_rate"] = fallback_rate(row["tools"])
    row["script_calls"] = sum(v for k, v in row["tools"].items() if k.startswith("script"))
    row["ax_rejections"] = sum(row["ax_outcomes"].get(k, 0) for k in ("stale", "ambiguous", "parse-rejected", "no-match"))
    if prices:
        row["cost"] = cost(row, prices)
    return row
