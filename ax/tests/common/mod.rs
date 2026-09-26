#![allow(dead_code)]

use assert_cmd::Command;
use std::fs;
use std::path::Path;
use std::process::Output;

pub fn write(root: &Path, rel: &str, body: &str) {
    let p = root.join(rel);
    fs::create_dir_all(p.parent().unwrap()).unwrap();
    fs::write(p, body).unwrap();
}

pub fn git(root: &Path, args: &[&str]) {
    let ok = std::process::Command::new("git")
        .arg("-C")
        .arg(root)
        .args([
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "-c",
            "init.defaultBranch=main",
        ])
        .args(args)
        .output()
        .unwrap()
        .status
        .success();
    assert!(ok, "git {args:?} failed");
}

/// a small git repo with ignored, hidden and nested files.
pub fn fixture() -> tempfile::TempDir {
    let t = tempfile::tempdir().unwrap();
    let r = t.path();
    git(r, &["init", "-q"]);
    write(r, ".gitignore", "target/\n*.log\n");
    write(r, "README.md", "# demo\n");
    write(r, "CLAUDE.md", "be nice\nplease\n");
    write(
        r,
        "package.json",
        r#"{"packageManager":"pnpm@9.0.0","scripts":{"test:unit":"vitest","test":"vitest run","build":"tsc"},"devDependencies":{"typescript":"5","vitest":"3"}}"#,
    );
    write(r, "src/main.rs", "fn main() {}\n");
    write(r, "src/router.ts", "export const r = 1\n");
    write(r, "src/deep/nested/util.ts", "export const u = 2\n");
    write(r, "src/Router.test.ts", "test('x', () => {})\n");
    write(r, "target/debug/junk.rs", "ignored\n");
    write(r, "app.log", "ignored\n");
    write(r, ".hidden/secret.ts", "hidden\n");
    git(r, &["add", "-A"]);
    git(r, &["commit", "-qm", "init"]);
    t
}

fn cmd(dir: &Path, env: &[(&str, &str)], args: &[&str]) -> Command {
    let mut c = Command::cargo_bin("ax").unwrap();
    c.current_dir(dir).args(args).envs(env.iter().copied());
    c
}

pub fn ax(dir: &Path, args: &[&str]) -> Output {
    cmd(dir, &[], args).output().unwrap()
}

pub fn ax_env(dir: &Path, env: &[(&str, &str)], args: &[&str]) -> Output {
    cmd(dir, env, args).output().unwrap()
}

/// `ax` with `input` on stdin.
pub fn ax_in(dir: &Path, args: &[&str], input: impl AsRef<[u8]>) -> Output {
    ax_env_in(dir, &[], args, input)
}

pub fn ax_env_in(
    dir: &Path,
    env: &[(&str, &str)],
    args: &[&str],
    input: impl AsRef<[u8]>,
) -> Output {
    cmd(dir, env, args)
        .write_stdin(input.as_ref())
        .output()
        .unwrap()
}

/// anchor for line n, taken from `ax read --json` like an agent would.
pub fn anchor(dir: &Path, path: &str, n: usize) -> String {
    let o = ax(dir, &["--json", "read", &format!("{path}:{n}-{n}")]);
    let v: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    v["data"]["files"][0]["rows"][0]["anchor"]
        .as_str()
        .unwrap()
        .to_string()
}

/// `rg <args>` in `dir`, output lines sorted.
pub fn rg(dir: &Path, args: &[&str]) -> Vec<String> {
    let o = std::process::Command::new("rg")
        .args(args)
        .current_dir(dir)
        .stdin(std::process::Stdio::null())
        .output()
        .unwrap();
    let mut lines: Vec<String> = String::from_utf8(o.stdout)
        .unwrap()
        .lines()
        .map(str::to_string)
        .collect();
    lines.sort();
    lines
}

pub fn stdout(o: &Output) -> String {
    String::from_utf8(o.stdout.clone()).unwrap()
}

pub fn stderr(o: &Output) -> String {
    String::from_utf8_lossy(&o.stderr).into_owned()
}

/// all output lines except the trailing summary line.
pub fn body(o: &Output) -> Vec<String> {
    let s = stdout(o);
    let mut l: Vec<String> = s.lines().map(str::to_string).collect();
    l.pop();
    l
}

pub fn summary(o: &Output) -> String {
    stdout(o).lines().last().unwrap_or("").to_string()
}

pub fn have_rg() -> bool {
    std::process::Command::new("rg")
        .arg("--version")
        .output()
        .is_ok_and(|o| o.status.success())
}
