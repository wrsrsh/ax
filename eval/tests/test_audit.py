import json

from ax_eval import audit
from ax_eval.audit import blame, calls, label, prog

STALE = "src/a.ts: stale anchor 3:beef: that line changed since you read it. current lines:\n  3:cafe  x\nnothing written (stale).\n"
VITEST_FAIL = "\n RUN  v4.1.9 /w\n ❯ src/a.test.ts (3 tests | 1 failed)\nerror: \"vitest\" exited with code 1\n"
CLAP = "error: unexpected argument '-n' found\n\n  tip: to pass '-n' as a value, use '-- -n'\n\nUsage: ax grep [OPTIONS] <PATTERN> [PATHS]...\n"


def bash(s):
    """how codex wraps a shell line: double quotes, real newlines."""
    return '/bin/bash -lc "' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def test_heredoc_bodies_arent_commands():
    cmd = bash("ax edit src/a.ts <<'EOF'\n@@ replace 1:abcd\nfoo && bar | baz\nEOF\nbun run test 2>&1 | tail -5")
    assert [prog(s) for s in calls(cmd)] == ["ax", "bun", "tail"]
    assert calls("cat <<< 'x' && ax read a.ts")[-1] == ["ax", "read", "a.ts"]
    assert label(["bun", "run", "test"]) == "bun run test"
    assert label(["bunx", "vitest", "run", "src/a.test.ts"]) == "bunx vitest"
    assert label(["npx", "tsc", "-p", "tsconfig.json"]) == "npx tsc"


def test_blame_rules():
    assert blame("rg x src", "", 1) is None
    assert blame("ax read a.ts", "a.ts ...", 0) == {"failed": False, "segments": [["ax", "read", "a.ts"]]}

    b = blame(bash("ax edit src/a.ts <<'EOF'\n@@ replace 3:beef\nx\nEOF"), STALE, 1)
    assert b["ax"] and b["sub"] == "edit" and b["kind"] == "stale anchor" and b["why"] == "ax is the last segment"

    # the edit worked, the tests failed
    b = blame(bash("ax edit src/a.ts <<'EOF'\n@@ insert after 1:abcd\nx\nEOF\nbun run test"), "src/a.ts: replaced\n" + VITEST_FAIL, 1)
    assert not b["ax"] and b["later"] == "bun run test" and b["where"] == "after ax"

    # the edit refused and the chain stopped
    b = blame(bash("ax edit src/a.ts <<'EOF'\n@@ replace 3:beef\nx\nEOF\n&& bun run test"), STALE, 1)
    assert b["ax"] and b["why"] == "output starts with an ax error" and b["kind"] == "stale anchor"

    # ax is last but never ran: prettier stopped the chain
    b = blame("bunx prettier --check a.ts && ax diff", "Checking formatting...\n[warn] a.ts\n", 1)
    assert not b["ax"] and b["later"] == "bunx prettier" and b["where"] == "before ax"

    b = blame(bash("ax read a.ts b.ts; ax grep x src -n"), "a.ts  (3 lines)\n1:aaaa  x\n" + CLAP, 2)
    assert b["sub"] == "grep" and b["kind"] == "usage error"

    # `src/jsx` is a prefix of the missing path, not the missing path
    b = blame("ax map src/jsx; ax outline src/jsx/c.tsx; echo done", "src/jsx\n  c.tsx\nax: no such path: src/jsx/c.tsx\ndone\n", 1)
    assert b["sub"] == "outline" and b["kind"] == "missing path"

    out = "a.ts  (1 lines)\n1:aaaa  x\nsrc/b.ts: find text \"y\" isn't in the file exactly. closest: indentation differs.\nnothing written (no-match).\n"
    b = blame(bash("ax read a.ts && ax edit src/b.ts <<'EOF'\n@@ find\ny\n@@ with\nz\nEOF\n&& bun run test"), out, 1)
    assert b["sub"] == "edit" and b["kind"] == "no match" and b["why"] == "ax error line later in the output"

    b = blame("ax write src/b.ts --if 1234abcd", "src/b.ts: this change doesn't parse (1 syntax errors, the file had none)\nnothing written (parse-rejected).\n", 1)
    assert b["kind"] == "parse-rejected"

    b = blame("ax read a.ts gone.ts", "a.ts  (1 lines)\n1:aaaa  x\ngone.ts: no such file or directory (os error 2)\nread 1 file (1 line shown). failed: gone.ts.\n", 1)
    assert b["sub"] == "read" and b["kind"] == "missing path" and b["line"].startswith("gone.ts: no such file")


