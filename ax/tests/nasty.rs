//! every command against a corpus of awkward files: nothing panics or hangs,
//! and files nobody asked to change stay byte-identical.

mod common;
use assert_cmd::Command;
use common::*;
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;
use std::time::Duration;

fn corpus() -> tempfile::TempDir {
    let t = tempfile::tempdir().unwrap();
    let r = t.path();
    git(r, &["init", "-q"]);
    fs::write(
        r.join("crlf.ts"),
        b"export const a = 1\r\nexport const b = 2\r\n",
    )
    .unwrap();
    fs::write(r.join("bom.js"), "\u{feff}const bom = 1\nconst two = 2\n").unwrap();
    fs::write(
        r.join("tabs.go"),
        b"package x\n\nfunc f() int {\n\treturn 1\n}\n",
    )
    .unwrap();
    fs::write(r.join("nofinal.py"), b"def f():\n    return 1").unwrap();
    fs::write(r.join("latin1.pas"), b"program Caf\xe9;\nbegin end.\n").unwrap();
    let bin: Vec<u8> = (0..4096u32).map(|i| (i * 7 % 256) as u8).collect();
    fs::write(r.join("blob.bin"), bin).unwrap();
    let mut big = vec![b'x'; 10 * 1024 * 1024];
    big[5_000_000..5_000_006].copy_from_slice(b"needle");
    fs::write(r.join("big.txt"), big).unwrap();
    fs::write(r.join("empty.txt"), b"").unwrap();
    #[cfg(unix)]
    {
        use std::os::unix::fs::symlink;
        symlink("loop_b", r.join("loop_a")).unwrap();
        symlink("loop_a", r.join("loop_b")).unwrap();
        symlink(".", r.join("self_dir")).unwrap();
    }
    t
}

/// checksums of every regular file (symlinks skipped).
fn snapshot(root: &Path) -> BTreeMap<String, u64> {
    let mut m = BTreeMap::new();
    for e in fs::read_dir(root).unwrap() {
        let e = e.unwrap();
        let ft = e.file_type().unwrap();
        if ft.is_file() {
            let b = fs::read(e.path()).unwrap();
            m.insert(
                e.file_name().to_string_lossy().into_owned(),
                ax::hash::fnv1a(&b),
            );
        }
    }
    m
}

fn run(dir: &Path, args: &[&str], input: &[u8]) -> std::process::Output {
    Command::cargo_bin("ax")
        .unwrap()
        .current_dir(dir)
        .args(args)
        .write_stdin(input)
        .timeout(Duration::from_secs(30))
        .output()
        .unwrap()
}

fn clean(o: &std::process::Output, what: &str) {
    let err = String::from_utf8_lossy(&o.stderr);
    assert!(
        matches!(o.status.code(), Some(0) | Some(1)),
        "{what}: exit {:?}, stderr {err}",
        o.status.code()
    );
    assert!(!err.contains("panicked"), "{what}: {err}");
}

#[test]
fn read_only_commands_survive_the_corpus() {
    let t = corpus();
    let before = snapshot(t.path());
    let files = [
        "crlf.ts",
        "bom.js",
        "tabs.go",
        "nofinal.py",
        "latin1.pas",
        "blob.bin",
        "big.txt",
        "empty.txt",
        "loop_a",
        "self_dir",
    ];
    let mut cmds: Vec<Vec<&str>> = vec![
        vec!["map"],
        vec!["find"],
        vec!["find", "--all"],
        vec!["grep", "needle"],
        vec!["grep", "--all", "-c", "x"],
        vec!["grep", "-C", "2", "return"],
        vec!["outline", "."],
        vec!["def", "f"],
        vec!["refs", "f", "--code-only"],
        vec!["diff"],
        vec!["read", "big.txt", "crlf.ts", "blob.bin", "empty.txt"],
    ];
    for f in files {
        cmds.push(vec!["read", f]);
        cmds.push(vec!["outline", f]);
    }
    for c in &cmds {
        let o = run(t.path(), c, b"");
        clean(&o, &c.join(" "));
        assert!(
            o.stdout.len() <= 25_000,
            "{}: {} bytes",
            c.join(" "),
            o.stdout.len()
        );
    }
    let big = stdout(&run(t.path(), &["read", "big.txt"], b""));
    assert!(big.contains("…[+"), "long line should be cut for display");
    assert_eq!(snapshot(t.path()), before);
}

