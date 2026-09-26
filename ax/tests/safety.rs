mod common;
use assert_cmd::Command;
use common::*;
use std::fs;
use std::path::Path;

fn run(dir: &Path, args: &[&str], input: &[u8]) -> std::process::Output {
    Command::cargo_bin("ax")
        .unwrap()
        .current_dir(dir)
        .args(args)
        .write_stdin(input)
        .output()
        .unwrap()
}

#[test]
fn write_wont_clobber_without_if_or_force() {
    let t = fixture();
    let o = run(t.path(), &["write", "src/router.ts"], b"oops\n");
    assert_eq!(o.status.code(), Some(1));
    assert!(stdout(&o).contains("already exists"), "{}", stdout(&o));
    assert_eq!(
        fs::read_to_string(t.path().join("src/router.ts")).unwrap(),
        "export const r = 1\n"
    );
    let o = run(
        t.path(),
        &["write", "src/router.ts", "--force"],
        b"export const r = 2\n",
    );
    assert!(o.status.success());
    assert_eq!(
        fs::read_to_string(t.path().join("src/router.ts")).unwrap(),
        "export const r = 2\n"
    );
}

#[test]
fn pasted_anchors_are_refused_everywhere() {
    let t = fixture();
    let before = fs::read(t.path().join("src/router.ts")).unwrap();
    let o = run(
        t.path(),
        &["edit", "src/router.ts"],
        b"@@ find\nexport const r = 1\n@@ with\n1:abcd  export const r = 2\n",
    );
    assert_eq!(o.status.code(), Some(1));
    assert!(
        stdout(&o).contains("without the `12:a3f1  ` prefix"),
        "{}",
        stdout(&o)
    );
    assert_eq!(fs::read(t.path().join("src/router.ts")).unwrap(), before);

    let o = run(
        t.path(),
        &["write", "src/n.ts"],
        b"1:abcd  const a = 1\n2:ef01  const b = 2\n",
    );
    assert_eq!(o.status.code(), Some(1));
    assert!(!t.path().join("src/n.ts").exists());

    let p = b"*** Begin Patch\n*** Add File: src/m.ts\n+3:0a0b  const c = 3\n*** End Patch\n";
    let o = run(t.path(), &["patch"], p);
    assert_eq!(o.status.code(), Some(1));
    assert!(!t.path().join("src/m.ts").exists());
}

#[test]
fn dry_run_writes_nothing() {
    let t = fixture();
    let before = fs::read(t.path().join("src/router.ts")).unwrap();
    let o = run(
        t.path(),
        &["edit", "src/router.ts", "--dry-run"],
        b"@@ find\nexport const r = 1\n@@ with\nexport const r = 3\n",
    );
    assert!(o.status.success());
    assert!(stdout(&o).contains("export const r = 3"));
    assert!(
        summary(&o).starts_with("dry run: nothing written."),
        "{}",
        summary(&o)
    );
    assert_eq!(fs::read(t.path().join("src/router.ts")).unwrap(), before);

    let o = run(t.path(), &["write", "src/new.ts", "--dry-run"], b"x\n");
    assert!(summary(&o).starts_with("dry run"), "{}", summary(&o));
    assert!(!t.path().join("src/new.ts").exists());

    let p = b"*** Begin Patch\n*** Delete File: src/router.ts\n*** End Patch\n";
    let o = run(t.path(), &["patch", "--dry-run"], p);
    assert!(o.status.success());
    assert!(summary(&o).starts_with("dry run"));
    assert!(t.path().join("src/router.ts").exists());
}

#[test]
fn whitespace_warnings_dont_change_content() {
    let t = fixture();
    let o = run(
        t.path(),
        &["write", "src/w.ts"],
        b"const a = 1  \nconst b = 2",
    );
    assert!(o.status.success());
    let s = summary(&o);
    assert!(
        s.contains("1 new line(s) end in whitespace") && s.contains("no newline at end of file"),
        "{s}"
    );
    assert_eq!(
        fs::read(t.path().join("src/w.ts")).unwrap(),
        b"const a = 1  \nconst b = 2"
    );

    let o = run(
        t.path(),
        &["edit", "src/router.ts"],
        b"@@ find\nexport const r = 1\n@@ with\nexport const r = 1 \n",
    );
    assert!(summary(&o).contains("end in whitespace"), "{}", summary(&o));
}

#[test]
fn bytes_are_written_verbatim() {
    let t = fixture();
    // escape sequences typed as text stay text, cjk punctuation stays full-width
    let body = "const s = \"a\\x00b\\n\\t\"\nconst jp = \"こんにちは、世界。「テスト」\"\n";
    let o = run(t.path(), &["write", "src/lit.ts"], body.as_bytes());
    assert!(o.status.success(), "{}", stdout(&o));
    assert_eq!(
        fs::read(t.path().join("src/lit.ts")).unwrap(),
        body.as_bytes()
    );
    let o = run(
        t.path(),
        &["edit", "src/lit.ts"],
        "@@ find\n\\x00b\n@@ with\n\\x01b\n".as_bytes(),
    );
    assert!(o.status.success(), "{}", stdout(&o));
    assert_eq!(
        fs::read_to_string(t.path().join("src/lit.ts")).unwrap(),
        body.replace("\\x00b", "\\x01b")
    );
}
