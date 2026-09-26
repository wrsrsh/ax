"""the three setups every task runs under, and the codex config for each.

A: stock codex + a placebo AGENTS note of the same token length as B's.
B: stock codex + the ax note, ax on PATH.
C: B without apply_patch (the model catalog loses `apply_patch_tool_type`).

config.toml never holds a secret: the provider reads its key from `env_key`
at run time.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

SETUPS = ("A", "B", "C")
NOTES = Path(__file__).resolve().parents[2] / "setups"
DISABLED = ("goals", "multi_agent", "apps", "browser_use", "computer_use", "image_generation", "in_app_browser", "plugins", "hooks")
CATALOG_NAME = "model-catalog.json"


def _check(setup: str) -> str:
    if setup not in SETUPS:
        raise ValueError(f"unknown setup {setup!r}, expected one of {SETUPS}")
    return setup


def uses_ax(setup: str) -> bool:
    return _check(setup) != "A"


def agents_md(setup: str) -> str:
    return (NOTES / ("AGENTS.ax.md" if uses_ax(setup) else "AGENTS.placebo.md")).read_text()


def _s(v: str) -> str:
    # json strings are valid toml basic strings
    return json.dumps(str(v))


def provider_toml(
    name: str,
    base_url: str,
    env_key: str,
    wire_api: str = "responses",
    *,
    request_max_retries: int = 0,
    stream_max_retries: int = 0,
) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env_key):
        raise ValueError("env_key is the name of an env var, not the key itself")
    return (
        f"[model_providers.{name}]\n"
        f"name = {_s(name)}\n"
        f"base_url = {_s(base_url)}\n"
        f"env_key = {_s(env_key)}\n"
        f"wire_api = {_s(wire_api)}\n"
        f"request_max_retries = {int(request_max_retries)}\n"
        f"stream_max_retries = {int(stream_max_retries)}\n"
    )


def catalog_without_apply_patch(src: Path, dst: Path, model: str = "gpt-6-astra") -> Path:
    """setup C: the same catalog minus apply_patch for `model`."""
    data = json.loads(Path(src).read_text())

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
    Path(dst).write_text(json.dumps(data))
    return Path(dst)


def write_codex_home(
    dest: Path,
    setup: str,
    base_url: str,
    env_key: str,
    catalog_src: Path,
    model: str = "gpt-6-astra",
    effort: str = "medium",
    provider: str = "eval",
) -> Path:
    _check(setup)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    catalog = dest / CATALOG_NAME
    if setup == "C":
        catalog_without_apply_patch(catalog_src, catalog, model)
    else:
        shutil.copyfile(catalog_src, catalog)
    (dest / "config.toml").write_text(
        f"model = {_s(model)}\n"
        f"model_provider = {_s(provider)}\n"
        f"model_catalog_json = {_s(catalog)}\n"
        f"model_reasoning_effort = {_s(effort)}\n"
        "\n[agents]\nmax_concurrent_threads_per_session = 1\n\n"
        + provider_toml(provider, base_url, env_key)
    )
    return dest


def codex_args(setup: str) -> list[str]:
    """flags for `codex exec`, identical across setups. run with CODEX_HOME set to
    a write_codex_home dir.

    no --ignore-user-config: in 0.156.0 it skips $CODEX_HOME/config.toml, which is
    the config written above, and codex falls back to api.openai.com. the fresh
    CODEX_HOME already keeps ~/.codex out."""
    _check(setup)
    args = ["--json", "--ephemeral", "--ignore-rules", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox"]
    for f in DISABLED:
        args += ["--disable", f]
    return args