def cmd_item(command, output="", exit_code=0):
    return {"type": "item.completed", "item": {"type": "command_execution", "command": command, "aggregated_output": output, "exit_code": exit_code}}


def write_run(runs, run_id, setup, items, *, dry=False, split="heldout", log=None):
    d = runs / run_id
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in [{"type": "turn.started"}, *items]))
    if log is not None:
        (d / "ax_log.jsonl").write_text(log)
    return {"run_id": run_id, "setup": setup, "dry": dry, "split": split}


def test_audit_end_to_end(tmp_path):
    runs = tmp_path / "runs"
    rows = [
        write_run(runs, "b1", "B", [
            cmd_item(bash("ax map"), "src/\n  a.ts\n  b.ts\nmap: 2 files.\n"),
            cmd_item(bash("ax find AGENTS.md"), "AGENTS.md\n1 file.\n"),
            cmd_item(bash("ax read a.ts"), "a.ts  (2 lines)\n1:aaaa  x\n2:bbbb  y\nread 1 file.\n"),
            cmd_item(bash("ax edit src/a.ts <<'EOF'\n@@ replace 3:beef\nx\nEOF"), STALE, 1),
            cmd_item(bash("ax edit src/a.ts <<'EOF'\n@@ replace 3:cafe\nx\nEOF\nbun run test"), "src/a.ts: replaced\n" + VITEST_FAIL, 1),
        ], log='{"cmd":"map","exit":0}\n{"cmd":"edit","exit":1,"outcome":"stale"}\n{{"cmd""cmd\n'),
        write_run(runs, "c1", "C", [
            cmd_item("pwd", "/w\n"),
            cmd_item(bash("ax map"), "src/\nmap: 1 file.\n"),
            cmd_item(bash("ax grep x src -n"), CLAP, 2),
            cmd_item(bash("ax read b.ts"), "b.ts  (1 lines)\n1:aaaa  x\nread 1 file.\n"),
        ]),
        write_run(runs, "dry1", "B", [cmd_item("ax grep x -n", CLAP, 2)], dry=True),
        write_run(runs, "dev1", "B", [cmd_item("ax grep x -n", CLAP, 2)], split="dev"),
    ]
    (runs / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    a = audit.audit(runs)
    assert a["runs"] == 2 and a["runs_by_setup"] == {"B": 1, "C": 1}
    assert a["commands"] == 9 and a["ax_commands"] == 8 and a["ax_commands_nonzero"] == 3
    assert a["blamed_on_ax"] == 2 and a["blamed_on_later"] == 1 and a["later_commands"] == {"bun run test": 1}
    assert a["failures"] == {"ax edit": {"stale anchor": 1}, "ax grep": {"usage error": 1}}
    assert a["blamed_on_ax_by_setup"] == {"B": 1, "C": 1}
    assert a["examples"]["usage error"][0]["run_id"] == "c1"
    assert a["first_command_ax_map"] == {"B": 1, "C": 0} and a["first_ax_command_ax_map"] == {"B": 1, "C": 1}
    assert a["runs_with_ax_find_agents_md"] == {"B": 1, "C": 0}
    assert a["output_lines"]["read"] == {"calls": 2, "median": 3.5, "mean": 3.5}
    assert a["output_lines"]["map"]["calls"] == 2 and a["output_lines"]["diff"]["median"] is None
    assert a["ax_log"]["lines"] == 3 and a["ax_log"]["corrupt"] == 1 and a["ax_log"]["nonzero_by_outcome"] == {"stale": 1}

    out = tmp_path / "report" / "ax_audit.md"
    assert audit.main([str(runs), "--out", str(out)]) == 0
    md = out.read_text()
    for h in ["# ax exit audit", "## non-zero exits", "## ax failures by subcommand and kind", "## examples",
              "## cross-check with ax's own log", "## habits", "## output size of successful calls"]:
        assert h in md, h
    assert "| `ax edit` |  | 1 |" in md and "| **total** | 1 | 1 |" in md
    assert "first command of the run is `ax map`: B 1/1, C 0/1." in md
    assert json.loads(out.with_suffix(".json").read_text()) == json.loads(json.dumps(a))
