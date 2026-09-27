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
    assert_eq!(ours, rg(t.path(), &["--files"]));
    for g in ["*.ts", "src/**/*.ts", "!*.md"] {
        let mut ours = body(&ax(t.path(), &["find", g]));
        ours.sort();
        assert_eq!(ours, rg(t.path(), &["--files", "-g", g]), "glob {g}");
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
    assert!(s.contains("checked hidden + gitignored files too"), "{s}");
}

#[test]
fn find_takes_trailing_paths_like_grep() {
    let t = fixture();
    assert_eq!(
        body(&ax(t.path(), &["find", "*.ts", "src/deep"])),
        vec!["src/deep/nested/util.ts"]
    );
    // several roots, and a substring pattern works the same way
    let o = ax(t.path(), &["find", ".", "src/deep", "README.md"]);
    assert!(o.status.success(), "{}", stderr(&o));
    assert_eq!(body(&o), vec!["README.md", "src/deep/nested/util.ts"]);
    assert!(
        summary(&o).contains("in src/deep, README.md"),
        "{}",
        summary(&o)
    );
    // trailing paths and --in add up
    assert_eq!(
        body(&ax(
            t.path(),
            &["find", "*.ts", "src/deep", "--in", "src/router.ts"]
        )),
        vec!["src/deep/nested/util.ts", "src/router.ts"]
    );
    let o = ax(t.path(), &["find", "x", "nope"]);
    assert_eq!(o.status.code(), Some(1));
}

#[test]
fn find_with_no_hits_shows_ignored_matches() {
    let t = fixture();
    // the harness hides AGENTS.md via .git/info/exclude, not .gitignore
    write(t.path(), "AGENTS.md", "be nice\n");
    write(t.path(), ".git/info/exclude", "AGENTS.md\n");
    let o = ax(t.path(), &["find", "AGENTS.md"]);
    assert!(o.status.success());
    assert_eq!(body(&o), vec!["AGENTS.md  (ignored)"]);
    let s = summary(&o);
    assert!(s.starts_with("no files matching \"AGENTS.md\""), "{s}");
    assert!(
        s.contains("1 hidden/gitignored one exists") && s.contains("--all"),
        "{s}"
    );

    // hidden dirs and gitignored files count too
    assert_eq!(
        body(&ax(t.path(), &["find", "secret"])),
        vec![".hidden/secret.ts  (ignored)"]
    );
    assert_eq!(
        body(&ax(t.path(), &["find", "app.log"])),
        vec!["app.log  (ignored)"]
    );
    // but never git's own files
    assert!(body(&ax(t.path(), &["find", "HEAD"])).is_empty());

    // json keeps files empty and lists them apart
    let o = ax(t.path(), &["--json", "find", "junk"]);
    let v: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    assert_eq!(v["data"]["files"], serde_json::json!([]));
    assert_eq!(v["data"]["ignored"][0], "target/debug/junk.rs");

    // capped at 10
    for i in 0..13 {
        write(t.path(), &format!("target/gen/g{i:02}.rs"), "x\n");
    }
    let o = ax(t.path(), &["find", "gen/g"]);
    assert!(o.status.success());
    assert_eq!(body(&o).len(), 10);
    assert!(
        summary(&o).contains("13 hidden/gitignored ones exist (first 10 above)"),
        "{}",
        summary(&o)
    );

    // --all finds them as plain hits
    assert_eq!(
        body(&ax(t.path(), &["find", "--all", "AGENTS.md"])),
        vec!["AGENTS.md"]
    );
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
fn map_a_subtree() {
    let t = fixture();
    write(
        t.path(),
        "src/deep/package.json",
        r#"{"scripts":{"test":"vitest run"}}"#,
    );
    write(t.path(), "src/router.ts", "export const r = 2\n"); // dirty, outside
    write(t.path(), "src/deep/nested/util.ts", "export const u = 3\n"); // dirty, inside
    let o = ax(t.path(), &["map", "src/deep"]);
    assert!(o.status.success(), "{}", stderr(&o));
    let out = stdout(&o);
    let lines: Vec<&str> = out.lines().collect();
    assert!(
        lines[0].contains("mapping src/deep/") && lines[0].contains("2 dirty"),
        "{out}"
    );
    assert!(out.contains("  test: vitest run"), "{out}");
    assert!(out.contains("  nested/  1"), "{out}");
    assert!(
        out.contains("src/deep/nested/util.ts") && !out.contains("src/router.ts"),
        "{out}"
    );
    assert!(summary(&o).starts_with("2 files in 1 dirs"), "{out}");
    // same thing from inside src
    let o = ax(&t.path().join("src"), &["map", "deep"]);
    assert!(
        stdout(&o)
            .lines()
            .next()
            .unwrap()
            .contains("mapping src/deep/")
    );
}

#[test]
fn map_bad_paths_say_what_to_do() {
    let t = fixture();
    let o = ax(t.path(), &["map", "src/main.rs"]);
    assert_eq!(o.status.code(), Some(1));
    assert!(stderr(&o).contains("is a file") && stderr(&o).contains("ax outline src/main.rs"));
    let o = ax(t.path(), &["map", "nope"]);
    assert_eq!(o.status.code(), Some(1));
    assert!(stderr(&o).contains("no such dir: nope"), "{}", stderr(&o));
    // a dir with only ignored files maps to nothing, and says why
    write(t.path(), "logs/today.log", "x\n");
    let o = ax(t.path(), &["map", "logs"]);
    assert!(o.status.success());
    assert!(summary(&o).contains("--all"), "{}", summary(&o));
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
