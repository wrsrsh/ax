from ax_eval.patch_parity import to_codex

DIFF = """diff --git a/src/a.ts b/src/a.ts
index 1..2 100644
--- a/src/a.ts
+++ b/src/a.ts
@@ -1,2 +1,2 @@
 keep
-old
+new
diff --git a/src/new.ts b/src/new.ts
new file mode 100644
--- /dev/null
+++ b/src/new.ts
@@ -0,0 +1 @@
+hello
diff --git a/gone.ts b/gone.ts
deleted file mode 100644
--- a/gone.ts
+++ /dev/null
@@ -1 +0,0 @@
-bye
diff --git a/x.ts b/y.ts
similarity index 90%
rename from x.ts
rename to y.ts
--- a/x.ts
+++ b/y.ts
@@ -1 +1 @@
-a
+b
"""


def test_to_codex():
    assert to_codex(DIFF) == "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: src/a.ts",
            "@@",
            " keep",
            "-old",
            "+new",
            "*** Add File: src/new.ts",
            "+hello",
            "*** Delete File: gone.ts",
            "*** Update File: x.ts",
            "*** Move to: y.ts",
            "@@",
            "-a",
            "+b",
            "*** End Patch",
        ]
    ) + "\n"
