//! `ax read <path[:a-b]>... [--sym name] [--full]`
//!
//! - many files / ranges per call
//! - header per file: line count + file hash (for `ax write --if`)
//! - files over AX_LONG_FILE lines (300) get their outline + the first window
//!   (AX_READ_WINDOW, 200 lines) instead of the whole thing
//! - `path:120-180`, `path:120` (a window from 120), `path:120-` (to the end)
//! - `--sym name` reads a symbol's lines (in the given files, or found repo-wide)
//! - a missing file is reported inline and makes the exit code 1, but the
//!   other files in the same call still get read

use crate::output::{Report, Summary, anchor, anchored};
use crate::syntax::{self, Lang, Symbol};
use crate::walk::{self, WalkOpts};
use crate::{AxError, Ctx, Result, hash, repo, text};
use serde_json::{Value, json};

/// total lines one call will print across all files before it stops
const CALL_BUDGET: usize = 1000;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Spec {
    pub path: String,
    /// 1-based inclusive; None = whole file (subject to the long-file rule)
    pub range: Option<(usize, Option<usize>)>,
}

/// `src/a.ts`, `src/a.ts:10-20`, `src/a.ts:10`, `src/a.ts:10-`
pub fn parse_spec(s: &str) -> Result<Spec> {
    if let Some((p, r)) = s.rsplit_once(':') {
        let bad = || {
            AxError(format!(
                "bad range in {s:?} (use path:10-20, path:10 or path:10-)"
            ))
        };
        if !r.is_empty() && r.chars().all(|c| c.is_ascii_digit() || c == '-') {
            let (a, b) = match r.split_once('-') {
                Some((a, "")) => (a.parse().map_err(|_| bad())?, None),
                Some((a, b)) => (
                    a.parse().map_err(|_| bad())?,
                    Some(b.parse().map_err(|_| bad())?),
                ),
                None => (r.parse().map_err(|_| bad())?, Some(usize::MAX)),
            };
            if a == 0 || b.is_some_and(|b| b < a) {
                return Err(bad());
            }
            return Ok(Spec {
                path: p.to_string(),
                range: Some((a, b)),
            });
        }
    }
    Ok(Spec {
        path: s.to_string(),
        range: None,
    })
}

struct Out {
    lines: Vec<String>,
    files: Vec<Value>,
    printed: usize,
    failed: Vec<String>,
    cut: Vec<String>,
}

impl Out {
    fn bytes(&self) -> usize {
        self.lines.iter().map(|l| l.len() + 1).sum()
    }
}

fn outline_of(rel: &str, src: &[u8]) -> Vec<Symbol> {
    let Some(lang) = Lang::from_path(rel) else {
        return Vec::new();
    };
    syntax::parse(lang, src)
        .map(|t| syntax::symbols(lang, &t, src))
        .unwrap_or_default()
}

fn emit(
    ctx: &Ctx,
    o: &mut Out,
    rel: &str,
    src: &[u8],
    start: usize,
    end: usize,
    why: Option<String>,
) {
    let all = text::lines(src);
    let n = all.len();
    let end = end.min(n);
    let want = end + 1 - start.min(end + 1);
    // lines first, then bytes: leave room for headers, notes and the summary
    let lines_left = CALL_BUDGET.saturating_sub(o.printed);
    let bytes_left = ctx.cfg.max_bytes.saturating_sub(o.bytes() + 2_000);
    let mut rows = Vec::new();
    let mut used = 0;
    let mut stop = start.saturating_sub(1);
    for (i, l) in all.iter().enumerate().take(end).skip(start - 1) {
        let line = anchored(&ctx.cfg, i + 1, l);
        if ctx.cfg.caps && (rows.len() >= lines_left || used + line.len() + 1 > bytes_left) {
            break;
        }
        used += line.len() + 1;
        o.lines.push(line);
        rows.push(json!({
            "line": i + 1,
            "anchor": anchor(i + 1, l),
            "text": crate::enc::show(hash::strip_eol(l)),
        }));
        stop = i + 1;
    }
    let take = rows.len();
    o.printed += rows.len();
    let mut note = why;
    if take < want {
        o.cut.push(rel.to_string());
        note = Some(format!(
            "… stopped at line {stop} (per-call output budget). continue with `ax read {rel}:{}-`",
            stop + 1
        ));
    }
    if let Some(n) = &note {
        o.lines.push(n.clone());
    }
    o.files.push(json!({
        "path": rel,
        "lines": n,
        "hash": hash::file_hash(src),
        "start": start,
        "end": stop,
        "rows": rows,
        "note": note,
    }));
}

