"""run codex against the fake api and keep what it printed. used to make parser
fixtures and to check which tools a setup exposes, without any model calls."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from ax_eval.fakeapi import Script, serve

DISABLED = ["goals", "multi_agent", "apps", "browser_use", "computer_use", "image_generation", "in_app_browser", "plugins", "hooks"]


def codex_home(root: Path, port: int, catalog: Path) -> Path:
    home = root / "codex-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(
        f'''model = "gpt-6-astra"
model_provider = "fake"
model_catalog_json = "{catalog}"
model_reasoning_effort = "medium"
[agents]
max_concurrent_threads_per_session = 1
[model_providers.fake]
name = "fake"
base_url = "http://127.0.0.1:{port}/v1"
env_key = "FAKE_KEY"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0
'''
    )
    return home


def run(steps: list[str], repo: Path, catalog: Path, extra_path: str = "") -> tuple[list[dict], list[dict]]:
    """(codex --json events, recorded request bodies)"""
    with tempfile.TemporaryDirectory(dir=Path.home()) as tmp:
        rec = Path(tmp) / "req.jsonl"
        srv, port = serve(Script(steps, rec))
        try:
            home = codex_home(Path(tmp), port, catalog)
            env = {**os.environ, "CODEX_HOME": str(home), "FAKE_KEY": "dummy"}
            if extra_path:
                env["PATH"] = f"{extra_path}:{env['PATH']}"
            args = ["codex", "exec", "--json", "--ephemeral", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox"]
            for f in DISABLED:
                args += ["--disable", f]
            out = subprocess.run([*args, "-C", str(repo), "go"], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120).stdout
        finally:
            srv.shutdown()
        events = [json.loads(l) for l in out.splitlines() if l.startswith("{")]
        reqs = [json.loads(l) for l in rec.read_text().splitlines()] if rec.exists() else []
        return events, reqs


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


def catalog_without_apply_patch(src: Path, dst: Path, model: str = "gpt-6-astra") -> Path:
    """setup C: the same catalog minus apply_patch for `model`."""
    data = json.loads(src.read_text())

    def strip(x):
        if isinstance(x, dict):
            if (x.get("slug") or x.get("id")) == model:
                x.pop("apply_patch_tool_type", None)
            for v in x.values():
                strip(v)
        elif isinstance(x, list):
            for v in x:
                strip(v)

    strip(data)
    dst.write_text(json.dumps(data))
    return dst
