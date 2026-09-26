mod common;
use common::*;
use std::collections::BTreeSet;
use std::path::Path;

fn grep_fixture() -> tempfile::TempDir {
    let t = tempfile::tempdir().unwrap();
    let r = t.path();
    git(r, &["init", "-q"]);
    write(r, ".gitignore", "dist/\n");
    write(
        r,
        "src/app.ts",
        "\
export class App {
  foo() {
    return fooBar + FOO
  }
}
const a = 'a.b' // foo
function helper() {
  return foo()
}
",
    );
    write(
        r,
        "src/lib.rs",
        "fn foo() {}\nfn main() { foo(); let x = \"fooo\"; }\n",
    );
    write(r, "src/crlf.py", "def foo():\r\n    return 'Foo'\r\n");
    write(r, "src/unicode.txt", "héllo foo wörld\nnaïve FOO\n");
    write(r, "README.md", "use foo like this:\n\n    foo()\n");
    write(r, "dist/bundle.js", "foo foo foo\n");
    write(r, ".hidden.ts", "foo\n");
    std::fs::write(r.join("src/blob.bin"), b"foo\0\x01\x02foo\n").unwrap();
    t
}

/// (path, line) pairs from `rg -n --no-heading --with-filename`
fn rg_pairs(dir: &Path, args: &[&str]) -> BTreeSet<(String, usize)> {
    let o = std::process::Command::new("rg")
        .args(["-n", "--no-heading", "--with-filename", "--color", "never"])
        .args(args)
        .current_dir(dir)
        .output()
        .unwrap();
    String::from_utf8_lossy(&o.stdout)
        .lines()
        .filter_map(|l| {
            let mut it = l.splitn(3, ':');
            let p = it.next()?.trim_start_matches("./").to_string();
            let n = it.next()?.parse().ok()?;
            Some((p, n))
        })
        .collect()
}

fn ax_pairs(dir: &Path, args: &[&str]) -> BTreeSet<(String, usize)> {
    let mut a = vec!["--json", "grep"];
    a.extend_from_slice(args);
    let o = ax_env(dir, &[("AX_NO_CAPS", "1")], &a);
    assert!(o.status.success(), "{}", String::from_utf8_lossy(&o.stderr));
    let v: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    v["data"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|h| h["context"].as_bool() != Some(true))
        .map(|h| {
            (
                h["path"].as_str().unwrap().to_string(),
                h["line"].as_u64().unwrap() as usize,
            )
        })
        .collect()
}

#[test]
fn parity_with_rg_across_flags() {
    if !have_rg() {
        eprintln!("rg not installed, skipping parity check");
        return;
    }
    let t = grep_fixture();
    let cases: &[&[&str]] = &[
        &["foo"],
        &["fo+"],
        &["-F", "a.b"],
        &["a.b"],
        &["-w", "foo"],
        &["-i", "foo"],
        &["-S", "Foo"],
        &["-S", "foo"],
        &["-t", "ts", "foo"],
        &["-t", "rust", "-t", "py", "foo"],
        &["-g", "*.rs", "foo"],
        &["-g", "!*.md", "foo"],
        &["-C", "1", "helper"],
        &["foo$"],
        &["^\\s+return"],
        &["wörld"],
        &["nothing-matches-this"],
    ];
    for args in cases {
        let ours = ax_pairs(t.path(), args);
        let theirs = rg_pairs(t.path(), args);
        assert_eq!(ours, theirs, "args {args:?}");
    }
    // paths: ax takes --in or trailing paths; rg takes trailing paths
    assert_eq!(
        ax_pairs(t.path(), &["foo", "--in", "src"]),
        rg_pairs(t.path(), &["foo", "src"])
    );
    assert_eq!(
        ax_pairs(t.path(), &["foo", "src/app.ts", "README.md"]),
        rg_pairs(t.path(), &["foo", "src/app.ts", "README.md"])
    );
    // --all = -uu
    assert_eq!(
        ax_pairs(t.path(), &["--all", "foo"]),
        rg_pairs(t.path(), &["-uu", "foo"])
    );
}

