"""agent images: a task image (ax-hono-deps:<hash>) plus the agent cli, and optionally ax.

    ax-agent:<hash>-noax          task image + codex + git safe.directory
    ax-agent:<hash>-ax            same, plus the ax binary at /usr/local/bin/ax
    ax-agent:<hash>-claude-noax   task image + claude code + git safe.directory
    ax-agent:<hash>-claude-ax     same, plus ax

the ax binary is a static musl build (x86_64-unknown-linux-musl, needs
musl-tools on the host for the tree-sitter c code). a plain host build doesn't
work: the host is ubuntu 24.04 (glibc 2.39) and the task images are
node:24-bookworm (glibc 2.36), and rust's std pulls in weak GLIBC_2.39 symbols
(pidfd_spawnp, pidfd_getpid), so it dies with "version `GLIBC_2.39' not found".
the musl build is static-pie, needs nothing from the image, and `ax --version`,
`ax map`, `ax outline`, `ax def` all run fine inside the task images.

images are built once and reused; an -ax image is rebuilt only if the binary
passed in differs from the one baked in (org.ax.sha256 label). the build
context holds the dockerfile and the ax binary, nothing else: no codex config,
no keys.

    uv run python -m ax_eval.images --task-image ax-hono-deps:<hash> [--no-ax] [--agent claude]
    uv run python -m ax_eval.images --all [--agent claude]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

from ax_eval.util import ROOT, TASKS, jsonl, sh

CODEX_VERSION = "0.156.0"  # matches `codex --version` on the host
CLAUDE_VERSION = "2.1.283"  # matches `claude --version` on the host
AGENTS = ("codex", "claude")
MUSL = "x86_64-unknown-linux-musl"


def agent_tag(task_image: str, with_ax: bool, agent: str = "codex") -> str:
    name, sep, h = task_image.partition(":")
    if not sep or not h:
        raise ValueError(f"task image needs a tag: {task_image!r}")
    if agent not in AGENTS:
        raise ValueError(f"unknown agent {agent!r}")
    pre = "" if agent == "codex" else f"{agent}-"
    return f"ax-agent:{h}-{pre}{'ax' if with_ax else 'noax'}"


def parse_labels(inspect_out: str) -> dict[str, str]:
    """output of `docker image inspect -f '{{json .Config.Labels}}'`."""
    s = inspect_out.strip()
    return (json.loads(s) or {}) if s else {}


def image_labels(tag: str) -> dict[str, str] | None:
    """None if the image isn't there."""
    r = sh("docker", "image", "inspect", "-f", "{{json .Config.Labels}}", tag, check=False)
    return parse_labels(r.stdout) if r.returncode == 0 else None


def dockerfile(task_image: str, with_ax: bool, labels: dict[str, str], agent: str = "codex") -> str:
    pkg = f"@openai/codex@{CODEX_VERSION}" if agent == "codex" else f"@anthropic-ai/claude-code@{CLAUDE_VERSION}"
    lines = [
        f"FROM {task_image}",
        f"RUN npm i -g {pkg} && npm cache clean --force"
        " && git config --system --add safe.directory '*'",
    ]
    if with_ax:
        lines.append("COPY ax /usr/local/bin/ax")
    lines.append("LABEL " + " ".join(f"{k}={json.dumps(v)}" for k, v in sorted(labels.items())))
    return "\n".join(lines) + "\n"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _cargo() -> str:
    c = shutil.which("cargo") or str(Path.home() / ".cargo/bin/cargo")
    if not Path(c).exists():
        raise RuntimeError("cargo not found")
    return c


def _commit(repo_root: Path) -> str:
    r = sh("git", "-C", str(repo_root), "rev-parse", "HEAD", check=False)
    if r.returncode:
        return "unknown"
    dirty = sh("git", "-C", str(repo_root), "status", "--porcelain", "--", "ax", check=False).stdout.strip()
    return r.stdout.strip() + ("-dirty" if dirty else "")


def build_ax_static(repo_root: Path) -> Path:
    """release musl build of ax; writes the source commit next to it (ax.commit)."""
    if not shutil.which("musl-gcc"):
        raise RuntimeError("musl-gcc not found (apt install musl-tools)")
    cargo = _cargo()
    rustup = Path(cargo).with_name("rustup")
    if rustup.exists():
        sh(str(rustup), "target", "add", MUSL)
    manifest = repo_root / "ax" / "Cargo.toml"
    r = sh(cargo, "build", "--release", "--target", MUSL, "--manifest-path", str(manifest), check=False)
    if r.returncode:
        raise RuntimeError(f"cargo build failed:\n{r.stderr[-2000:]}")
    bin = repo_root / "ax" / "target" / MUSL / "release" / "ax"
    bin.with_name("ax.commit").write_text(_commit(repo_root) + "\n")
    return bin


def _bin_commit(ax_bin: Path) -> str:
    side = ax_bin.with_name("ax.commit")
    return side.read_text().strip() if side.exists() else _commit(ax_bin.parent)


def agent_image(task_image: str, with_ax: bool, ax_bin: Path | None = None, agent: str = "codex") -> str:
    tag = agent_tag(task_image, with_ax, agent)
    have = image_labels(tag)
    if have is not None and (not with_ax or ax_bin is None):
        return tag
    labels = {"org.ax.task-image": task_image}
    labels |= {"org.ax.codex": CODEX_VERSION} if agent == "codex" else {"org.ax.claude": CLAUDE_VERSION}
    if with_ax:
        if ax_bin is None:
            ax_bin = build_ax_static(ROOT)
        labels |= {"org.ax.commit": _bin_commit(ax_bin), "org.ax.sha256": sha256(ax_bin)}
        if have is not None and have.get("org.ax.sha256") == labels["org.ax.sha256"]:
            return tag
    with tempfile.TemporaryDirectory() as ctx:
        Path(ctx, "Dockerfile").write_text(dockerfile(task_image, with_ax, labels, agent))
        if with_ax:
            shutil.copy2(ax_bin, Path(ctx, "ax"))
        r = sh("docker", "build", "-q", "-t", tag, ctx, check=False)
        if r.returncode:
            raise RuntimeError(f"docker build {tag} failed:\n{r.stderr[-2000:]}")
    return tag


def final_images() -> list[str]:
    return sorted({t["image"] for t in jsonl(TASKS / "final.jsonl")})


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--task-image")
    g.add_argument("--all", action="store_true", help="both variants for every image in tasks/final.jsonl")
    p.add_argument("--no-ax", action="store_true")
    p.add_argument("--agent", choices=AGENTS, default="codex")
    a = p.parse_args(argv)
    ax_bin = None if (a.task_image and a.no_ax) else build_ax_static(ROOT)
    jobs = [(i, v) for i in final_images() for v in (False, True)] if a.all else [(a.task_image, not a.no_ax)]
    for img, with_ax in jobs:
        t0 = time.time()
        tag = agent_image(img, with_ax, ax_bin if with_ax else None, a.agent)
        print(f"{tag}  ({time.time() - t0:.1f}s)", file=sys.stderr, flush=True)
        print(tag, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
