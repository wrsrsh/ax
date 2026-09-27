"""the setups a task can run under, and the codex config for each.

A: stock codex + a placebo AGENTS note of the same token length as B's.
B: stock codex + the ax note, ax on PATH.
C: B without apply_patch (the model catalog loses `apply_patch_tool_type`).

Ar / Br / Cr: the same three with codex's code mode off. stock codex 0.156.0
gives gpt-6-astra one `exec` javascript tool and nests exec_command /
apply_patch inside it (`tool_mode = "code_mode_only"` in the catalog); dropping
that key gives the model plain function tools again. no feature flag does it.

config.toml never holds a secret: the provider reads its key from `env_key`
at run time.

claude code runs A/B/C only (code mode is a codex thing). the same note goes in
as CLAUDE.md, and C takes away its edit tools instead of apply_patch. see
claude_args and eval/report/claude_code_agent.md.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from ax_eval.util import EVAL

CORE = ("A", "B", "C")
RAW = ("Ar", "Br", "Cr")
SETUPS = CORE + RAW
NOTES = EVAL / "setups"
DISABLED = ("goals", "multi_agent", "apps", "browser_use", "computer_use", "image_generation", "in_app_browser", "plugins", "hooks")
CATALOG_NAME = "model-catalog.json"


def _check(setup: str) -> str:
    if setup not in SETUPS:
        raise ValueError(f"unknown setup {setup!r}, expected one of {SETUPS}")
    return setup


def uses_ax(setup: str) -> bool:
    return _check(setup)[0] != "A"


def raw_tools(setup: str) -> bool:
    return _check(setup).endswith("r")


def base_of(setup: str) -> str:
    """the no-ax setup this one is compared against: A, or Ar for the raw family."""
    return "Ar" if raw_tools(setup) else "A"


def agents_md(setup: str) -> str:
    return (NOTES / ("AGENTS.ax.md" if uses_ax(setup) else "AGENTS.placebo.md")).read_text()


def note_name(agent: str) -> str:
    """where the note goes in /w: codex reads AGENTS.md, claude code CLAUDE.md."""
    return "CLAUDE.md" if agent == "claude" else "AGENTS.md"


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


def catalog_for(setup: str, src: Path, dst: Path, model: str = "gpt-6-astra") -> Path:
    """the source catalog with the keys this setup takes away from `model`:
    apply_patch_tool_type for C/Cr, tool_mode (code mode) for Ar/Br/Cr."""
    drop = set()
    if _check(setup)[0] == "C":
        drop.add("apply_patch_tool_type")
    if raw_tools(setup):
        drop.add("tool_mode")
    data = json.loads(Path(src).read_text())

    def strip(x):
        if isinstance(x, dict):
            if (x.get("slug") or x.get("id")) == model:
                for k in drop:
                    x.pop(k, None)
            for v in x.values():
                strip(v)
        elif isinstance(x, list):
            for v in x:
                strip(v)

    strip(data)
    Path(dst).write_text(json.dumps(data))
    return Path(dst)


def catalog_without_apply_patch(src: Path, dst: Path, model: str = "gpt-6-astra") -> Path:
    return catalog_for("C", src, dst, model)


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
    catalog_for(setup, catalog_src, catalog, model)
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


# claude code 2.1.283. the default -p tool list also has Agent, Cron*,
# Enter/ExitWorktree, ListAgents, NotebookEdit, ReportFindings, ScheduleWakeup,
# SendMessage, Skill, TaskStop, WebFetch, WebSearch and Workflow. those go, the
# way codex loses multi_agent, browser_use and friends. Glob and Grep aren't on
# by default in this version but still exist, so they're asked for by name.
# MultiEdit and TodoWrite are gone (asking for them is silently ignored).
CLAUDE_TOOLS = ("Bash", "Read", "Edit", "Write", "Glob", "Grep")
CLAUDE_EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
CLAUDE_SETTINGS = {"autoMemoryEnabled": False}


def claude_tools(setup: str) -> list[str]:
    if raw_tools(setup):
        raise ValueError(f"setup {setup} is codex-only (code mode)")
    drop = CLAUDE_EDIT_TOOLS if setup == "C" else ()
    return [t for t in CLAUDE_TOOLS if t not in drop]


def claude_args(setup: str, model: str, effort: str, max_turns: int, max_budget_usd: float | None = None) -> list[str]:
    """flags for `claude -p`, prompt on stdin. run with CLAUDE_CONFIG_DIR set to an
    empty dir. only project settings load (that's also what reads /w/CLAUDE.md),
    no mcp servers, no skills, no auto-memory."""
    args = [
        "-p", "--output-format", "stream-json", "--verbose",
        "--model", model, "--effort", effort, "--max-turns", str(int(max_turns)),
        "--permission-mode", "bypassPermissions",
        "--strict-mcp-config", "--setting-sources", "project", "--settings", json.dumps(CLAUDE_SETTINGS),
        "--disable-slash-commands", "--no-session-persistence",
        "--tools", ",".join(claude_tools(setup)),
    ]
    if setup == "C":
        args += ["--disallowedTools", ",".join(CLAUDE_EDIT_TOOLS)]
    if max_budget_usd is not None:
        args += ["--max-budget-usd", f"{max_budget_usd:g}"]
    return args