#[test]
fn files_and_counts_match_rg() {
    if !have_rg() {
        return;
    }
    let t = grep_fixture();
    let mut ours = body(&ax(t.path(), &["grep", "-l", "foo"]));
    ours.sort();
    let o = std::process::Command::new("rg")
        .args(["-l", "foo"])
        .current_dir(t.path())
        .output()
        .unwrap();
    let mut theirs: Vec<String> = String::from_utf8(o.stdout)
        .unwrap()
        .lines()
        .map(str::to_string)
        .collect();
    theirs.sort();
    assert_eq!(ours, theirs);

    let mut ours = body(&ax(t.path(), &["grep", "-c", "foo"]));
    ours.sort();
    let o = std::process::Command::new("rg")
        .args(["-c", "foo"])
        .current_dir(t.path())
        .output()
        .unwrap();
    let mut theirs: Vec<String> = String::from_utf8(o.stdout)
        .unwrap()
        .lines()
        .map(|l| l.replacen(':', ": ", 1))
        .collect();
    theirs.sort();
    assert_eq!(ours, theirs);
}

#[test]
fn output_is_grouped_anchored_and_tagged() {
    let t = grep_fixture();
    let o = ax(t.path(), &["grep", "foo", "src/app.ts"]);
    let b = body(&o);
    assert_eq!(b[0], "src/app.ts");
    assert_eq!(b[1], "  @ App.foo  (method 2-4)");
    assert!(
        b[2].starts_with("  2:") && b[2].ends_with("  foo() {"),
        "{b:?}"
    );
    assert!(b[3].starts_with("  3:"), "{b:?}");
    assert_eq!(b[4], "  @ (top level)");
    assert!(b[5].starts_with("  6:"), "{b:?}");
    assert_eq!(b[6], "  @ helper  (function 7-9)");
    assert_eq!(summary(&o), "4 hits for /foo/ in 1 file.");
}

#[test]
fn context_lines_are_marked() {
    let t = grep_fixture();
    let b = body(&ax(t.path(), &["grep", "-C", "1", "helper"]));
    assert!(b.iter().any(|l| l.starts_with("> 7:")), "{b:?}");
    assert!(b.iter().any(|l| l.starts_with("  6:")), "{b:?}");
    assert!(b.iter().any(|l| l.starts_with("  8:")), "{b:?}");
}

#[test]
fn caps_empty_and_errors() {
    let t = grep_fixture();
    let o = ax_env(t.path(), &[("AX_MAX_HITS", "3")], &["grep", "foo"]);
    let hits = body(&o)
        .iter()
        .filter(|l| l.trim_start().starts_with(|c: char| c.is_ascii_digit()))
        .count();
    assert_eq!(hits, 3);
    assert!(summary(&o).contains("showing first 3. narrow with"));

    let o = ax(t.path(), &["grep", "zzz-nope"]);
    assert!(o.status.success());
    assert!(
        summary(&o).starts_with("no hits for /zzz-nope/ in "),
        "{}",
        summary(&o)
    );
    assert!(summary(&o).contains("--all"));

    assert_eq!(ax(t.path(), &["grep", "("]).status.code(), Some(1));
    assert_eq!(
        ax(t.path(), &["grep", "-t", "nolang", "x"]).status.code(),
        Some(1)
    );
}

#[test]
fn anchors_and_symbols_can_be_switched_off() {
    let t = grep_fixture();
    let o = ax_env(
        t.path(),
        &[("AX_NO_ANCHORS", "1"), ("AX_NO_SYMBOLS", "1")],
        &["grep", "helper"],
    );
    assert_eq!(body(&o), vec!["src/app.ts", "  7  function helper() {"]);
}
