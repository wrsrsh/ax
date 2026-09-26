import json
import os
import tomllib

import pytest

from ax_eval import setups
from ax_eval.setups import SETUPS, agents_md, codex_args, provider_toml, uses_ax, write_codex_home

MODEL = "gpt-6-astra"


@pytest.fixture
def catalog(tmp_path):
    p = tmp_path / "src-catalog.json"
    p.write_text(json.dumps({"models": [
        {"slug": MODEL, "apply_patch_tool_type": "freeform", "x": 1},
        {"slug": "other", "apply_patch_tool_type": "freeform"},
    ]}))
    return p


def models(home):
    cfg = tomllib.loads((home / "config.toml").read_text())
    return cfg, {m["slug"]: m for m in json.loads(open(cfg["model_catalog_json"]).read())["models"]}


@pytest.mark.parametrize("setup", SETUPS)
def test_config_per_setup(tmp_path, catalog, setup, monkeypatch):
    monkeypatch.setenv("SECRET_TEST_KEY", "sk-should-never-appear")
    home = write_codex_home(tmp_path / setup, setup, "http://127.0.0.1:9/v1", "SECRET_TEST_KEY", catalog)
    assert home == tmp_path / setup
    text = (home / "config.toml").read_text()
    assert "sk-should-never-appear" not in text
    for k, v in os.environ.items():
        if any(s in k for s in ("KEY", "TOKEN", "SECRET")) and len(v) >= 8:
            assert v not in text, k
    cfg, ms = models(home)
    assert cfg["model"] == MODEL and cfg["model_reasoning_effort"] == "medium"
    assert cfg["agents"] == {"max_concurrent_threads_per_session": 1}
    assert os.path.dirname(cfg["model_catalog_json"]) == str(home)
    prov = cfg["model_providers"][cfg["model_provider"]]
    assert prov == {
        "name": cfg["model_provider"],
        "base_url": "http://127.0.0.1:9/v1",
        "env_key": "SECRET_TEST_KEY",
        "wire_api": "responses",
        "request_max_retries": 0,
        "stream_max_retries": 0,
    }
    assert ("apply_patch_tool_type" in ms[MODEL]) == (setup != "C")
    assert ms[MODEL]["x"] == 1 and "apply_patch_tool_type" in ms["other"]


def test_effort_and_model(tmp_path, catalog):
    cfg, _ = models(write_codex_home(tmp_path, "B", "http://h/v1", "K", catalog, model="other", effort="high"))
    assert cfg["model"] == "other" and cfg["model_reasoning_effort"] == "high"


def test_provider_toml():
    cfg = tomllib.loads(provider_toml("p", "http://h/v1", "MY_KEY", "chat", request_max_retries=2, stream_max_retries=3))
    assert cfg["model_providers"]["p"]["wire_api"] == "chat"
    assert cfg["model_providers"]["p"]["request_max_retries"] == 2
    assert cfg["model_providers"]["p"]["stream_max_retries"] == 3
    with pytest.raises(ValueError):
        provider_toml("p", "http://h/v1", "sk-proj-abc123-real-key")


def test_setup_flags():
    assert [uses_ax(s) for s in SETUPS] == [False, True, True]
    with pytest.raises(ValueError):
        uses_ax("D")
    assert agents_md("B") == agents_md("C") != agents_md("A")
    assert "ax edit" in agents_md("B") and "ax " not in agents_md("A")


def test_codex_args_same_everywhere():
    a = codex_args("A")
    assert a == codex_args("B") == codex_args("C")
    for f in ["--json", "--ephemeral", "--ignore-rules", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox"]:
        assert f in a
    # it would make codex skip the config we write
    assert "--ignore-user-config" not in a
    disabled = [a[i + 1] for i, x in enumerate(a) if x == "--disable"]
    assert disabled == list(setups.DISABLED)


def test_notes_token_parity():
    tiktoken = pytest.importorskip("tiktoken")
    try:
        enc = tiktoken.get_encoding("o200k_base")
    except Exception as e:  # encoding not cached and no network
        pytest.skip(str(e))
    a, b = len(enc.encode(agents_md("A"))), len(enc.encode(agents_md("B")))
    assert abs(a - b) <= 0.05 * max(a, b), (a, b)
