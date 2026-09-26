import shutil
import subprocess
from pathlib import Path

import pytest

from ax_eval.capture import nested_tools, run
from ax_eval.setups import catalog_without_apply_patch

CATALOG = Path.home() / ".codex/model-catalogs/azure-foundry.json"

needs_codex = pytest.mark.skipif(not shutil.which("codex") or not CATALOG.exists(), reason="needs codex + its model catalog")


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    return r


@needs_codex
def test_setup_c_drops_apply_patch_only(tmp_path, repo):
    _, b = run(["msg:hi"], repo, CATALOG)
    _, c = run(["msg:hi"], repo, catalog_without_apply_patch(CATALOG, tmp_path / "c.json"))
    tb, tc = set(nested_tools(b)), set(nested_tools(c))
    assert "apply_patch" in tb and "exec_command" in tb
    assert tb - tc == {"apply_patch"} and tc <= tb


@needs_codex
def test_tools_per_setup(repo):
    tools = {}
    for s in ("A", "B", "C"):
        events, reqs = run(["msg:hi"], repo, CATALOG, setup=s)
        # the config we wrote was honoured: codex talked to the fake api and finished
        assert reqs and any(e.get("type") == "turn.completed" for e in events), s
        assert reqs[0]["body"]["model"] == "gpt-6-astra"
        assert reqs[0]["body"].get("reasoning", {}).get("effort") == "medium"
        tools[s] = set(nested_tools(reqs))
    assert "apply_patch" in tools["A"] and "apply_patch" in tools["B"]
    assert "apply_patch" not in tools["C"]
    assert tools["A"] == tools["B"] and tools["B"] - tools["C"] == {"apply_patch"}
