mod common;
use common::*;

#[test]
fn find_matches_rg_files() {
    if !have_rg() {
        eprintln!("rg not installed, skipping parity check");
        return;
    }
    let t = fixture();
    let o = ax(t.path(), &["find"]);
    assert!(o.status.success());
    let mut ours = body(&o);
    ours.sort();
    let rg = std::process::Command::new("rg")
        .arg("--files")
        .current_dir(t.path())
        .output()
        .unwrap();
    let mut theirs: Vec<String> = String::from_utf8(rg.stdout)
        .unwrap()
        .lines()
        .map(str::to_string)
        .collect();
    theirs.sort();
    assert_eq!(ours, theirs);
    for g in ["*.ts", "src/**/*.ts", "!*.md"] {
        let mut ours = body(&ax(t.path(), &["find", g]));
        ours.sort();
        let rg = std::process::Command::new("rg")
            .args(["--files", "-g", g])
            .current_dir(t.path())
            .output()
            .unwrap();
        let mut theirs: Vec<String> = String::from_utf8(rg.stdout)
            .unwrap()
            .lines()
            .map(str::to_string)
            .collect();
        theirs.sort();
        assert_eq!(ours, theirs, "glob {g}");
    }
}

#[test]
fn find_skips_ignored_and_hidden_unless_all() {
    let t = fixture();
    let files = body(&ax(t.path(), &["find"]));
    assert!(
        !files
            .iter()
            .any(|f| f.contains("target/") || f.ends_with(".log") || f.contains(".hidden"))
    );
    let all = body(&ax(t.path(), &["find", "--all"]));
    assert!(all.iter().any(|f| f == "target/debug/junk.rs"));
    assert!(all.iter().any(|f| f == ".hidden/secret.ts"));
    assert!(all.iter().any(|f| f == "app.log"));
}

#[test]
fn find_by_name_is_smart_case() {
    let t = fixture();
    let lower = body(&ax(t.path(), &["find", "router"]));
    assert_eq!(lower, vec!["src/Router.test.ts", "src/router.ts"]);
    let upper = body(&ax(t.path(), &["find", "Router"]));
    assert_eq!(upper, vec!["src/Router.test.ts"]);
    let path = body(&ax(t.path(), &["find", "deep/nested"]));
    assert_eq!(path, vec!["src/deep/nested/util.ts"]);
}

#[test]
fn find_filters() {
    let t = fixture();
    assert_eq!(
        body(&ax(t.path(), &["find", "--ext", "rs"])),
        vec!["src/main.rs"]
    );
    assert_eq!(
        body(&ax(t.path(), &["find", "--ext", ".rs,md", "--in", "src"])),
        vec!["src/main.rs"]
    );
    // --in works from a subdir too, paths stay repo-relative
    let sub = t.path().join("src");
    assert_eq!(
        body(&ax(&sub, &["find", "util", "--in", "deep"])),
        vec!["src/deep/nested/util.ts"]
    );
    // age filter: make one file old
    let old = std::fs::File::options()
        .write(true)
        .open(t.path().join("README.md"))
        .unwrap();
    old.set_modified(std::time::SystemTime::now() - std::time::Duration::from_secs(7200))
        .unwrap();
    let fresh = body(&ax(t.path(), &["find", "--changed", "1h"]));
    assert!(!fresh.contains(&"README.md".to_string()));
    assert!(fresh.contains(&"src/main.rs".to_string()));
}

#[test]
fn find_empty_is_success_and_says_so() {
    let t = fixture();
    let o = ax(t.path(), &["find", "nope-nothing"]);
    assert!(o.status.success());
    assert!(body(&o).is_empty());
    let s = summary(&o);
    assert!(s.starts_with("no files matching \"nope-nothing\""), "{s}");
    assert!(s.contains("--all"), "{s}");
}

#[test]
fn find_caps_and_tells_you_how_to_narrow() {
    let t = fixture();
    let o = ax_env(t.path(), &[("AX_MAX_HITS", "2")], &["find"]);
    assert_eq!(body(&o).len(), 2);
    let s = summary(&o);
    assert!(
        s.contains("showing first 2") && s.contains("narrow with"),
        "{s}"
    );
    let o = ax_env(
        t.path(),
        &[("AX_MAX_HITS", "2"), ("AX_NO_CAPS", "1")],
        &["find"],
    );
    assert!(body(&o).len() > 2);
}

#[test]
fn find_json() {
    let t = fixture();
    let o = ax(t.path(), &["--json", "find", "*.rs"]);
    let v: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    assert_eq!(v["command"], "find");
    assert_eq!(v["data"]["files"][0], "src/main.rs");
    assert_eq!(v["summary"]["total"], 1);
}

#[test]
fn find_bad_dir_is_an_error() {
    let t = fixture();
    let o = ax(t.path(), &["find", "--in", "nope"]);
    assert_eq!(o.status.code(), Some(1));
}

#[test]
fn map_one_screen() {
    let t = fixture();
    write(t.path(), "src/router.ts", "export const r = 2\n"); // dirty
    let o = ax(t.path(), &["map"]);
    assert!(o.status.success());
    let out = stdout(&o);
    let lines: Vec<&str> = out.lines().collect();
    assert!(lines.len() <= 51, "{} lines", lines.len());
    assert!(
        lines[0].contains("branch main") && lines[0].contains("1 dirty"),
        "{}",
        lines[0]
    );
    assert!(out.contains("node (pnpm 9.0.0)"), "{out}");
    assert!(out.contains("typescript") && out.contains("vitest"));
    // exact names before variants
    let test_pos = out.find("  test: vitest run").unwrap();
    let build_pos = out.find("  build: tsc").unwrap();
    let variant_pos = out.find("  test:unit: vitest").unwrap();
    assert!(test_pos < build_pos && build_pos < variant_pos, "{out}");
    assert!(out.contains("agent docs: CLAUDE.md (2 lines)"), "{out}");
    assert!(out.contains("  src/  4"), "{out}");
    assert!(!out.contains("target"), "{out}");
    assert!(out.contains("dirty:") && out.contains("src/router.ts"));
    assert!(lines.last().unwrap().starts_with("7 files in"), "{out}");
}

#[test]
fn map_subdir_and_json() {
    let t = fixture();
    let o = ax(t.path(), &["--json", "map", "src"]);
    let v: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    assert_eq!(v["data"]["dir"], "src");
    assert_eq!(v["data"]["files"], 4);
    assert_eq!(v["data"]["branch"], "main");
}

#[test]
fn map_outside_git_still_works() {
    let t = tempfile::tempdir().unwrap();
    write(t.path(), "a.py", "print(1)\n");
    let o = ax(t.path(), &["map"]);
    assert!(o.status.success());
    assert!(stdout(&o).contains("not a git repo"));
}

#[test]
fn map_sees_manifests_one_level_down() {
    let t = fixture();
    write(t.path(), "crates/core/Cargo.toml", "[package]\n");
    write(t.path(), "tool/pyproject.toml", "[project]\n");
    write(t.path(), "tool/x.py", "x = 1\n");
    let out = stdout(&ax(t.path(), &["map"]));
    assert!(out.contains("python (tool/)"), "{out}");
    // only one level down, deeper manifests don't count
    assert!(!out.contains("rust ("), "{out}");
}
