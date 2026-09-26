from ax_eval.validate import parse_report, runnable, split


def test_parse_report():
    rep = {
        "testResults": [
            {"name": "/w/src/a.test.ts", "status": "passed", "assertionResults": [{"fullName": "a works", "status": "passed"}]},
            {"name": "/w/src/b.test.ts", "status": "failed", "assertionResults": []},
        ]
    }
    assert parse_report(rep) == {"src/a.test.ts::a works": "passed", "src/b.test.ts::<file>": "failed"}


def test_split():
    base = {"t1": "passed", "t2": "failed", "t4": "passed"}
    golds = [
        {"t1": "passed", "t2": "passed", "t3": "passed", "t4": "passed"},
        {"t1": "passed", "t2": "passed", "t3": "passed", "t4": "failed"},
        {"t1": "passed", "t2": "passed", "t3": "passed", "t4": "passed"},
    ]
    f2p, p2p, flaky = split(base, golds)
    assert f2p == ["t2", "t3"]
    assert p2p == ["t1"]
    assert flaky == ["t4"]


def test_runnable():
    assert runnable(["src/a.test.ts", "runtime-tests/deno/x.test.ts", "src/b.ts"]) == ["src/a.test.ts"]
