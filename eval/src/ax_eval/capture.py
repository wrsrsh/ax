"""run codex (or claude code) against a fake api and keep what it printed. used
to make parser fixtures and to check which tools a setup exposes, without any
model calls."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ax_eval import fakeapi_anthropic
from ax_eval.fakeapi import Script, serve
from ax_eval.setups import claude_args, codex_args, write_codex_home


def _clean_env() -> dict[str, str]:
    # a fake run never needs a real key
    return {k: v for k, v in os.environ.items() if not re.search(r"OPENAI|AZURE|API_KEY", k)}


def run(steps: list[str], repo: Path, catalog: Path, extra_path: str = "", setup: str = "B") -> tuple[list[dict], list[dict]]:
    """(codex --json events, recorded request bodies). `catalog` is the source
    catalog; setup C strips apply_patch from it."""
    with tempfile.TemporaryDirectory(dir=Path.home()) as tmp:
        rec = Path(tmp) / "req.jsonl"
        srv, port = serve(Script(steps, rec))
        try:
            home = write_codex_home(Path(tmp) / "codex-home", setup, f"http://127.0.0.1:{port}/v1", "FAKE_KEY", catalog)
            env = {**_clean_env(), "CODEX_HOME": str(home), "FAKE_KEY": "dummy"}
            if extra_path:
                env["PATH"] = f"{extra_path}:{env['PATH']}"
            args = ["codex", "exec", *codex_args(setup), "-C", str(repo), "go"]
            out = subprocess.run(args, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120).stdout
        finally:
            srv.shutdown()
        events = [json.loads(l) for l in out.splitlines() if l.startswith("{")]
        reqs = [json.loads(l) for l in rec.read_text().splitlines()] if rec.exists() else []
        return events, reqs


def run_claude(steps: list[str], repo: Path, setup: str = "B", *, model: str = "claude-opus-5", effort: str = "medium",
               max_turns: int = 20, extra_path: str = "", env_extra: dict | None = None) -> tuple[list[dict], list[dict]]:
    """(claude stream-json events, recorded request bodies) for the host's claude
    against the fake messages api. the env is built from nothing: running this
    from inside a claude code session must not hand it that session's vars."""
    with tempfile.TemporaryDirectory(dir=Path.home()) as tmp:
        rec = Path(tmp) / "req.jsonl"
        srv, port = fakeapi_anthropic.serve(fakeapi_anthropic.Script(steps, rec))
        try:
            (Path(tmp) / "claude-home").mkdir()
            path = os.environ.get("PATH", "/usr/bin:/bin")
            env = {
                "PATH": f"{extra_path}:{path}" if extra_path else path, "HOME": tmp, "LANG": "C.UTF-8",
                "CLAUDE_CONFIG_DIR": f"{tmp}/claude-home", "DISABLE_AUTOUPDATER": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}", "ANTHROPIC_API_KEY": "dummy", **(env_extra or {}),
            }
            args = [shutil.which("claude") or "claude", *claude_args(setup, model, effort, max_turns)]
            out = subprocess.run(args, env=env, cwd=repo, input="go", capture_output=True, text=True, timeout=120).stdout
        finally:
            srv.shutdown()
        events = [json.loads(l) for l in out.splitlines() if l.startswith("{")]
        reqs = [json.loads(l) for l in rec.read_text().splitlines()] if rec.exists() else []
        return events, reqs


def claude_tools(reqs: list[dict]) -> list[str]:
    """tool names claude code offered in its first agent request."""
    agent = [r["body"] for r in reqs if r.get("method") == "POST" and fakeapi_anthropic.offers_bash(r.get("body") or {})]
    return [t["name"] for t in agent[0].get("tools", [])] if agent else []


def nested_tools(reqs: list[dict]) -> list[str]:
    """tool names codex offered in its first request (code-mode nested tools included)."""
    names = []
    body = reqs[0]["body"] if reqs else {}
    for item in body.get("input", []):
        if item.get("type") != "additional_tools":
            continue
        for ns in item.get("tools", []):
            for t in ns.get("tools", []):
                names.append(t.get("name"))
                if t.get("name") == "exec":
                    names += re.findall(r"^### `([a-z_0-9]+)`", t.get("description", ""), re.M)
    return names
