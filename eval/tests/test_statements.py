from ax_eval.statements import changed_symbols, clean, diff_size, leaks, mentions, split

PATCH = """diff --git a/src/utils/url.ts b/src/utils/url.ts
--- a/src/utils/url.ts
+++ b/src/utils/url.ts
@@ -10,3 +10,4 @@ export const getPath = (request: Request): string => {
-  const x = 1
+  const tryDecodeURI = 2
+  return x
"""


def test_clean_strips_templates():
    body = "Fixes a bug.\n\n<!-- hidden -->\n### The author should do the following, if applicable\n\n- [x] Add tests\n- [ ] Run tests\n\n## Why\nbecause"
    out = clean(body)
    assert "hidden" not in out and "[x]" not in out and "author should" not in out
    assert out.startswith("Fixes a bug.") and "because" in out


def test_leaks():
    t = {"src_files": ["src/utils/url.ts"], "gold_patch": PATCH}
    assert "tryDecodeURI" in changed_symbols(PATCH)
    assert leaks("the getPath helper breaks on %2F", t) == []
    assert mentions("the getPath helper breaks on %2F", t) == ["getPath"]
    assert leaks("look at src/utils/url.ts", t) == ["src/utils/url.ts"]
    assert leaks("routing drops encoded slashes", t) == []


def test_split_is_seeded_and_stratified():
    tasks = [{"id": f"t{i}", "gold_patch": "+x\n" * i} for i in range(1, 41)]
    a = split(tasks, 10, 7)
    b = split(tasks, 10, 7)
    assert a == b
    assert sum(v == "dev" for v in a.values()) == 10
    dev_sizes = sorted(diff_size(t) for t in tasks if a[t["id"]] == "dev")
    assert dev_sizes[0] <= 4 and dev_sizes[-1] >= 37
