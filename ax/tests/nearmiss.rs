mod common;
use common::*;
use std::fs;

const GO: &str = "package x\n\nfunc f() int {\n\treturn 1\n}\n";

#[test]
fn tabs_vs_spaces_miss_is_explained_with_anchors() {
    let t = fixture();
    write(t.path(), "x.go", GO);
    let o = ax_in(
        t.path(),
        &["edit", "x.go"],
        "@@ find\n    return 1\n}\n@@ with\n    return 2\n}\n",
    );
    assert_eq!(o.status.code(), Some(1));
    let out = stdout(&o);
    assert!(out.contains("tabs vs spaces"), "{out}");
    assert!(
        out.contains("\n  4:") && out.contains("\treturn 1"),
        "{out}"
    );
    assert_eq!(fs::read_to_string(t.path().join("x.go")).unwrap(), GO);
}

#[test]
fn many_occurrences_list_their_anchors() {
    let t = fixture();
    write(t.path(), "a.ts", "x()\ny()\nx()\n");
    let o = ax_in(t.path(), &["edit", "a.ts"], "@@ find\nx()\n@@ with\nz()\n");
    let out = stdout(&o);
    assert!(out.contains("occurs 2 times"), "{out}");
    assert!(out.contains("\n  1:") && out.contains("\n  3:"), "{out}");
}

#[test]
fn bom_is_invisible_to_find_and_patch_and_kept() {
    let t = fixture();
    fs::write(t.path().join("b.js"), "\u{feff}const a = 1\nconst b = 2\n").unwrap();
    let o = ax_in(
        t.path(),
        &["edit", "b.js"],
        "@@ find\nconst a = 1\n@@ with\nconst a = 10\n",
    );
    assert!(o.status.success(), "{}", stdout(&o));
    assert_eq!(
        fs::read_to_string(t.path().join("b.js")).unwrap(),
        "\u{feff}const a = 10\nconst b = 2\n"
    );
    let p = "--- a/b.js\n+++ b/b.js\n@@ -1,2 +1,2 @@\n-const a = 10\n+const a = 11\n const b = 2\n";
    let o = ax_in(t.path(), &["patch"], p);
    assert!(o.status.success(), "{}", stderr(&o));
    assert_eq!(
        fs::read_to_string(t.path().join("b.js")).unwrap(),
        "\u{feff}const a = 11\nconst b = 2\n"
    );
}

#[test]
fn pure_addition_after_seek_line_not_at_eof() {
    let t = fixture();
    write(
        t.path(),
        "c.py",
        "def a():\n    pass\n\ndef b():\n    pass\n",
    );
    let p =
        "*** Begin Patch\n*** Update File: c.py\n@@ def a():\n+    # added in a\n*** End Patch\n";
    let o = ax_in(t.path(), &["patch"], p);
    assert!(o.status.success(), "{}", stderr(&o));
    assert_eq!(
        fs::read_to_string(t.path().join("c.py")).unwrap(),
        "def a():\n    # added in a\n    pass\n\ndef b():\n    pass\n"
    );
}

#[test]
fn unified_insert_at_top() {
    let t = fixture();
    write(t.path(), "d.txt", "one\ntwo\n");
    let o = ax_in(
        t.path(),
        &["patch"],
        "--- a/d.txt\n+++ b/d.txt\n@@ -0,0 +1 @@\n+zero\n",
    );
    assert!(o.status.success(), "{}", stderr(&o));
    assert_eq!(
        fs::read_to_string(t.path().join("d.txt")).unwrap(),
        "zero\none\ntwo\n"
    );
}

#[test]
fn patch_miss_shows_closest_real_lines() {
    let t = fixture();
    write(t.path(), "x.go", GO);
    let p = "*** Begin Patch\n*** Update File: x.go\n-    return 1\n+    return 2\n*** End Patch\n";
    let o = ax_in(t.path(), &["patch"], p);
    assert_eq!(o.status.code(), Some(1));
    let err = stderr(&o);
    assert!(err.contains("closest: tabs vs spaces"), "{err}");
    assert!(err.contains("  4:"), "{err}");
    assert_eq!(fs::read_to_string(t.path().join("x.go")).unwrap(), GO);
}
