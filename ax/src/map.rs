//! `ax map [dir]`: one screen (~50 lines) to get your bearings. branch +
//! dirty files, stack, build/test scripts, agent docs, and a gitignore-aware
//! tree with file counts that expands the biggest dirs while space lasts.

use crate::output::{Report, Summary};
use crate::walk::{self, WalkOpts};
use crate::{Ctx, Result, repo};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::path::Path;
use std::process::Command;

const SCREEN: usize = 50;
const MAX_SCRIPTS: usize = 10;
const MAX_DIRTY: usize = 8;

fn git(root: &Path, args: &[&str]) -> Option<String> {
    let out = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .ok()?;
    out.status
        .success()
        .then(|| String::from_utf8_lossy(&out.stdout).trim_end().to_string())
}

#[derive(Default)]
struct Dir {
    files: usize,
    own_files: Vec<String>,
    dirs: BTreeMap<String, Dir>,
}

impl Dir {
    fn insert(&mut self, parts: &[&str]) {
        self.files += 1;
        match parts {
            [name] => self.own_files.push(name.to_string()),
            [d, rest @ ..] => self.dirs.entry(d.to_string()).or_default().insert(rest),
            [] => {}
        }
    }
}

fn short(s: &str, n: usize) -> String {
    if s.chars().count() <= n {
        s.to_string()
    } else {
        format!("{}…", s.chars().take(n - 1).collect::<String>())
    }
}

/// package.json scripts (test/build/lint-ish first), makefile targets.
fn scripts(dir: &Path) -> Vec<(String, String, String)> {
    let mut out = Vec::new();
    if let Ok(s) = std::fs::read_to_string(dir.join("package.json"))
        && let Ok(v) = serde_json::from_str::<Value>(&s)
        && let Some(obj) = v["scripts"].as_object()
    {
        // exact well-known names first, then their `name:variant`s,
        // then everything else, so `build` never hides behind 9 `test:*`s
        const KNOWN: [&str; 7] = [
            "test",
            "build",
            "lint",
            "check",
            "typecheck",
            "format",
            "dev",
        ];
        let rank = |k: &str| {
            if let Some(i) = KNOWN.iter().position(|p| k == *p) {
                (0, i)
            } else if let Some(i) = KNOWN.iter().position(|p| k.starts_with(&format!("{p}:"))) {
                (1, i)
            } else {
                (2, 0)
            }
        };
        let mut items: Vec<_> = obj.iter().collect();
        items.sort_by_key(|(k, _)| (rank(k), k.len()));
        for (k, cmd) in items {
            out.push((
                "package.json".into(),
                k.clone(),
                cmd.as_str().unwrap_or("").to_string(),
            ));
        }
    }
    for mk in ["Makefile", "makefile", "justfile"] {
        if let Ok(s) = std::fs::read_to_string(dir.join(mk)) {
            for line in s.lines() {
                let Some((t, _)) = line.split_once(':') else {
                    continue;
                };
                let ok = !t.is_empty()
                    && !line.starts_with(['\t', ' ', '.', '#'])
                    && !line.contains(":=")
                    && t.chars().all(|c| c.is_alphanumeric() || "-_".contains(c));
                if ok {
                    out.push((mk.into(), t.to_string(), String::new()));
                }
            }
        }
    }
    out
}

fn stack(dir: &Path, ext_counts: &BTreeMap<String, usize>) -> Vec<String> {
    let mut s = Vec::new();
    let has = |f: &str| dir.join(f).exists();
    if let Ok(pj) = std::fs::read_to_string(dir.join("package.json")) {
        let v: Value = serde_json::from_str(&pj).unwrap_or(Value::Null);
        let pm = v["packageManager"]
            .as_str()
            .map(|p| p.replace('@', " "))
            .or_else(|| {
                [
                    ("pnpm-lock.yaml", "pnpm"),
                    ("bun.lock", "bun"),
                    ("bun.lockb", "bun"),
                    ("yarn.lock", "yarn"),
                    ("package-lock.json", "npm"),
                ]
                .iter()
                .find(|(f, _)| has(f))
                .map(|(_, p)| p.to_string())
            });
        s.push(match pm {
            Some(pm) => format!("node ({pm})"),
            None => "node".into(),
        });
        let deps = |k: &str| {
            v[k].as_object()
                .map(|o| o.keys().cloned().collect::<Vec<_>>())
        };
        let all: Vec<String> = ["dependencies", "devDependencies"]
            .iter()
            .filter_map(|k| deps(k))
            .flatten()
            .collect();
        for t in [
            "typescript",
            "vitest",
            "jest",
            "vite",
            "react",
            "next",
            "vite-plus",
        ] {
            if all.iter().any(|d| d == t) {
                s.push(t.into());
            }
        }
    }
    for (f, name) in [
        ("Cargo.toml", "rust (cargo)"),
        ("pyproject.toml", "python (pyproject)"),
        ("setup.py", "python (setup.py)"),
        ("go.mod", "go"),
        ("deno.json", "deno"),
        ("Gemfile", "ruby"),
        ("pom.xml", "java (maven)"),
        ("build.gradle", "jvm (gradle)"),
    ] {
        if has(f) {
            s.push(name.into());
        }
    }
    let mut exts: Vec<_> = ext_counts.iter().collect();
    exts.sort_by(|a, b| b.1.cmp(a.1).then(a.0.cmp(b.0)));
    let top: Vec<String> = exts
        .iter()
        .take(6)
        .map(|(e, n)| format!("{e} {n}"))
        .collect();
    if !top.is_empty() {
        s.push(format!("files: {}", top.join(", ")));
    }
    s
}

