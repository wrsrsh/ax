//! `ax grep <pattern> [-F -w -i -S -t -g --in -C -l -c --all]`
//!
//! built on ripgrep's own crates with rg's defaults (line-oriented regex,
//! binary files skipped at the first NUL, same walk), so the set of matching
//! (file, line) pairs is the same as `rg`'s. what's different is the output:
//! grouped by file, then by enclosing symbol, every line anchored, capped,
//! and one summary line at the end.

use crate::hits::{self, Hit};
use crate::output::{Capped, Report, Summary};
use crate::walk::{self, WalkOpts};
use crate::{AxError, Ctx, Result};
use grep::regex::RegexMatcherBuilder;
use grep::searcher::{BinaryDetection, SearcherBuilder, Sink, SinkContext, SinkMatch};
use serde_json::json;
use std::collections::BTreeMap;

#[derive(Debug, Clone, Default)]
pub struct GrepArgs {
    pub pattern: String,
    pub fixed: bool,
    pub word: bool,
    pub ignore_case: bool,
    pub smart_case: bool,
    pub types: Vec<String>,
    pub globs: Vec<String>,
    pub within: Vec<String>,
    pub context: usize,
    pub files_only: bool,
    pub count: bool,
    pub all: bool,
}

/// matched and context lines for one file.
#[derive(Default)]
struct Collect {
    lines: Vec<(usize, Vec<u8>, bool)>,
    matches: usize,
}

impl Sink for Collect {
    type Error = std::io::Error;

    fn matched(
        &mut self,
        _: &grep::searcher::Searcher,
        m: &SinkMatch<'_>,
    ) -> std::io::Result<bool> {
        // a match can span one line here (no multiline), but be safe
        let first = m.line_number().unwrap_or(0) as usize;
        for (i, l) in m.bytes().split_inclusive(|&b| b == b'\n').enumerate() {
            self.lines.push((first + i, l.to_vec(), false));
            self.matches += 1;
        }
        Ok(true)
    }

    fn context(
        &mut self,
        _: &grep::searcher::Searcher,
        c: &SinkContext<'_>,
    ) -> std::io::Result<bool> {
        let n = c.line_number().unwrap_or(0) as usize;
        self.lines.push((n, c.bytes().to_vec(), true));
        Ok(true)
    }
}

pub fn run(ctx: &Ctx, a: &GrepArgs) -> Result<Report> {
    let matcher = RegexMatcherBuilder::new()
        .line_terminator(Some(b'\n'))
        .case_insensitive(a.ignore_case)
        .case_smart(a.smart_case && !a.ignore_case)
        .fixed_strings(a.fixed)
        .word(a.word)
        .build(&a.pattern)
        .map_err(|e| AxError(format!("bad pattern: {e}")))?;
    let mut searcher = SearcherBuilder::new()
        .binary_detection(BinaryDetection::quit(b'\x00'))
        .line_number(true)
        .before_context(a.context)
        .after_context(a.context)
        .build();

    let opts = WalkOpts {
        roots: a.within.clone(),
        globs: a.globs.clone(),
        types: a.types.clone(),
        all: a.all,
    };
    let files = walk::files(ctx, &opts)?;
    let n_searched = files.len();

    // (rel, abs, lines)
    let mut per_file: Vec<(String, std::path::PathBuf, Collect)> = Vec::new();
    for e in files {
        let mut sink = Collect::default();
        if searcher.search_path(&matcher, &e.abs, &mut sink).is_err() {
            continue; // unreadable file: rg warns and moves on, so do we
        }
        if sink.matches > 0 {
            per_file.push((e.rel, e.abs, sink));
        }
    }
    let total_hits: usize = per_file.iter().map(|(_, _, c)| c.matches).sum();
    let n_files = per_file.len();
    let pat = format!("/{}/", a.pattern);

    let mut r = Report::new("grep");
    let narrow = "--in <dir>, -t <type>, -g <glob> or a stricter pattern";

    if a.files_only || a.count {
        let rows: Vec<(String, usize)> = per_file
            .iter()
            .map(|(rel, _, c)| (rel.clone(), c.matches))
            .collect();
        let capped = Capped::new(rows, ctx.cfg.hit_cap());
        r.lines = capped
            .items
            .iter()
            .map(|(rel, n)| {
                if a.count {
                    format!("{rel}: {n}")
                } else {
                    rel.clone()
                }
            })
            .collect();
        r.summary = Summary::counted(
            "file",
            capped.total,
            capped.items.len(),
            &format!("with hits for {pat} ({total_hits} hits)"),
            narrow,
        );
        r.data = json!(
            capped
                .items
                .iter()
                .map(|(rel, n)| json!({"path": rel, "count": n}))
                .collect::<Vec<_>>()
        );
    } else {
        // cap on matching lines; context lines ride along with their match
        let cap = ctx.cfg.hit_cap().unwrap_or(usize::MAX);
        let mut shown_hits = 0;
        let mut out: Vec<Hit> = Vec::new();
        'files: for (rel, abs, c) in &per_file {
            if shown_hits >= cap {
                break;
            }
            let src = std::fs::read(abs).unwrap_or_default();
            let syms = hits::symbols_for(&ctx.cfg, rel, &src);
            let mut lines: BTreeMap<usize, (Vec<u8>, bool)> = BTreeMap::new();
            for (n, b, is_ctx) in &c.lines {
                // a line can be both context (for one hit) and a match; match wins
                let e = lines.entry(*n).or_insert((b.clone(), *is_ctx));
                e.1 &= *is_ctx;
            }
            let mut pending_ctx: Vec<Hit> = Vec::new();
            for (n, (b, is_ctx)) in lines {
                let h = Hit {
                    rel: rel.clone(),
                    line: n,
                    bytes: b,
                    symbol: crate::syntax::enclosing(&syms, n).cloned(),
                    context: is_ctx,
                };
                if is_ctx {
                    pending_ctx.push(h);
                    continue;
                }
                if shown_hits >= cap {
                    break 'files;
                }
                out.append(&mut pending_ctx);
                out.push(h);
                shown_hits += 1;
            }
            // whatever's left is after-context of this file's last hit
            out.append(&mut pending_ctx);
        }
        r.lines = hits::render(&ctx.cfg, &out);
        r.summary = Summary::counted(
            "hit",
            total_hits,
            shown_hits,
            &format!("for {pat} in {}", crate::text::plural(n_files, "file")),
            narrow,
        );
        r.data = hits::to_json(&out);
    }

    if total_hits == 0 {
        r.summary.text = format!(
            "no hits for {pat} in {}{}.",
            crate::text::plural(n_searched, "file"),
            if a.all {
                ""
            } else {
                " (hidden + gitignored skipped; --all searches them)"
            }
        );
    }
    Ok(r)
}
