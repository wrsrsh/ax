mod common;
use assert_cmd::Command;
use common::*;
use std::fs;
use std::path::Path;

fn with_stdin(
    dir: &Path,
    env: &[(&str, &str)],
    args: &[&str],
    input: &str,
) -> std::process::Output {
    let mut c = Command::cargo_bin("ax").unwrap();
    c.current_dir(dir).args(args).write_stdin(input);
    for (k, v) in env {
        c.env(k, v);
    }
    c.output().unwrap()
}

#[test]
fn parse_guard_on_edit_write_and_patch() {
    let t = fixture();
    let before = fs::read(t.path().join("src/router.ts")).unwrap();
    let bad_edit = "@@ find\nexport const r = 1\n@@ with\nexport const r = (\n";
    let o = with_stdin(t.path(), &[], &["edit", "src/router.ts"], bad_edit);
    assert_eq!(o.status.code(), Some(1));
    assert!(stdout(&o).contains("doesn't parse"), "{}", stdout(&o));
    assert_eq!(summary(&o), "nothing written (parse-rejected).");
    assert_eq!(fs::read(t.path().join("src/router.ts")).unwrap(), before);

    // switched off, it goes through
    let o = with_stdin(
        t.path(),
        &[("AX_NO_PARSE_CHECK", "1")],
        &["edit", "src/router.ts"],
        bad_edit,
    );
    assert!(o.status.success());

    let o = with_stdin(t.path(), &[], &["write", "src/x.py"], "def f(:\n");
    assert_eq!(o.status.code(), Some(1));
    assert!(!t.path().join("src/x.py").exists());

    let p = "*** Begin Patch\n*** Update File: src/main.rs\n-fn main() {}\n+fn main() {\n*** End Patch\n";
    let o = with_stdin(t.path(), &[], &["patch"], p);
    assert_eq!(o.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&o.stderr).contains("doesn't parse"));
    assert_eq!(
        fs::read_to_string(t.path().join("src/main.rs")).unwrap(),
        "fn main() {}\n"
    );

    // an already-broken file can still be edited
    fs::write(t.path().join("src/broken.ts"), "const a = (\nconst b = 1\n").unwrap();
    let o = with_stdin(
        t.path(),
        &[],
        &["edit", "src/broken.ts"],
        "@@ find\nconst b = 1\n@@ with\nconst b = 2\n",
    );
    assert!(o.status.success(), "{}", stdout(&o));
}

#[test]
fn ax_log_writes_one_json_line_per_call() {
    let t = fixture();
    let log = t.path().join("ax.log");
    let env = [("AX_LOG", log.to_str().unwrap()), ("AX_MAX_HITS", "7")];
    with_stdin(t.path(), &env, &["grep", "export"], "");
    with_stdin(
        t.path(),
        &env,
        &["edit", "src/router.ts"],
        "@@ replace 1:0000\nx\n",
    );
    with_stdin(t.path(), &env, &["read", "nope.ts"], "");
    let lines: Vec<serde_json::Value> = fs::read_to_string(&log)
        .unwrap()
        .lines()
        .map(|l| serde_json::from_str(l).unwrap())
        .collect();
    assert_eq!(lines.len(), 3);
    assert_eq!(lines[0]["cmd"], "grep");
    assert_eq!(lines[0]["exit"], 0);
    assert!(lines[0]["out_bytes"].as_u64().unwrap() > 0);
    assert!(lines[0]["ms"].as_f64().unwrap() >= 0.0);
    assert_eq!(lines[0]["knobs"][0], "AX_MAX_HITS=7");
    assert_eq!(lines[1]["cmd"], "edit");
    assert_eq!(lines[1]["outcome"], "stale");
    assert_eq!(lines[1]["exit"], 1);
    assert_eq!(lines[2]["exit"], 1);
}

#[test]
fn each_knob_does_something() {
    let t = fixture();
    let plain = stdout(&ax(t.path(), &["read", "src/router.ts"]));
    let no_anchor = stdout(&ax_env(
        t.path(),
        &[("AX_NO_ANCHORS", "1")],
        &["read", "src/router.ts"],
    ));
    assert!(
        plain.contains("1:") && no_anchor.contains("\n1  export"),
        "{no_anchor}"
    );

    write(t.path(), "src/big.ts", &"x\n".repeat(50));
    let long = stdout(&ax_env(
        t.path(),
        &[("AX_LONG_FILE", "10"), ("AX_READ_WINDOW", "5")],
        &["read", "src/big.ts"],
    ));
    assert!(long.contains("lines 1-5 of 50"), "{long}");
    let nocap = stdout(&ax_env(
        t.path(),
        &[("AX_LONG_FILE", "10"), ("AX_NO_CAPS", "1")],
        &["read", "src/big.ts"],
    ));
    assert!(nocap.contains("\n50:"), "{nocap}");

    // relocation off: a moved anchor is refused
    let o = ax(t.path(), &["--json", "read", "src/router.ts"]);
    let v: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    let a = v["data"]["files"][0]["rows"][0]["anchor"]
        .as_str()
        .unwrap()
        .to_string();
    write(t.path(), "src/router.ts", "// moved\nexport const r = 1\n");
    let ops = format!("@@ replace {a}\nexport const r = 2\n");
    let o = with_stdin(
        t.path(),
        &[("AX_NO_RELOCATE", "1")],
        &["edit", "src/router.ts"],
        &ops,
    );
    assert_eq!(o.status.code(), Some(1));
    let o = with_stdin(t.path(), &[], &["edit", "src/router.ts"], &ops);
    assert!(o.status.success());
}

#[test]
fn agent_help_note_and_env() {
    let t = fixture();
    let o = ax(t.path(), &["agent-help"]);
    let out = stdout(&o);
    assert!(out.starts_with("## ax\n"));
    assert!(out.contains("not type-aware"));
    assert!(out.contains("@@ replace 12:a3f1..15:9c2e"));
    let env = stdout(&ax(t.path(), &["agent-help", "--env"]));
    for k in [
        "AX_NO_CAPS",
        "AX_NO_ANCHORS",
        "AX_NO_SYMBOLS",
        "AX_NO_PARSE_CHECK",
        "AX_NO_RELOCATE",
        "AX_READ_WINDOW",
        "AX_LOG",
    ] {
        assert!(env.contains(k), "{k}");
    }
}
