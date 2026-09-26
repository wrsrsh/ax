mod common;
use common::*;
use std::path::Path;
use std::process::Output;

fn edit(dir: &Path, path: &str, ops: &str) -> Output {
    ax_in(dir, &["edit", path], ops)
}

const SRC: &str =
    "export function add(a: number, b: number) {\n  return a + b\n}\n\nexport const x = 1\n";

#[test]
fn replace_with_anchor_from_read() {
    let t = fixture();
    write(t.path(), "src/math.ts", SRC);
    let a = anchor(t.path(), "src/math.ts", 2);
    let o = edit(
        t.path(),
        "src/math.ts",
        &format!("@@ replace {a}\n  return a + b + 0\n"),
    );
    assert!(o.status.success(), "{}", stdout(&o));
    let out = stdout(&o);
    assert!(out.starts_with("src/math.ts: +1 -1  (1 op)"), "{out}");
    assert!(out.contains("return a + b + 0"), "{out}");
    assert!(
        summary(&o).starts_with("wrote src/math.ts (5 lines, hash "),
        "{out}"
    );
    assert_eq!(
        std::fs::read_to_string(t.path().join("src/math.ts")).unwrap(),
        SRC.replace("a + b\n", "a + b + 0\n")
    );
}

#[test]
fn fresh_anchors_from_output_work_for_the_next_edit() {
    let t = fixture();
    write(t.path(), "src/math.ts", SRC);
    let a = anchor(t.path(), "src/math.ts", 5);
    let o = edit(
        t.path(),
        "src/math.ts",
        &format!("@@ insert after {a}\nexport const y = 2\n"),
    );
    let line = stdout(&o)
        .lines()
        .find(|l| l.contains("export const y = 2"))
        .unwrap()
        .trim()
        .to_string();
    let fresh = line.split("  ").next().unwrap();
    let o = edit(
        t.path(),
        "src/math.ts",
        &format!("@@ replace {fresh}\nexport const y = 3\n"),
    );
    assert!(o.status.success(), "{}", stdout(&o));
    assert!(
        std::fs::read_to_string(t.path().join("src/math.ts"))
            .unwrap()
            .ends_with("export const y = 3\n")
    );
}

#[test]
fn stale_anchor_writes_nothing_and_shows_current_lines() {
    let t = fixture();
    write(t.path(), "src/math.ts", SRC);
    let a = anchor(t.path(), "src/math.ts", 2);
    // someone else changes line 2
    write(t.path(), "src/math.ts", &SRC.replace("a + b", "b + a"));
    let before = std::fs::read(t.path().join("src/math.ts")).unwrap();
    let o = edit(
        t.path(),
        "src/math.ts",
        &format!("@@ replace {a}\n  return 0\n"),
    );
    assert_eq!(o.status.code(), Some(1));
    let out = stdout(&o);
    assert!(out.contains("stale anchor"), "{out}");
    assert!(out.contains("return b + a"), "shows current content: {out}");
    assert_eq!(summary(&o), "nothing written (stale).");
    assert_eq!(std::fs::read(t.path().join("src/math.ts")).unwrap(), before);
}

#[test]
fn moved_line_is_relocated() {
    let t = fixture();
    write(t.path(), "src/math.ts", SRC);
    let a = anchor(t.path(), "src/math.ts", 5);
    write(
        t.path(),
        "src/math.ts",
        &format!("// header\n// more\n{SRC}"),
    );
    let o = edit(
        t.path(),
        "src/math.ts",
        &format!("@@ replace {a}\nexport const x = 2\n"),
    );
    assert!(o.status.success(), "{}", stdout(&o));
    assert!(stdout(&o).contains("1 relocated"));
    let o = ax_in(
        t.path(),
        &["--json", "edit", "src/math.ts"],
        "@@ find\nexport const x = 2\n@@ with\nexport const x = 3\n",
    );
    let v: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    assert_eq!(v["data"]["outcome"], "ok");
    assert!(
        std::fs::read_to_string(t.path().join("src/math.ts"))
            .unwrap()
            .contains("export const x = 3")
    );
}

#[test]
fn find_with_errors_are_explained() {
    let t = fixture();
    write(t.path(), "src/math.ts", SRC);
    let o = edit(
        t.path(),
        "src/math.ts",
        "@@ find\nexport\n@@ with\nexport default\n",
    );
    assert_eq!(o.status.code(), Some(1));
    assert!(stdout(&o).contains("occurs 2 times"), "{}", stdout(&o));
    let o = edit(t.path(), "src/math.ts", "@@ find\nnope\n@@ with\nx\n");
    assert!(stdout(&o).contains("not found"));
    assert_eq!(summary(&o), "nothing written (no-match).");
}

#[test]
fn refuses_outside_repo_missing_and_binary() {
    let t = fixture();
    let outside = tempfile::tempdir().unwrap();
    std::fs::write(outside.path().join("f.ts"), "x\n").unwrap();
    let rel = format!("{}/f.ts", outside.path().display());
    let o = edit(t.path(), &rel, "@@ find\nx\n@@ with\ny\n");
    assert_eq!(o.status.code(), Some(1));
    assert!(stderr(&o).contains("outside the repo"));
    assert_eq!(
        std::fs::read_to_string(outside.path().join("f.ts")).unwrap(),
        "x\n"
    );

    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(outside.path().join("f.ts"), t.path().join("link.ts")).unwrap();
        let o = edit(t.path(), "link.ts", "@@ find\nx\n@@ with\ny\n");
        assert_eq!(o.status.code(), Some(1));
        assert_eq!(
            std::fs::read_to_string(outside.path().join("f.ts")).unwrap(),
            "x\n"
        );
    }

    let o = edit(t.path(), "nope.ts", "@@ find\nx\n@@ with\ny\n");
    assert!(stderr(&o).contains("ax write"));

    std::fs::write(t.path().join("b.bin"), b"a\0b").unwrap();
    let o = edit(t.path(), "b.bin", "@@ find\na\n@@ with\nb\n");
    assert_eq!(o.status.code(), Some(1));
}

#[cfg(unix)]
#[test]
fn symlink_inside_repo_is_written_through() {
    let t = fixture();
    write(t.path(), "src/real.ts", "a\n");
    std::os::unix::fs::symlink("real.ts", t.path().join("src/alias.ts")).unwrap();
    let o = edit(t.path(), "src/alias.ts", "@@ find\na\n@@ with\nb\n");
    assert!(o.status.success(), "{}", stderr(&o));
    assert!(t.path().join("src/alias.ts").is_symlink());
    assert_eq!(
        std::fs::read_to_string(t.path().join("src/real.ts")).unwrap(),
        "b\n"
    );
}

#[test]
fn crlf_file_stays_crlf() {
    let t = fixture();
    std::fs::write(t.path().join("w.py"), b"def f():\r\n    return 1\r\n").unwrap();
    let a = anchor(t.path(), "w.py", 2);
    let o = edit(
        t.path(),
        "w.py",
        &format!("@@ replace {a}\n    return 2\n    # done\n"),
    );
    assert!(o.status.success());
    assert_eq!(
        std::fs::read(t.path().join("w.py")).unwrap(),
        b"def f():\r\n    return 2\r\n    # done\r\n"
    );
}