pub fn run(ctx: &Ctx, paths: &[String], sym: Option<&str>, full: bool) -> Result<Report> {
    let mut o = Out {
        lines: Vec::new(),
        files: Vec::new(),
        printed: 0,
        failed: Vec::new(),
        cut: Vec::new(),
    };
    let window = ctx.cfg.read_window;

    // --sym with no paths: find it repo-wide
    let specs: Vec<Spec> = if paths.is_empty() {
        let Some(s) = sym else {
            return Err(AxError("give at least one path (or --sym name)".into()));
        };
        let needle = s.rsplit('.').next().unwrap_or(s);
        walk::files(ctx, &WalkOpts::default())?
            .into_iter()
            .filter(|e| Lang::from_path(&e.rel).is_some())
            .filter(|e| {
                std::fs::read(&e.abs)
                    .is_ok_and(|b| memchr::memmem::find(&b, needle.as_bytes()).is_some())
            })
            .map(|e| Spec {
                path: e.abs.to_string_lossy().into_owned(),
                range: None,
            })
            .collect()
    } else {
        paths.iter().map(|p| parse_spec(p)).collect::<Result<_>>()?
    };

    let mut sym_hits = 0;
    for spec in &specs {
        let abs = repo::absolute(&ctx.cwd, spec.path.as_ref());
        let rel = repo::rel(&ctx.root, &abs);
        let src = match std::fs::read(&abs) {
            Ok(b) => b,
            Err(e) => {
                let why = if abs.is_dir() {
                    "is a directory (try `ax map` or `ax outline`)".to_string()
                } else {
                    e.to_string().to_lowercase()
                };
                o.lines.push(format!("{rel}: {why}"));
                o.failed.push(rel);
                continue;
            }
        };
        if text::is_binary(&src) {
            o.lines
                .push(format!("{rel}  (binary, {} bytes, not shown)", src.len()));
            o.files
                .push(json!({"path": rel, "binary": true, "bytes": src.len()}));
            continue;
        }
        let n = text::line_count(&src);
        let enc = crate::enc::Enc::detect(&src);
        let header = format!(
            "{rel}  ({}, hash {}{})",
            text::lines_label(n),
            hash::file_hash(&src),
            if enc == crate::enc::Enc::Utf8 {
                String::new()
            } else {
                format!(", {}", enc.label())
            }
        );

        if let Some(s) = sym {
            let found: Vec<Symbol> = outline_of(&rel, &src)
                .into_iter()
                .filter(|x| x.path == s || x.name == s || x.path.ends_with(&format!(".{s}")))
                .collect();
            if found.is_empty() {
                if !paths.is_empty() {
                    o.lines.push(format!("{rel}: no symbol {s}"));
                }
                continue;
            }
            o.lines.push(header);
            for f in found {
                sym_hits += 1;
                o.lines
                    .push(format!("@ {}  ({} {}-{})", f.path, f.kind, f.start, f.end));
                emit(ctx, &mut o, &rel, &src, f.start, f.end, None);
            }
            continue;
        }

        o.lines.push(header);
        if n == 0 {
            o.lines.push("(empty file)".into());
            o.files
                .push(json!({"path": rel, "lines": 0, "hash": hash::file_hash(&src)}));
            continue;
        }
        match spec.range {
            Some((a, b)) => {
                if a > n {
                    o.lines
                        .push(format!("(line {a} is past the end; file has {n})"));
                    continue;
                }
                // explicit `a-b` is honored (only the call budget limits it);
                // `a` is one window from a; `a-` runs to the end but still
                // stops after a window when caps are on
                let (end, capped_end) = match b {
                    Some(usize::MAX) => (n, a + window - 1),
                    Some(b) => (b, b),
                    None if ctx.cfg.caps => (n, a + window - 1),
                    None => (n, n),
                };
                let capped_end = capped_end.min(n);
                let why = (capped_end < end.min(n)).then(|| {
                    format!(
                        "… lines {a}-{capped_end} of {n}. next: `ax read {rel}:{}-{}`",
                        capped_end + 1,
                        (capped_end + window).min(n)
                    )
                });
                emit(ctx, &mut o, &rel, &src, a, capped_end, why);
            }
            None if full || !ctx.cfg.caps || n <= ctx.cfg.long_file => {
                emit(ctx, &mut o, &rel, &src, 1, n, None);
            }
            None => {
                let syms: Vec<Symbol> = outline_of(&rel, &src)
                    .into_iter()
                    .filter(|s| s.depth <= 1)
                    .collect();
                if !syms.is_empty() {
                    o.lines.push(format!("outline ({} symbols):", syms.len()));
                    for s in syms.iter().take(60) {
                        o.lines.push(format!(
                            "  {}-{}  {}{} {}",
                            s.start,
                            s.end,
                            "  ".repeat(s.depth),
                            s.kind,
                            s.name
                        ));
                    }
                    if syms.len() > 60 {
                        o.lines
                            .push(format!("  … +{} more (ax outline {rel})", syms.len() - 60));
                    }
                }
                let why = format!(
                    "… lines 1-{window} of {n}. next: `ax read {rel}:{}-{}`, a symbol with `--sym`, or everything with --full",
                    window + 1,
                    (2 * window).min(n)
                );
                emit(ctx, &mut o, &rel, &src, 1, window, Some(why));
            }
        }
    }

    let mut r = Report::new("read");
    let files_read = o.files.len();
    let mut text = match sym {
        Some(s) if sym_hits == 0 => format!(
            "no symbol {s} found{}. try `ax def {s}`.",
            if paths.is_empty() {
                " in the repo"
            } else {
                " in those files"
            }
        ),
        _ => format!(
            "read {} ({} shown).",
            text::plural(files_read, "file"),
            text::lines_label(o.printed)
        ),
    };
    if !o.failed.is_empty() {
        text.push_str(&format!(" failed: {}.", o.failed.join(", ")));
    }
    if !o.cut.is_empty() {
        text.push_str(" hit the per-call output budget; read fewer files or smaller ranges.");
    }
    r.summary = Summary {
        total: files_read,
        shown: files_read,
        truncated: !o.cut.is_empty(),
        text,
    };
    r.failed = !o.failed.is_empty();
    r.lines = o.lines;
    r.data = json!({ "files": o.files, "failed": o.failed });
    Ok(r)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn specs() {
        assert_eq!(parse_spec("a.ts").unwrap().range, None);
        assert_eq!(parse_spec("a.ts:3-9").unwrap().range, Some((3, Some(9))));
        assert_eq!(parse_spec("a.ts:3-").unwrap().range, Some((3, None)));
        assert_eq!(
            parse_spec("a.ts:3").unwrap().range,
            Some((3, Some(usize::MAX)))
        );
        assert!(parse_spec("a.ts:9-3").is_err());
        assert!(parse_spec("a.ts:0-3").is_err());
        // a colon that isn't a range stays part of the path
        assert_eq!(parse_spec("c:weird").unwrap().path, "c:weird");
    }
}
