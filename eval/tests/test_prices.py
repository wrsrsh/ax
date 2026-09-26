import json
from pathlib import Path

PRICES = Path(__file__).resolve().parent.parent / "prices.json"


def test_prices_are_positive_floats():
    p = json.loads(PRICES.read_text())
    assert p["model"] == "gpt-6-astra"
    for k in ("input", "cached_input", "output"):
        v = p["per_million"][k]
        assert isinstance(v, float), k
        assert v > 0, k
