//! `ax outline`, `ax def`, `ax refs`: the tree-sitter commands.

use crate::hits::{self, Hit};
use crate::output::{Capped, Report, Summary, anchored};
use crate::syntax::{self, Lang, Symbol};
use crate::text;
use crate::walk::{self, WalkOpts};
use crate::{AxError, Ctx, Result, repo};
use serde_json::json;

const SUPPORTED: &str = "ts/tsx/js/py/rs/go";

fn read(abs: &std::path::Path) -> Option<Vec<u8>> {
    std::fs::read(abs).ok().filter(|b| !text::is_binary(b))
}

fn outline_lines(syms: &[Symbol], max_depth: usize) -> Vec<String> {
    let w = syms
        .iter()
        .map(|s| format!("{}-{}", s.start, s.end).len())
        .max()
        .unwrap_or(0);
    syms.iter()
        .filter(|s| s.depth <= max_depth)
        .map(|s| {
            let range = format!("{}-{}", s.start, s.end);
            format!(
                "  {range:>w$}  {}{} {}",
                "  ".repeat(s.depth),
                s.kind,
                s.name
            )
        })
        .collect()
}

/// `ax outline <path>...`. a file shows every symbol; a dir shows top-level
/// symbols + their direct members per file. several paths come back one
/// after the other under one summary.
pub fn outline(ctx: &Ctx, paths: &[String]) -> Result<Report> {
    if let [one] = paths {
        return outline_one(ctx, one);
    }
    let mut r = Report::new("outline");
    let (mut total, mut shown, mut truncated) = (0, 0, false);
    let mut data = Vec::new();
    for p in paths {
        let one = outline_one(ctx, p)?;
        if !r.lines.is_empty() {
            r.lines.push(String::new());
        }
        r.lines.extend(one.lines);
        total += one.summary.total;
        shown += one.summary.shown;
        truncated |= one.summary.truncated;
        data.push(one.data);
    }
    r.summary = Summary {
        total,
        shown,
        truncated,
        text: format!(
            "{total} symbols across {}{}",
            text::plural(paths.len(), "path"),
            if truncated {
                ", some cut; `ax outline <one path>` for the rest."
            } else {
                "."
            }
        ),
    };
    r.data = json!({ "paths": data });
    Ok(r)
}

fn outline_one(ctx: &Ctx, path: &str) -> Result<Report> {
    let abs = repo::absolute(&ctx.cwd, path.as_ref());
    if !abs.exists() {
        return Err(AxError(format!("no such path: {path}")));
    }
    let mut r = Report::new("outline");
    let cap = ctx.cfg.caps.then_some(ctx.cfg.read_window);

    if abs.is_file() {
        let rel = repo::rel(&ctx.root, &abs);
        if Lang::from_path(&rel).is_none() {
            r.summary = Summary::plain(format!(
                "no outline for {rel}: not a language ax parses ({SUPPORTED}). use `ax read {rel}`."
            ));
            r.data = json!({ "path": rel, "symbols": [] });
            return Ok(r);
        }
        let src = std::fs::read(&abs)?;
        let syms = syntax::file_symbols(&rel, &src);
        let c = Capped::new(outline_lines(&syms, usize::MAX), cap);
        r.lines.push(format!(
            "{rel}  ({})",
            text::lines_label(text::line_count(&src))
        ));
        r.lines.extend(c.items.iter().cloned());
        r.summary = Summary::counted(
            "symbol",
            c.total,
            c.items.len(),
            &format!("in {rel}"),
            "`ax read <file>:<a>-<b>` on a range",
        );
        r.data = json!({ "path": rel, "symbols": syms });
        return Ok(r);
    }

    let opts = WalkOpts {
        roots: vec![abs.to_string_lossy().into_owned()],
        ..Default::default()
    };
    let mut all_lines = Vec::new();
    let mut data = Vec::new();
    let mut n_files = 0;
    let mut n_syms = 0;
    for e in walk::files(ctx, &opts)? {
        let Some(lang) = Lang::from_path(&e.rel) else {
            continue;
        };
        let Some(src) = read(&e.abs) else { continue };
        let Some(tree) = syntax::parse(lang, &src) else {
            continue;
        };
        let syms = syntax::symbols(lang, &tree, &src);
        n_files += 1;
        let shown: Vec<Symbol> = syms.into_iter().filter(|s| s.depth <= 1).collect();
        n_syms += shown.len();
        all_lines.push(format!(
            "{}  ({})",
            e.rel,
            text::lines_label(text::line_count(&src))
        ));
        all_lines.extend(outline_lines(&shown, 1));
        data.push(json!({ "path": e.rel, "symbols": shown }));
    }
    let c = Capped::new(all_lines, cap);
    r.lines = c.items.clone();
    let rel = repo::rel(&ctx.root, &abs);
    r.summary = if c.truncated() {
        Summary {
            total: n_syms,
            shown: c.items.len(),
            truncated: true,
            text: format!(
                "{n_syms} symbols in {n_files} files under {rel}, cut at {} lines. narrow with `ax outline <subdir>` or `ax outline <file>`.",
                c.items.len()
            ),
        }
    } else {
        Summary {
            total: n_syms,
            shown: n_syms,
            truncated: false,
            text: if n_files == 0 {
                format!("no {SUPPORTED} files under {rel}.")
            } else {
                format!("{n_syms} symbols in {n_files} files under {rel} (top level + members).")
            },
        }
    };
    r.data = json!({ "path": rel, "files": data });
    Ok(r)
}

