mod common;
use common::*;

fn sym_fixture() -> tempfile::TempDir {
    let t = tempfile::tempdir().unwrap();
    let r = t.path();
    git(r, &["init", "-q"]);
    write(
        r,
        "src/app.ts",
        "\
import { route } from './route'

export class App {
  handle(req: Request) {
    // route the request, route is imported
    return route(req, 'route')
  }
  fetch = (req: Request) => {
    return this.handle(req)
  }
}
",
    );
    write(
        r,
        "src/route.ts",
        "export function route(req: Request, name: string) {\n  return name\n}\n",
    );
    write(
        r,
        "py/mod.py",
        "class Box:\n    def route(self):\n        return 1\n",
    );
    write(r, "notes.md", "we should rename route\n");
    t
}

#[test]
fn outline_file_and_dir() {
    let t = sym_fixture();
    let o = ax(t.path(), &["outline", "src/app.ts"]);
    assert!(o.status.success());
    assert_eq!(
        body(&o),
        vec![
            "src/app.ts  (11 lines)",
            "  3-11  class App",
            "   4-7    method handle",
            "  8-10    method fetch",
        ]
    );
    assert_eq!(summary(&o), "3 symbols in src/app.ts.");

    let o = ax(t.path(), &["outline", "."]);
    let out = stdout(&o);
    assert!(
        out.contains("py/mod.py  (3 lines)") && out.contains("method route"),
        "{out}"
    );
    assert!(summary(&o).contains("symbols in 3 files"), "{out}");
}

#[test]
fn outline_unsupported_and_missing() {
    let t = sym_fixture();
    let o = ax(t.path(), &["outline", "notes.md"]);
    assert!(o.status.success());
    assert!(summary(&o).starts_with("no outline for notes.md"));
    let o = ax(t.path(), &["outline", "nope.ts"]);
    assert_eq!(o.status.code(), Some(1));
}

#[test]
fn def_finds_all_languages_and_dotted_paths() {
    let t = sym_fixture();
    let o = ax(t.path(), &["def", "route"]);
    let b = body(&o);
    assert_eq!(b[0], "py/mod.py:2-3  method Box.route");
    assert_eq!(b[2], "src/route.ts:1-3  function route");
    assert!(
        b[3].starts_with("  1:")
            && b[3].ends_with("export function route(req: Request, name: string) {")
    );
    assert_eq!(summary(&o), "2 definitions of route.");

    let o = ax(t.path(), &["def", "App.fetch"]);
    assert_eq!(body(&o)[0], "src/app.ts:8-10  method App.fetch");
    let o = ax(t.path(), &["def", "route", "--in", "src"]);
    assert_eq!(summary(&o), "1 definition of route.");
    let o = ax(t.path(), &["def", "nothing_here"]);
    assert!(o.status.success());
    assert!(summary(&o).starts_with("no definitions of nothing_here"));
}

#[test]
fn refs_group_by_symbol_and_code_only() {
    let t = sym_fixture();
    let o = ax(t.path(), &["refs", "route", "--in", "src"]);
    let b = body(&o);
    assert_eq!(b[0], "src/app.ts");
    assert!(b[1].starts_with("  1:"), "{b:?}");
    assert_eq!(b[2], "  @ App.handle  (method 4-7)");
    assert!(
        b[3].starts_with("  5:") && b[4].starts_with("  6:"),
        "{b:?}"
    );
    assert!(summary(&o).contains("name match, not type-aware"));

    // comment on line 5 goes away, line 6 stays (it has a real call too)
    let code = body(&ax(
        t.path(),
        &["refs", "route", "--code-only", "--in", "src"],
    ));
    assert!(!code.iter().any(|l| l.starts_with("  5:")), "{code:?}");
    assert!(code.iter().any(|l| l.starts_with("  6:")), "{code:?}");

    // plain refs include non-code files, --code-only skips them and says so
    assert!(stdout(&ax(t.path(), &["refs", "route"])).contains("notes.md"));
    let o = ax(t.path(), &["refs", "route", "--code-only"]);
    assert!(!stdout(&o).contains("notes.md"));
    assert!(summary(&o).contains("skipped 1 non-"), "{}", summary(&o));
}

#[test]
fn symbol_tags_can_be_switched_off() {
    let t = sym_fixture();
    let o = ax_env(
        t.path(),
        &[("AX_NO_SYMBOLS", "1")],
        &["refs", "route", "--in", "src"],
    );
    assert!(!stdout(&o).contains("@ "), "{}", stdout(&o));
}

#[test]
fn refs_json() {
    let t = sym_fixture();
    let o = ax(t.path(), &["--json", "refs", "handle"]);
    let v: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
    let hits = v["data"].as_array().unwrap();
    assert_eq!(hits.len(), 2);
    assert_eq!(hits[1]["symbol"], "App.fetch");
    assert!(hits[1]["anchor"].as_str().unwrap().starts_with("9:"));
}
