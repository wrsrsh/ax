from ax_eval.mine import classify, qualifies


def test_classify():
    assert classify("src/router/trie-router/node.ts") == "source"
    assert classify("src/router/trie-router/node.test.ts") == "test"
    assert classify("src/jsx/dom/render.test.tsx") == "test"
    assert classify("runtime-tests/deno/app.ts") == "test"
    assert classify("src/helper/__tests__/x.ts") == "test"
    assert classify("tests/test_models.py") == "test"
    assert classify("pkg/server_test.go") == "test"
    assert classify("package.json") == "dependency"
    assert classify("pnpm-lock.yaml") == "dependency"
    assert classify("docs/MIGRATION.md") == "other"
    assert classify("benchmarks/routers/src/bench.mts") == "other"
    assert classify("vite.config.ts") == "other"
    assert classify("src/types.d.ts") == "other"
    assert classify("README.md") == "other"


def test_qualifies():
    assert qualifies(["src/a.ts", "src/a.test.ts"]) == (True, "")
    assert qualifies(["src/a.ts"]) == (False, "no test changes")
    assert qualifies(["src/a.test.ts"]) == (False, "0 source files")
    six = [f"src/{i}.ts" for i in range(6)] + ["src/x.test.ts"]
    assert qualifies(six) == (False, "6 source files")
    assert qualifies(["src/a.ts", "src/a.test.ts", "package.json"]) == (False, "touches dependencies")
