import shutil
import subprocess
from pathlib import Path

import pytest

from ax_eval.capture import catalog_without_apply_patch, nested_tools, run

CATALOG = Path.home() / ".codex/model-catalogs/azure-foundry.json"

needs_codex = pytest.mark.skipif(not shutil.which("codex") or not CATALOG.exists(), reason="needs codex + its model catalog")


@needs_codex
def test_setup_c_drops_apply_patch_only(tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _, b = run(["msg:hi"], repo, CATALOG)
    _, c = run(["msg:hi"], repo, catalog_without_apply_patch(CATALOG, tmp_path / "c.json"))
    tb, tc = set(nested_tools(b)), set(nested_tools(c))
    assert "apply_patch" in tb and "exec_command" in tb
    assert tb - tc == {"apply_patch"} and tc <= tb
