mod common;
use common::*;

#[test]
fn read_many_files_stays_under_the_byte_budget() {
    let t = fixture();
    let body: String = (0..400)
        .map(|i| format!("const value_{i:04} = {i} // padding padding\n"))
        .collect();
    for f in ["src/a.ts", "src/b.ts", "src/c.ts"] {
        write(t.path(), f, &body);
    }
    let o = ax_env(
        t.path(),
        &[("AX_MAX_BYTES", "6000")],
        &["read", "--full", "src/a.ts", "src/b.ts", "src/c.ts"],
    );
    let out = stdout(&o);
    assert!(out.len() <= 6000, "{} bytes", out.len());
    assert!(out.contains("continue with `ax read src/a.ts:"), "{out}");
    assert!(
        summary(&o).contains("hit the per-call output budget"),
        "{}",
        summary(&o)
    );
    let o = ax_env(
        t.path(),
        &[("AX_MAX_BYTES", "6000"), ("AX_NO_CAPS", "1")],
        &["read", "--full", "src/a.ts", "src/b.ts", "src/c.ts"],
    );
    assert!(stdout(&o).len() > 30_000);
}

#[test]
fn any_command_is_cut_at_the_budget_and_says_so() {
    let t = fixture();
    let body: String = (0..300)
        .map(|i| format!("export function f{i}() {{ return {i} }}\n"))
        .collect();
    write(t.path(), "src/many.ts", &body);
    let o = ax_env(
        t.path(),
        &[("AX_MAX_BYTES", "2000")],
        &["outline", "src/many.ts"],
    );
    let out = stdout(&o);
    assert!(out.len() <= 2000, "{} bytes", out.len());
    assert!(
        summary(&o).contains("output cut at 2000 bytes"),
        "{}",
        summary(&o)
    );
    let o = ax_env(
        t.path(),
        &[("AX_MAX_BYTES", "1500"), ("AX_MAX_HITS", "500")],
        &["grep", "return"],
    );
    assert!(stdout(&o).len() <= 1500);
    assert!(summary(&o).contains("more lines not shown"));
}

#[test]
fn grep_says_how_many_binary_files_it_skipped() {
    let t = fixture();
    std::fs::write(t.path().join("blob.bin"), b"needle\0\x01").unwrap();
    std::fs::write(t.path().join("blob2.bin"), b"\0needle").unwrap();
    let o = ax(t.path(), &["grep", "zzz-none"]);
    assert!(
        summary(&o).contains("skipped 2 binary files"),
        "{}",
        summary(&o)
    );
    let o = ax(t.path(), &["grep", "export"]);
    assert!(
        summary(&o).contains("skipped 2 binary files"),
        "{}",
        summary(&o)
    );
}
