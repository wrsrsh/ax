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
from ax_eval.setups import codex_args, write_codex_home


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