/// `ax def <sym> [--in dir]`: where a symbol is defined. `Hono.fetch` or just
/// `fetch` both work.
pub fn def(ctx: &Ctx, sym: &str, within: &[String]) -> Result<Report> {
    let needle = sym.rsplit('.').next().unwrap_or(sym).as_bytes();
    let opts = WalkOpts {
        roots: within.to_vec(),
        ..Default::default()
    };
    let mut found: Vec<(String, Symbol, Vec<u8>)> = Vec::new();
    for e in walk::files(ctx, &opts)? {
        let Some(lang) = Lang::from_path(&e.rel) else {
            continue;
        };
        let Some(src) = read(&e.abs) else { continue };
        if memchr::memmem::find(&src, needle).is_none() {
            continue;
        }
        let Some(tree) = syntax::parse(lang, &src) else {
            continue;
        };
        let lines = text::lines(&src);
        for s in syntax::symbols(lang, &tree, &src) {
            if s.matches(sym) {
                let first = lines
                    .get(s.start - 1)
                    .map(|l| l.to_vec())
                    .unwrap_or_default();
                found.push((e.rel.clone(), s, first));
            }
        }
    }
    let c = Capped::new(found, ctx.cfg.hit_cap());
    let mut r = Report::new("def");
    for (rel, s, first) in &c.items {
        r.lines.push(format!(
            "{rel}:{}-{}  {} {}",
            s.start, s.end, s.kind, s.path
        ));
        r.lines
            .push(format!("  {}", anchored(&ctx.cfg, s.start, first)));
    }
    r.summary = Summary::counted(
        "definition",
        c.total,
        c.items.len(),
        &format!("of {sym}"),
        "a dotted path like Class.method or --in <dir>",
    );
    if c.total == 0 {
        r.summary.text = format!(
            "no definitions of {sym} in {SUPPORTED} files. names are matched syntactically; try `ax refs {sym}` or `ax grep {sym}`."
        );
    }
    r.data = json!(
        c.items
            .iter()
            .map(|(rel, s, first)| json!({
                "path": rel,
                "symbol": s,
                "anchor": crate::output::anchor(s.start, first),
            }))
            .collect::<Vec<_>>()
    );
    Ok(r)
}

/// `ax refs <sym> [--code-only] [--in dir]`: whole-word occurrences of the
/// symbol's name, tagged with the enclosing symbol. syntactic, not type-aware.
pub fn refs(ctx: &Ctx, sym: &str, code_only: bool, within: &[String]) -> Result<Report> {
    let name = sym.rsplit('.').next().unwrap_or(sym);
    let needle = name.as_bytes();
    let opts = WalkOpts {
        roots: within.to_vec(),
        ..Default::default()
    };
    let mut all = Vec::new();
    let mut skipped_other_langs = 0;
    for e in walk::files(ctx, &opts)? {
        let lang = Lang::from_path(&e.rel);
        let Some(src) = read(&e.abs) else { continue };
        if memchr::memmem::find(&src, needle).is_none() {
            continue;
        }
        if code_only && lang.is_none() {
            skipped_other_langs += 1;
            continue;
        }
        let tree = lang.and_then(|l| syntax::parse(l, &src));
        let syms = match (lang, &tree) {
            (Some(l), Some(t)) if ctx.cfg.symbols => syntax::symbols(l, t, &src),
            _ => Vec::new(),
        };
        let mut offset = 0;
        for (i, line) in text::lines(&src).into_iter().enumerate() {
            let ms = hits::word_matches(line, needle);
            let keep = !ms.is_empty()
                && (!code_only
                    || tree.as_ref().is_none_or(|t| {
                        ms.iter()
                            .any(|&m| syntax::is_code(t, offset + m, offset + m + needle.len()))
                    }));
            if keep {
                all.push(Hit {
                    rel: e.rel.clone(),
                    line: i + 1,
                    bytes: line.to_vec(),
                    symbol: syntax::enclosing(&syms, i + 1).cloned(),
                    context: false,
                });
            }
            offset += line.len();
        }
    }
    let n_files = hits::files_in(&all);
    let c = Capped::new(all, ctx.cfg.hit_cap());
    let mut r = Report::new("refs");
    r.lines = hits::render(&ctx.cfg, &c.items);
    r.summary = Summary::counted(
        "ref",
        c.total,
        c.items.len(),
        &format!("to {name} in {}", text::plural(n_files, "file")),
        "--in <dir> or --code-only",
    );
    if c.total > 0 {
        r.summary
            .text
            .push_str(" (name match, not type-aware: same-named things elsewhere show up too)");
    }
    if code_only && skipped_other_langs > 0 {
        r.summary.text.push_str(&format!(
            " skipped {skipped_other_langs} non-{SUPPORTED} files for --code-only."
        ));
    }
    r.data = hits::to_json(&c.items);
    Ok(r)
}
