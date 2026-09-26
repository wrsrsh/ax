mod common;
use common::*;

fn long_ts(n: usize) -> String {
    let mut s = String::from("export class Big {\n");
    for i in 0..n {
        s.push_str(&format!("  m{i}() {{ return {i} }}\n"));
    }
    s.push_str("}\n");
    s
}

#[test]
fn read_short_file_whole_with_anchors() {
    let t = fixture();
    let o = ax(t.path(), &["read", "src/router.ts"]);
    assert!(o.status.success());
    let b = body(&o);
    assert!(b[0].starts_with("src/router.ts  (1 line, hash "), "{b:?}");
    assert_eq!(b.len(), 2);
    let (anchor, code) = b[1].split_once("  ").unwrap();
    assert!(anchor.starts_with("1:") && anchor.len() == 6, "{anchor}");
    assert_eq!(code, "export const r = 1");
    assert_eq!(summary(&o), "read 1 file (1 line shown).");
}

#[test]
fn read_long_file_gets_outline_and_window() {
    let t = fixture();
    write(t.path(), "src/big.ts", &long_ts(400));
    let o = ax_env(
        t.path(),
        &[("AX_READ_WINDOW", "50")],
        &["read", "src/big.ts"],
    );
    let out = stdout(&o);
    assert!(
        out.contains("outline (61 symbols):") || out.contains("outline ("),
        "{out}"
    );
    assert!(out.contains("  1-402  class Big"), "{out}");
    assert!(out.contains("\n50:"), "{out}");
    assert!(!out.contains("\n51:"), "{out}");
    assert!(out.contains("next: `ax read src/big.ts:51-100`"), "{out}");
    // --full prints everything, no outline
    let full = stdout(&ax(t.path(), &["read", "--full", "src/big.ts"]));
    assert!(full.contains("\n402:") && !full.contains("outline ("));
}

#[test]
fn read_ranges() {
    let t = fixture();
    write(t.path(), "src/big.ts", &long_ts(400));
    let b = body(&ax(t.path(), &["read", "src/big.ts:10-12"]));
    assert_eq!(b.len(), 4);
    assert!(b[1].starts_with("10:") && b[3].starts_with("12:"));
    // one window from a line
    let o = ax_env(
        t.path(),
        &[("AX_READ_WINDOW", "5")],
        &["read", "src/big.ts:100"],
    );
    let b = body(&o);
    assert!(
        b[1].starts_with("100:") && b[5].starts_with("104:"),
        "{b:?}"
    );
    assert!(b[6].contains("next: `ax read src/big.ts:105-109`"), "{b:?}");
    // past the end is not a crash
    let o = ax(t.path(), &["read", "src/big.ts:900-910"]);
    assert!(o.status.success());
    assert!(stdout(&o).contains("past the end"));
    // bad range is an error
    assert_eq!(
        ax(t.path(), &["read", "src/big.ts:9-3"]).status.code(),
        Some(1)
    );
}

#[test]
fn read_many_files_and_a_missing_one() {
    let t = fixture();
    let o = ax(
        t.path(),
        &["read", "src/router.ts", "nope.ts", "src/main.rs"],
    );
    assert_eq!(o.status.code(), Some(1));
    let out = stdout(&o);
    assert!(out.contains("src/router.ts  (") && out.contains("src/main.rs  ("));
    assert!(out.contains("nope.ts: no such file"));
    assert!(summary(&o).contains("failed: nope.ts"));
}

#[test]
fn read_binary_crlf_and_non_utf8() {
    let t = fixture();
    std::fs::write(t.path().join("blob.bin"), b"\x00\x01\x02").unwrap();
    std::fs::write(t.path().join("crlf.py"), b"a = 1\r\nb = 2\r\n").unwrap();
    std::fs::write(t.path().join("latin1.txt"), b"caf\xe9\n").unwrap();
    let out = stdout(&ax(
        t.path(),
        &["read", "blob.bin", "crlf.py", "latin1.txt"],
    ));
    assert!(
        out.contains("blob.bin  (binary, 3 bytes, not shown)"),
        "{out}"
    );
    assert!(out.contains("  a = 1\n"), "no stray \\r: {out:?}");
    assert!(out.contains("café") && out.contains("windows-1252"), "{out}");
}

#[test]
fn read_sym() {
    let t = fixture();
    write(t.path(), "src/big.ts", &long_ts(10));
    let b = body(&ax(t.path(), &["read", "src/big.ts", "--sym", "m3"]));
    assert_eq!(b[1], "@ Big.m3  (method 5-5)");
    assert!(b[2].starts_with("5:") && b[2].ends_with("m3() { return 3 }"));
    // repo-wide
    let b = body(&ax(t.path(), &["read", "--sym", "Big.m3"]));
    assert_eq!(b[1], "@ Big.m3  (method 5-5)");
    let o = ax(t.path(), &["read", "--sym", "nothing"]);
    assert!(summary(&o).starts_with("no symbol nothing found"));
}

#[test]
fn read_hash_matches_file_hash_in_json() {
    let t = fixture();
    let o = ax(t.path(), &["--json", "read", "src/router.ts"]);
    let v: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    let f = &v["data"]["files"][0];
    assert_eq!(f["lines"], 1);
    assert_eq!(f["hash"].as_str().unwrap().len(), 8);
    assert_eq!(f["rows"][0]["text"], "export const r = 1");
}

#[test]
fn diff_clean_dirty_untracked_and_caps() {
    let t = fixture();
    let o = ax(t.path(), &["diff"]);
    assert!(o.status.success());
    assert_eq!(summary(&o), "no changes (clean working tree on main).");

    write(
        t.path(),
        "src/router.ts",
        "export const r = 2\nexport const s = 3\n",
    );
    write(t.path(), "src/new.ts", "a\nb\nc\n");
    git(t.path(), &["rm", "-q", "README.md"]);
    let o = ax(t.path(), &["diff"]);
    let out = stdout(&o);
    assert!(
        out.starts_with("branch main · 2 files changed, 1 untracked · +5 -2"),
        "{out}"
    );
    assert!(out.contains(" M src/router.ts  +2 -1"), "{out}");
    assert!(out.contains(" D README.md"), "{out}");
    assert!(out.contains("?? src/new.ts     new, 3 lines"), "{out}");
    assert!(out.contains("+export const s = 3"), "{out}");
    assert!(
        summary(&o).starts_with("3 files changed, +5 -2."),
        "{}",
        summary(&o)
    );

    let o = ax_env(t.path(), &[("AX_READ_WINDOW", "3")], &["diff"]);
    assert!(summary(&o).contains("showed 3 of"), "{}", summary(&o));
    let o = ax_env(t.path(), &[("AX_READ_WINDOW", "3")], &["diff", "--full"]);
    assert!(!summary(&o).contains("showed"));

    // path filter, relative to cwd
    let o = ax(&t.path().join("src"), &["diff", "router.ts"]);
    let out = stdout(&o);
    assert!(
        out.contains("src/router.ts") && !out.contains("README.md"),
        "{out}"
    );
}

#[test]
fn diff_outside_git_is_an_error() {
    let t = tempfile::tempdir().unwrap();
    assert_eq!(ax(t.path(), &["diff"]).status.code(), Some(1));
}