#[test]
fn failed_and_dry_run_writes_leave_everything_untouched() {
    let t = corpus();
    let before = snapshot(t.path());
    let texts = [
        "crlf.ts",
        "bom.js",
        "tabs.go",
        "nofinal.py",
        "latin1.pas",
        "big.txt",
        "empty.txt",
    ];
    for f in texts {
        clean(&run(t.path(), &["edit", f], b"@@ replace 1:0000\nz\n"), f);
        clean(
            &run(
                t.path(),
                &["edit", f],
                b"@@ find\nnot-in-any-file\n@@ with\nz\n",
            ),
            f,
        );
        clean(
            &run(
                t.path(),
                &["edit", f, "--dry-run"],
                b"@@ find\nx\n@@ with\ny\n",
            ),
            f,
        );
        clean(&run(t.path(), &["write", f], b"clobber\n"), f);
    }
    clean(
        &run(t.path(), &["edit", "blob.bin"], b"@@ find\nx\n@@ with\ny\n"),
        "blob",
    );
    clean(
        &run(t.path(), &["edit", "loop_a"], b"@@ find\nx\n@@ with\ny\n"),
        "loop",
    );
    clean(
        &run(t.path(), &["write", "loop_a", "--force"], b"x\n"),
        "loop write",
    );
    let p = b"*** Begin Patch\n*** Update File: crlf.ts\n-nope\n+x\n*** Update File: bom.js\n-const bom = 1\n+const bom = 2\n*** End Patch\n";
    clean(&run(t.path(), &["patch"], p), "patch");
    clean(&run(t.path(), &["patch", "--dry-run"], p), "patch dry");
    assert_eq!(snapshot(t.path()), before);
}

#[test]
fn successful_edits_touch_only_their_target() {
    let t = corpus();
    let cases: &[(&str, &[u8], &[u8])] = &[
        (
            "crlf.ts",
            b"@@ find\nconst b = 2\n@@ with\nconst b = 3\n",
            b"export const a = 1\r\nexport const b = 3\r\n",
        ),
        (
            "bom.js",
            b"@@ find\nconst bom = 1\n@@ with\nconst bom = 9\n",
            "\u{feff}const bom = 9\nconst two = 2\n".as_bytes(),
        ),
        (
            "nofinal.py",
            b"@@ find\nreturn 1\n@@ with\nreturn 2\n",
            b"def f():\n    return 2",
        ),
        (
            "latin1.pas",
            "@@ find\nbegin end.\n@@ with\nbegin é end.\n".as_bytes(),
            b"program Caf\xe9;\nbegin \xe9 end.\n",
        ),
    ];
    for (f, ops, want) in cases {
        let before = snapshot(t.path());
        let o = run(t.path(), &["edit", f], ops);
        clean(&o, f);
        assert!(o.status.success(), "{f}: {}", stdout(&o));
        assert_eq!(&fs::read(t.path().join(f)).unwrap(), want, "{f}");
        let after = snapshot(t.path());
        for (k, v) in &before {
            if k != f {
                assert_eq!(after.get(k), Some(v), "{k} changed while editing {f}");
            }
        }
    }
    // a 10 MB one-line file: find/with in the middle of it
    let o = run(
        t.path(),
        &["edit", "big.txt"],
        b"@@ find\nneedle\n@@ with\nNEEDLE\n",
    );
    clean(&o, "big");
    assert!(o.status.success());
    let big = fs::read(t.path().join("big.txt")).unwrap();
    assert_eq!(big.len(), 10 * 1024 * 1024);
    assert_eq!(&big[5_000_000..5_000_006], b"NEEDLE");
}