/// render the tree into at most `budget` lines.
fn tree(root: &Dir, budget: usize) -> Vec<String> {
    // level 1: every dir, then files (collapsed if they don't fit)
    let mut lines: Vec<(String, Vec<String>)> = Vec::new();
    for (name, d) in &root.dirs {
        lines.push((format!("  {name}/  {}", d.files), Vec::new()));
    }
    let dir_lines = lines.len();
    let room = budget.saturating_sub(dir_lines);
    if root.own_files.len() <= room {
        for f in &root.own_files {
            lines.push((format!("  {f}"), Vec::new()));
        }
    } else {
        let show = room.saturating_sub(1);
        for f in &root.own_files[..show] {
            lines.push((format!("  {f}"), Vec::new()));
        }
        lines.push((
            format!("  … +{} more files here", root.own_files.len() - show),
            Vec::new(),
        ));
    }
    // level 2: expand the biggest dirs while budget remains
    let mut used = lines.len();
    let mut order: Vec<(usize, &String, &Dir)> = root
        .dirs
        .iter()
        .enumerate()
        .map(|(i, (n, d))| (i, n, d))
        .collect();
    order.sort_by_key(|a| std::cmp::Reverse(a.2.files));
    for (i, _, d) in order {
        if used >= budget {
            break;
        }
        let mut kids: Vec<String> = d
            .dirs
            .iter()
            .map(|(n, c)| format!("    {n}/  {}", c.files))
            .collect();
        if !d.own_files.is_empty() {
            kids.push(format!("    ({} files)", d.own_files.len()));
        }
        if kids.len() <= 1 && d.dirs.is_empty() {
            continue;
        }
        let room = budget - used;
        if kids.len() > room {
            if room < 2 {
                continue;
            }
            let extra = kids.len() - (room - 1);
            kids.truncate(room - 1);
            kids.push(format!("    … +{extra} more"));
        }
        used += kids.len();
        lines[i].1 = kids;
    }
    lines
        .into_iter()
        .flat_map(|(l, kids)| std::iter::once(l).chain(kids))
        .collect()
}

