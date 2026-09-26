mod common;
use assert_cmd::Command;
use common::*;
use std::fs;
use std::path::Path;

fn with_stdin(dir: &Path, args: &[&str], input: &str) -> std::process::Output {
    Command::cargo_bin("ax")
        .unwrap()
        .current_dir(dir)
        .args(args)
        .write_stdin(input)
        .output()
        .unwrap()
}

fn file_hash(dir: &Path, path: &str) -> String {
    let o = ax(dir, &["--json", "read", path]);
    let v: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    v["data"]["files"][0]["hash"].as_str().unwrap().to_string()
}

#[test]
fn write_creates_replaces_and_checks_hash() {
    let t = fixture();
    let o = with_stdin(t.path(), &["write", "src/new/deep.ts"], "a\nb\n");
    assert!(o.status.success());
    assert!(summary(&o).starts_with("wrote src/new/deep.ts: created, hash "));
    assert_eq!(
        fs::read_to_string(t.path().join("src/new/deep.ts")).unwrap(),
        "a\nb\n"
    );

    let h = file_hash(t.path(), "src/new/deep.ts");
    let o = with_stdin(t.path(), &["write", "src/new/deep.ts", "--if", &h], "c\n");
    assert!(o.status.success(), "{}", stdout(&o));
    assert!(
        summary(&o).contains("replaced (2 lines → 1 line)"),
        "{}",
        summary(&o)
    );

    // old hash is stale now
    let o = with_stdin(t.path(), &["write", "src/new/deep.ts", "--if", &h], "d\n");
    assert_eq!(o.status.code(), Some(1));
    assert!(stdout(&o).contains("changed since you read it"));
    assert_eq!(
        fs::read_to_string(t.path().join("src/new/deep.ts")).unwrap(),
        "c\n"
    );

    let o = with_stdin(t.path(), &["write", "../escape.ts"], "x\n");
    assert_eq!(o.status.code(), Some(1));
    assert!(!t.path().parent().unwrap().join("escape.ts").exists());
}

#[test]
fn codex_patch_multi_file() {
    let t = fixture();
    write(
        t.path(),
        "src/a.ts",
        "function f() {\n  return 1\n}\n\nfunction g() {\n  return 1\n}\n",
    );
    let p = "*** Begin Patch
*** Update File: src/a.ts
@@ function g
-  return 1
+  return 2
*** Add File: src/b.ts
+export const b = 1
*** Delete File: src/router.ts
*** Update File: src/main.rs
*** Move to: src/bin.rs
@@
-fn main() {}
+fn main() { println!(\"hi\") }
*** End Patch
";
    let o = with_stdin(t.path(), &["patch"], p);
    assert!(
        o.status.success(),
        "{}\n{}",
        stdout(&o),
        String::from_utf8_lossy(&o.stderr)
    );
    let out = stdout(&o);
    assert!(out.contains("M src/a.ts  +1 -1"), "{out}");
    assert!(out.contains("A src/b.ts  +1"), "{out}");
    assert!(out.contains("D src/router.ts  -1"), "{out}");
    assert!(out.contains("R src/main.rs -> src/bin.rs  +1 -1"), "{out}");
    assert_eq!(summary(&o), "patched 4 files (+3 -3).");
    let a = fs::read_to_string(t.path().join("src/a.ts")).unwrap();
    assert!(a.contains("function f() {\n  return 1") && a.contains("function g() {\n  return 2"));
    assert!(!t.path().join("src/router.ts").exists());
    assert!(!t.path().join("src/main.rs").exists());
    assert!(
        fs::read_to_string(t.path().join("src/bin.rs"))
            .unwrap()
            .contains("println")
    );
}

#[test]
fn unified_patch_with_offset() {
    let t = fixture();
    write(t.path(), "src/a.ts", "x\n// added later\none\ntwo\nthree\n");
    // hunk says line 2 but the text is now at line 3
    let p = "--- a/src/a.ts\n+++ b/src/a.ts\n@@ -2,3 +2,3 @@\n one\n-two\n+TWO\n three\n";
    let o = with_stdin(t.path(), &["patch"], p);
    assert!(o.status.success(), "{}", String::from_utf8_lossy(&o.stderr));
    assert_eq!(
        fs::read_to_string(t.path().join("src/a.ts")).unwrap(),
        "x\n// added later\none\nTWO\nthree\n"
    );
}

#[test]
fn failing_hunk_writes_nothing_anywhere() {
    let t = fixture();
    let before_router = fs::read(t.path().join("src/router.ts")).unwrap();
    let p = "*** Begin Patch
*** Update File: src/router.ts
-export const r = 1
+export const r = 99
*** Add File: src/c.ts
+c
*** Update File: src/main.rs
-this line is not in the file
+nope
*** End Patch
";
    let o = with_stdin(t.path(), &["patch"], p);
    assert_eq!(o.status.code(), Some(1));
    let err = String::from_utf8_lossy(&o.stderr);
    assert!(
        err.contains("src/main.rs: hunk 1 of 1 doesn't match"),
        "{err}"
    );
    assert!(err.contains("current lines there:"), "{err}");
    assert_eq!(
        fs::read(t.path().join("src/router.ts")).unwrap(),
        before_router
    );
    assert!(!t.path().join("src/c.ts").exists());
}

#[test]
fn patch_refuses_bad_input_and_escapes() {
    let t = fixture();
    assert_eq!(
        with_stdin(t.path(), &["patch"], "hello\n").status.code(),
        Some(1)
    );
    let p = "*** Begin Patch\n*** Add File: ../x.ts\n+x\n*** End Patch\n";
    assert_eq!(with_stdin(t.path(), &["patch"], p).status.code(), Some(1));
    let p = "*** Begin Patch\n*** Add File: src/router.ts\n+x\n*** End Patch\n";
    let o = with_stdin(t.path(), &["patch"], p);
    assert!(String::from_utf8_lossy(&o.stderr).contains("already exists"));
}

#[test]
fn no_final_newline_is_respected() {
    let t = fixture();
    fs::write(t.path().join("n.txt"), "a\nb").unwrap();
    let p = "--- a/n.txt\n+++ b/n.txt\n@@ -1,2 +1,2 @@\n a\n-b\n\\ No newline at end of file\n+B\n\\ No newline at end of file\n";
    assert!(with_stdin(t.path(), &["patch"], p).status.success());
    assert_eq!(fs::read(t.path().join("n.txt")).unwrap(), b"a\nB");
    let p = "--- a/n.txt\n+++ b/n.txt\n@@ -1,2 +1,2 @@\n a\n-B\n\\ No newline at end of file\n+B\n";
    assert!(with_stdin(t.path(), &["patch"], p).status.success());
    assert_eq!(fs::read(t.path().join("n.txt")).unwrap(), b"a\nB\n");
}
