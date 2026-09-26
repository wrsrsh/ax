import json

from ax_eval.parity import CaseResult, compare, markdown, parse_ax_hits, parse_rg_lines


def test_parse_rg_lines():
    out = "./src/a.ts:12:const a = 1\nsrc/b.py:3:x: int = 2\nweird line\nsrc/c.go:x:nope\n"
    assert parse_rg_lines(out) == {"src/a.ts:12", "src/b.py:3"}


def test_parse_ax_hits_skips_context():
    out = json.dumps(
        {
            "data": [
                {"path": "a.ts", "line": 1},
                {"path": "a.ts", "line": 2, "context": True},
                {"path": "b.ts", "line": 9, "context": False},
            ]
        }
    )
    assert parse_ax_hits(out) == {"a.ts:1", "b.ts:9"}


def test_compare_and_markdown():
    ok = compare("r", "grep", ["x"], {"a:1"}, {"a:1"})
    bad = compare("r", "grep", ["y"], {"a:1", "a:2"}, {"a:1", "b:3"})
    assert ok.ok and not bad.ok
    assert bad.only_rg == ["a:2"] and bad.only_ax == ["b:3"]
    md = markdown([ok, bad], [], {"rg": "14"})
    assert "**1/2 cases identical.**" in md
    assert "### diff: r grep y" in md


def test_case_result_errors_count_as_not_ok():
    assert not CaseResult("r", "grep", ["-t", "x"], -1, -1, ["ax errored"], []).ok
