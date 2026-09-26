import json
import shutil
import subprocess

import pytest

from ax_eval import images
from ax_eval.images import CODEX_VERSION, agent_tag, dockerfile, parse_labels
from ax_eval.parity import ROOT


def test_agent_tag():
    assert agent_tag("ax-hono-deps:c83c3031a376", True) == "ax-agent:c83c3031a376-ax"
    assert agent_tag("ax-hono-deps:c83c3031a376", False) == "ax-agent:c83c3031a376-noax"
    with pytest.raises(ValueError):
        agent_tag("ax-hono-deps", True)


def test_parse_labels():
    assert parse_labels('{"org.ax.commit":"abc123","org.ax.codex":"0.156.0"}\n') == {
        "org.ax.commit": "abc123",
        "org.ax.codex": "0.156.0",
    }
    assert parse_labels("null\n") == {}
    assert parse_labels("") == {}


def test_dockerfile():
    labels = {"org.ax.commit": "abc-dirty", "org.ax.task-image": "ax-hono-deps:x"}
    noax = dockerfile("ax-hono-deps:x", False, labels)
    ax = dockerfile("ax-hono-deps:x", True, labels)
    assert noax.startswith("FROM ax-hono-deps:x\n")
    assert f"@openai/codex@{CODEX_VERSION} " in noax and "safe.directory" in noax
    # the only thing ever copied in is the ax binary
    assert "COPY" not in noax and "ADD" not in noax
    assert [l for l in ax.splitlines() if l.startswith(("COPY", "ADD"))] == ["COPY ax /usr/local/bin/ax"]
    assert 'org.ax.commit="abc-dirty"' in ax


def _image():
    if not shutil.which("docker") or not shutil.which("musl-gcc"):
        return None
    have = lambda img: subprocess.run(["docker", "image", "inspect", img], capture_output=True).returncode == 0  # noqa: E731
    return next((i for i in images.final_images() if have(i)), None)


@pytest.mark.docker
@pytest.mark.skipif(not _image(), reason="needs docker, musl-tools and a locally built task image")
def test_agent_image_runs():
    task_image = _image()
    ax_bin = images.build_ax_static(ROOT)
    tag = images.agent_image(task_image, True, ax_bin)
    assert tag == agent_tag(task_image, True)
    labels = images.image_labels(tag)
    assert labels["org.ax.sha256"] == images.sha256(ax_bin) and labels["org.ax.commit"] != "unknown"
    # no codex config/keys baked in (checked before codex runs, it creates ~/.codex)
    script = "set -e; test ! -e /root/.codex; ax --version; codex --version; node -e 1; ax map >/dev/null; git status --short >/dev/null"
    r = subprocess.run(["docker", "run", "--rm", "--network", "none", "-w", "/w", tag, "bash", "-c", script], capture_output=True, text=True)
    out = r.stdout.splitlines()
    assert r.returncode == 0, r.stderr
    assert out[0].startswith("ax ") and out[1] == f"codex-cli {CODEX_VERSION}"
    assert len(out) == 2
    # cached: same binary, no rebuild
    assert images.agent_image(task_image, True, ax_bin) == tag
    assert json.dumps(images.image_labels(tag)) == json.dumps(labels)
