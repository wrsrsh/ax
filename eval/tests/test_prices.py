import json
from pathlib import Path

from ax_eval.runner import load_prices

PRICES = Path(__file__).resolve().parent.parent / "prices.json"
MODELS = ("gpt-6-astra", "gpt-6-sol", "gpt-6-luna", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")


def test_prices_are_positive_floats():
    p = json.loads(PRICES.read_text())
    assert p["currency"] == "USD"
    assert set(MODELS) <= set(p["models"])
    for m, e in p["models"].items():
        assert e["source"].startswith("https://"), m
        for k in ("input", "cached_input", "cache_write", "output"):
            v = e["per_million"][k]
            assert isinstance(v, float), (m, k)
            assert v > 0, (m, k)
        assert e["per_million"]["cached_input"] < e["per_million"]["input"] < e["per_million"]["cache_write"], m


def test_default_model_is_astra():
    assert load_prices(PRICES) == {"input": 10.0, "cached_input": 1.0, "cache_write": 12.5, "output": 50.0}
