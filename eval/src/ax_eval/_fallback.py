"""stand-ins for ax_eval.images and ax_eval.setups until those land. same
interfaces, less care. delete this file once both modules are merged."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from ax_eval.capture import DISABLED, catalog_without_apply_patch
from ax_eval.parity import EVAL

SETUPS = ("A", "B", "C")
REPO = EVAL.parent
CODEX_PKG = Path.home() / ".local/lib/node_modules/@openai/codex"


def uses_ax(setup: str) -> bool:
    return setup in ("B", "C")


def agents_md(setup: str) -> str:
    name = "AGENTS.ax.md" if uses_ax(setup) else "AGENTS.placebo.md"
    return (EVAL / "setups" / name).read_text()


def write_codex_home(dest: Path, setup: str, base_url: str, env_key: str, catalog_src: Path, model: str = "gpt-6-astra", effort: str = "medium") -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    cat = dest / "catalog.json"
    if setup == "C":
        catalog_without_apply_patch(catalog_src, cat, model)
    else:
        shutil.copyfile(catalog_src, cat)
    (dest / "config.toml").write_text(
        f'''model = "{model}"
model_provider = "eval"
model_catalog_json = "{cat}"
model_reasoning_effort = "{effort}"
[agents]
max_concurrent_threads_per_session = 1
[model_providers.eval]
name = "eval"
base_url = "{base_url}"
env_key = "{env_key}"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0
'''
    )
    return dest


def codex_args(setup: str) -> list[str]:
    args = ["--json", "--ephemeral", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox"]
    for f in DISABLED:
        args += ["--disable", f]
    return args


def _sh(*cmd: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True, check=True, **kw)


def _ax_commit() -> str:
    return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or "unknown"


def _ax_src_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((REPO / "ax").glob("src/**/*.rs")) + [REPO / "ax/Cargo.toml", REPO / "ax/Cargo.lock"]:
        h.update(p.read_bytes())
    return h.hexdigest()[:10]


def build_ax() -> Path:
    """ax built against bookworm's glibc (the host binary needs a newer one)."""
    out = EVAL / ".cache" / "ax-bookworm"
    out.mkdir(parents=True, exist_ok=True)
    stamp = out / f"ax-{_ax_src_hash()}"
    if not stamp.exists():
        _sh(
            "docker", "run", "--rm", "-v", f"{REPO / 'ax'}:/src:ro", "-v", f"{out}:/out", "rust:1-bookworm",
            "bash", "-c", "cp -r /src /b && cd /b && cargo build -q --release --target-dir /out/target && cp /out/target/release/ax /out/ax.tmp",
        )
        (out / "ax.tmp").rename(stamp)
    return stamp


def agent_image(task_image: str, with_ax: bool, ax_bin: Path | None = None) -> str:
    base_id = _sh("docker", "image", "inspect", "-f", "{{.Id}}", task_image).stdout.strip()
    codex_v = json.loads((CODEX_PKG / "package.json").read_text())["version"]
    ax_bin = (ax_bin or build_ax()) if with_ax else None
    ax_h = hashlib.sha256(ax_bin.read_bytes()).hexdigest() if ax_bin else ""
    h = hashlib.sha256(f"{base_id} {codex_v} {ax_h}".encode()).hexdigest()[:12]
    tag = f"ax-agent:{h}-{'ax' if with_ax else 'noax'}"
    if subprocess.run(["docker", "image", "inspect", tag], capture_output=True).returncode == 0:
        return tag
    with tempfile.TemporaryDirectory() as tmp:
        ctx = Path(tmp)
        shutil.copytree(CODEX_PKG, ctx / "codex", symlinks=True, ignore=shutil.ignore_patterns("voice"))
        lines = [
            f"FROM {task_image}",
            "COPY codex /usr/local/lib/node_modules/@openai/codex",
            "RUN ln -sf /usr/local/lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex && rm -rf /root/.codex",
        ]
        if ax_bin:
            shutil.copyfile(ax_bin, ctx / "ax")
            lines.append("COPY --chmod=755 ax /usr/local/bin/ax")
            lines.append(f"LABEL ax.commit={_ax_commit()}")
        (ctx / "Dockerfile").write_text("\n".join(lines) + "\n")
        _sh("docker", "build", "-q", "-t", tag, str(ctx))
    return tag
