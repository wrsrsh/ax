from ax_eval import chains
from ax_eval.chains import check_script, chain_files, greedy, kinds_for, record, reference_patches, src_like


def task(i, pr, files, **kw):
    return {"id": f"t{i}", "pr": pr, "base": f"base{i}", "commit": f"fix{i}", "image": "img", "src_files": files,
            "gold_patch": f"gold{i}", "test_patch": f"--- a/src/t{i}.test.ts\n+++ b/src/t{i}.test.ts\n",
            "fail_to_pass": ["f"], "pass_to_pass": ["p"], **kw}


def test_src_like_and_files():
    assert src_like("src/a.ts") and src_like("src/jsx/b.tsx")
    assert not src_like("src/a.test.ts") and not src_like("docs/a.ts") and not src_like("src/a.json")
    ts = [task(0, 1, ["src/a.ts", "src/a.test.ts"]), task(1, 2, ["src/b.ts", "src/a.ts"])]
    assert chain_files(ts) == ["src/a.ts", "src/b.ts"]


def test_kinds_rotate():
    assert kinds_for(0, 4) == ["insert", "upstream", "fmt"]  # never upstream after fmt
    assert kinds_for(1, 3) == ["upstream", "fmt"]
    assert kinds_for(2, 4) == ["upstream", "insert", "fmt"]
    assert kinds_for(1, 2) == ["fmt"]
    assert kinds_for(5, 1) == []


def test_check_script_order():
    ts = [task(0, 1, ["src/a.ts"]), task(1, 2, ["src/b.ts"])]
    s = check_script("base0", ts, {0: "up1"})
    lines = s.splitlines()
    assert "git checkout -q -f base0" in lines[1]
    assert sum("merge-base --is-ancestor" in l for l in lines) == 2
    i_test0 = next(i for i, l in enumerate(lines) if "/p/t0.test" in l)
    i_gold0 = next(i for i, l in enumerate(lines) if "/p/t0.gold" in l)
    i_up = next(i for i, l in enumerate(lines) if "up-up1.patch" in l)
    i_gold1 = next(i for i, l in enumerate(lines) if "/p/t1.gold" in l)
    assert i_test0 < i_gold0 < i_up < i_gold1
    # hidden test files go back to the anchor before their patch is checked
    assert any("git checkout -q base0 -- src/t1.test.ts" in l for l in lines[:i_gold1 + 2])
    assert lines[-1] == "echo OK"


def test_greedy_prefers_shared_files_and_stays_disjoint():
    ts = [task(0, 10, ["src/a.ts"]), task(1, 11, ["src/x.ts"]), task(2, 12, ["src/a.ts"]), task(3, 13, ["src/y.ts"]),
          task(4, 14, ["src/z.ts"])]
    bad = {("t1", "t3")}

    def ok(chain):
        ids = [t["id"] for t in chain]
        return not any((a, b) in bad for a in ids for b in ids)

    out = greedy(ts, ok, max_len=3)
    ids = [[t["id"] for t in c] for c in out]
    assert {"t0", "t2"} <= set(ids[0])  # the pair sharing src/a.ts goes first
    flat = [i for c in ids for i in c]
    assert len(flat) == len(set(flat))
    for c in out:
        assert 2 <= len(c) <= 3
        assert [t["pr"] for t in c] == sorted(t["pr"] for t in c)
        assert ok(c)


def test_greedy_max_len_and_rejects():
    ts = [task(i, i, [f"src/{i}.ts"]) for i in range(6)]
    assert all(len(c) == 2 for c in greedy(ts, lambda c: True, max_len=2))
    assert greedy(ts, lambda c: False) == []


def test_reference_patches():
    ts = [task(i, i, ["src/a.ts"]) for i in range(3)]
    wcs = [{"after": 0, "kind": "upstream", "patch": "UP0"}, {"after": 1, "kind": "fmt"}]
    before = reference_patches(ts, wcs, 1, 1, 1)
    assert list(before) == ["00a-gold", "00b-upstream", "99-tests"] and before["99-tests"] == ts[1]["test_patch"]
    after = reference_patches(ts, wcs, 1, 2, 1)
    assert sorted(after) == list(after) == ["00a-gold", "00b-upstream", "01a-gold", "99-tests"]
    first = reference_patches(ts, wcs, 0, 1, 0)
    assert list(first) == ["00a-gold", "99-tests"]  # the upstream diff comes after step 0's work
    end = reference_patches(ts, wcs, 0, 3, 2)
    assert list(end) == ["00a-gold", "00b-upstream", "01a-gold", "02a-gold", "99-tests"] and end["99-tests"] == ts[0]["test_patch"]


def test_record():
    ts = [task(0, 1, ["src/a.ts"]), task(1, 2, ["src/a.ts", "src/b.ts"])]
    r = record(3, ts, [{"after": 0, "kind": "insert", "files": ["src/a.ts", "src/b.ts"]}])
    assert r["id"] == "chain-03" and r["anchor"] == "base0" and r["tasks"] == ["t0", "t1"]
    assert r["shared_files"] == ["src/a.ts"] and not r["validated"]
    assert [s["task"] for s in r["steps"]] == ["t0", "t1"]


def test_validate_drops_and_keeps_leftovers(monkeypatch):
    ts = {f"t{i}": task(i, i, ["src/a.ts"]) for i in range(4)}

    def fake(chain, wcs, k):
        t = chain[k]
        empty = t["id"] == "t1"
        return {"task": t["id"], "error": None, "fail_to_pass": [] if empty else ["f"], "pass_to_pass": [], "flaky": [], "at_end": []}

    monkeypatch.setattr(chains, "validate_step", fake)
    good = record(0, [ts["t2"], ts["t3"]], [])
    bad = record(1, [ts["t0"], ts["t1"], ts["t3"]], [])
    kept, rest = chains.validate([good, bad], ts, jobs=2, log=lambda *_: None)
    assert [r["tasks"] for r in kept] == [["t2", "t3"]] and kept[0]["validated"]
    assert [[t["id"] for t in c] for c in rest] == [["t0", "t3"]]
