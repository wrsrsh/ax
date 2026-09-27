import json
import shutil
import subprocess

import pytest

from ax_eval.capture import claude_tools, run_claude
from ax_eval.images import CLAUDE_VERSION


def _claude_version():
    if not shutil.which("claude"):
        return None
    return subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.split(" ")[0].strip()


# the tool surface below is what 2.1.283 does; another version may differ
needs_claude = pytest.mark.skipif(_claude_version() != CLAUDE_VERSION, reason=f"needs claude code {CLAUDE_VERSION} on PATH")


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    (r / "CLAUDE.md").write_text("ax-eval-note-marker\n")
    return r


def text_of(content):
    return content if isinstance(content, str) else "\n".join(b.get("text", "") for b in content)


@needs_claude
def test_tools_per_setup(repo):
    tools = {}
    for s in ("A", "B", "C"):
        events, reqs = run_claude(["msg:hi"], repo, s)
        assert events[-1]["type"] == "result" and events[-1]["subtype"] == "success", s
        body = next(r["body"] for r in reqs if r.get("method") == "POST")
        assert body["model"] == "claude-opus-5" and body["output_config"]["effort"] == "medium"
        # the note went in as CLAUDE.md, and nothing else from outside the repo did
        assert "ax-eval-note-marker" in text_of(body["messages"][0]["content"])
        assert "# Memory" not in text_of(body["system"])
        init = events[0]
        assert init["mcp_servers"] == [] and init["skills"] == [] and init["slash_commands"] == []
        assert init["apiKeySource"] == "ANTHROPIC_API_KEY"
        tools[s] = claude_tools(reqs)
        assert tools[s] == init["tools"], s
    assert tools["A"] == tools["B"] == ["Bash", "Edit", "Glob", "Grep", "Read", "Write"]
    assert tools["C"] == ["Bash", "Glob", "Grep", "Read"]


@needs_claude
def test_setup_c_edit_goes_nowhere(repo):
    (repo / "a.txt").write_text("y\n")
    edit = json.dumps({"file_path": str(repo / "a.txt"), "old_string": "y", "new_string": "z"})
    events, _ = run_claude([f"tool:Edit {edit}", "msg:done"], repo, "C")
    res = [b for e in events if e["type"] == "user" for b in e["message"]["content"] if b.get("type") == "tool_result"]
    assert res and res[0]["is_error"] and "No such tool available: Edit" in text_of(res[0]["content"])
    assert (repo / "a.txt").read_text() == "y\n"


@needs_claude
def test_max_turns_stops_the_run(repo):
    events, reqs = run_claude(["sh:echo 1", "sh:echo 2", "sh:echo 3", "msg:done"], repo, "A", max_turns=2)
    assert events[-1]["subtype"] == "error_max_turns" and events[-1]["terminal_reason"] == "max_turns"
    assert sum(r.get("method") == "POST" for r in reqs) == 2