pub fn run(ctx: &Ctx, dir: Option<&str>) -> Result<Report> {
    let base = match dir {
        Some(d) => repo::absolute(&ctx.cwd, d.as_ref()),
        None => ctx.root.clone(),
    };
    let base_rel = repo::rel(&ctx.root, &base);
    let opts = WalkOpts {
        roots: vec![base.to_string_lossy().into_owned()],
        ..Default::default()
    };
    let files = walk::files(ctx, &opts)?;

    let mut t = Dir::default();
    let mut exts: BTreeMap<String, usize> = BTreeMap::new();
    let prefix = if base_rel == "." {
        String::new()
    } else {
        format!("{base_rel}/")
    };
    for f in &files {
        let rel = f.rel.strip_prefix(&prefix).unwrap_or(&f.rel);
        let parts: Vec<&str> = rel.split('/').collect();
        t.insert(&parts);
        let name = parts.last().copied().unwrap_or("");
        if let Some((_, e)) = name.rsplit_once('.')
            && (!name.starts_with('.') || name.matches('.').count() > 1)
        {
            *exts.entry(e.to_string()).or_default() += 1;
        }
    }

    let mut lines = Vec::new();
    let name = ctx
        .root
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default();
    let branch = git(&ctx.root, &["rev-parse", "--abbrev-ref", "HEAD"]);
    let dirty: Vec<String> = git(&ctx.root, &["status", "--porcelain"])
        .map(|s| s.lines().map(str::to_string).collect())
        .unwrap_or_default();
    let head = match &branch {
        Some(b) => format!("{name}  (branch {b}, {} dirty)", dirty.len()),
        None => format!("{name}  (not a git repo)"),
    };
    lines.push(if base_rel == "." {
        head
    } else {
        format!("{head}  · mapping {base_rel}/")
    });

    let st = stack(&base, &exts);
    if !st.is_empty() {
        lines.push(format!("stack: {}", st.join(" · ")));
    }

    let sc = scripts(&base);
    if !sc.is_empty() {
        lines.push(format!("scripts ({}):", sc[0].0));
        for (_, k, cmd) in sc.iter().take(MAX_SCRIPTS) {
            if cmd.is_empty() {
                lines.push(format!("  {k}"));
            } else {
                lines.push(format!("  {k}: {}", short(cmd, 90)));
            }
        }
        if sc.len() > MAX_SCRIPTS {
            lines.push(format!("  … +{} more", sc.len() - MAX_SCRIPTS));
        }
    }

    let docs: Vec<String> = files
        .iter()
        .filter(|f| {
            let n = f.rel.rsplit('/').next().unwrap_or("");
            matches!(
                n,
                "CLAUDE.md" | "AGENTS.md" | "AGENT.md" | "GEMINI.md" | ".cursorrules"
            )
        })
        .take(6)
        .map(|f| {
            let n = std::fs::read(&f.abs)
                .map(|b| crate::text::line_count(&b))
                .unwrap_or(0);
            format!("{} ({n} lines)", f.rel)
        })
        .collect();
    if !docs.is_empty() {
        lines.push(format!("agent docs: {}", docs.join(", ")));
    }

    let dirty_lines = if dirty.is_empty() {
        0
    } else {
        1 + dirty.len().min(MAX_DIRTY) + usize::from(dirty.len() > MAX_DIRTY)
    };
    lines.push(format!("tree ({} files):", files.len()));
    let budget = SCREEN.saturating_sub(lines.len() + dirty_lines + 1).max(8);
    lines.extend(tree(&t, budget));

    if !dirty.is_empty() {
        lines.push("dirty:".into());
        for d in dirty.iter().take(MAX_DIRTY) {
            lines.push(format!("  {d}"));
        }
        if dirty.len() > MAX_DIRTY {
            lines.push(format!("  … +{} more (ax diff)", dirty.len() - MAX_DIRTY));
        }
    }

    let n_dirs = {
        fn count(d: &Dir) -> usize {
            d.dirs.len() + d.dirs.values().map(count).sum::<usize>()
        }
        count(&t)
    };
    let mut r = Report::new("map");
    r.summary = Summary::plain(format!(
        "{} files in {n_dirs} dirs. zoom in with `ax map <dir>`, list with `ax find`, peek with `ax outline <dir>`.",
        files.len()
    ));
    r.summary.total = files.len();
    r.summary.shown = files.len();
    r.data = json!({
        "root": name,
        "dir": base_rel,
        "branch": branch,
        "dirty": dirty,
        "stack": st,
        "scripts": sc.iter().map(|(src, k, cmd)| json!({"source": src, "name": k, "cmd": cmd})).collect::<Vec<_>>(),
        "agent_docs": docs,
        "files": files.len(),
        "dirs": n_dirs,
        "tree": lines.iter().skip_while(|l| !l.starts_with("tree (")).skip(1).take_while(|l| l.starts_with("  ")).cloned().collect::<Vec<_>>(),
    });
    r.lines = lines;
    Ok(r)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tree_fits_budget() {
        let mut t = Dir::default();
        for i in 0..40 {
            for j in 0..(i % 7 + 1) {
                t.insert(&[&format!("d{i}"), &format!("sub{j}"), "f.rs"]);
            }
            t.insert(&[&format!("top{i}.md")]);
        }
        for budget in [8, 20, 45] {
            let l = tree(&t, budget);
            // level-1 dirs always show, everything else squeezes into what's left
            assert!(l.len() <= budget.max(40 + 1), "{} > {budget}", l.len());
        }
    }

    #[test]
    fn small_tree_is_complete() {
        let mut t = Dir::default();
        t.insert(&["src", "main.rs"]);
        t.insert(&["src", "lib", "a.rs"]);
        t.insert(&["README.md"]);
        let l = tree(&t, 40);
        assert_eq!(
            l,
            vec!["  src/  2", "    lib/  1", "    (1 files)", "  README.md"]
        );
    }

    #[test]
    fn shortens() {
        assert_eq!(short("abcdef", 4), "abc…");
        assert_eq!(short("abc", 4), "abc");
    }
}
