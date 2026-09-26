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
use std::sync::atomic::{AtomicUsize, Ordering};

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
    /// hit a NUL after some matches (search stopped there)
    binary: bool,
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

    fn binary_data(&mut self, _: &grep::searcher::Searcher, _: u64) -> std::io::Result<bool> {
        self.binary = true;
        Ok(false)
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
    let mut searcher = SearcherBuilder::new();
    searcher
        .binary_detection(BinaryDetection::quit(b'\x00'))
        .line_number(true)
        .before_context(a.context)
        .after_context(a.context);

    let opts = WalkOpts {
        roots: a.within.clone(),
        globs: a.globs.clone(),
        types: a.types.clone(),
        all: a.all,
    };
    let files = walk::files(ctx, &opts)?;
    let n_searched = files.len();

    let threads = threads();
    let found = par_map(threads, 16, &files, &|| searcher.build(), &|s, e| {
        let mut sink = Collect::default();
        // unreadable file: rg warns and moves on, so do we
        s.search_path(&matcher, &e.abs, &mut sink)
            .ok()
            .map(|_| sink)
    });

    // (rel, abs, lines)
    let mut per_file: Vec<(String, std::path::PathBuf, Collect)> = Vec::new();
    let mut binary_skipped = 0;
    for (e, sink) in files.into_iter().zip(found) {
        let Some(sink) = sink else { continue };
        if sink.matches > 0 {
            per_file.push((e.rel, e.abs, sink));
        } else if sink.binary {
            binary_skipped += 1;
        }
    }
    let total_hits: usize = per_file.iter().map(|(_, _, c)| c.matches).sum();
    let n_files = per_file.len();
    let pat = format!("/{}/", a.pattern);

    let mut r = Report::new("grep");
    let narrow = "--in <dir>, -t <type>, -g <glob> or a stricter pattern";

    if a.files_only || a.count {
        // rg quirk we copy for parity: -c leaves out a file whose search
        // stopped at a NUL after it had already matched (-l and plain mode
        // still show it)
        let rows: Vec<(String, usize)> = per_file
            .iter()
            .filter(|(_, _, c)| !(a.count && c.binary))
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
        // merge only the files we'll show something from (those that start
        // below the cap); only these get parsed for symbols
        let mut merged: Vec<BTreeMap<usize, (Vec<u8>, bool)>> = Vec::new();
        let mut before = 0;
        for (_, _, c) in &per_file {
            if before >= cap {
                break;
            }
            let mut lines: BTreeMap<usize, (Vec<u8>, bool)> = BTreeMap::new();
            for (n, b, is_ctx) in &c.lines {
                // a line can be both context (for one hit) and a match; match wins
                let e = lines.entry(*n).or_insert((b.clone(), *is_ctx));
                e.1 &= *is_ctx;
            }
            before += lines.values().filter(|(_, is_ctx)| !is_ctx).count();
            merged.push(lines);
        }
        let shown = &per_file[..merged.len()];
        let syms = par_map(threads, 1, shown, &|| (), &|_, (rel, abs, _)| {
            let src = std::fs::read(abs).unwrap_or_default();
            hits::symbols_for(&ctx.cfg, rel, &src)
        });

        let mut shown_hits = 0;
        let mut out: Vec<Hit> = Vec::new();
        'files: for (((rel, _, _), lines), syms) in shown.iter().zip(merged).zip(&syms) {
            let mut pending_ctx: Vec<Hit> = Vec::new();
            for (n, (b, is_ctx)) in lines {
                let h = Hit {
                    rel: rel.clone(),
                    line: n,
                    bytes: b,
                    symbol: crate::syntax::enclosing(syms, n).cloned(),
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
    if binary_skipped > 0 {
        r.summary.text.push_str(&format!(
            " skipped {} (not searched, like rg).",
            crate::text::plural(binary_skipped, "binary file")
        ));
    }
    Ok(r)
}

/// worker count: `AX_THREADS` if set (1 = no threads), else one per core.
fn threads() -> usize {
    std::env::var("AX_THREADS")
        .ok()
        .and_then(|v| v.parse().ok())
        .filter(|&n| n > 0)
        .or_else(|| std::thread::available_parallelism().ok().map(|n| n.get()))
        .unwrap_or(1)
}

/// `items.iter().map(f)` on up to `threads` scoped threads, results in input
/// order. workers pull `batch` items at a time off a shared counter so one slow file
/// doesn't stall a whole chunk; `init` makes each worker's scratch state.
fn par_map<T: Sync, S, R: Send>(
    threads: usize,
    batch: usize,
    items: &[T],
    init: &(dyn Fn() -> S + Sync),
    f: &(dyn Fn(&mut S, &T) -> R + Sync),
) -> Vec<R> {
    let threads = threads.min(items.len().div_ceil(batch));
    if threads <= 1 {
        let mut s = init();
        return items.iter().map(|t| f(&mut s, t)).collect();
    }
    let next = AtomicUsize::new(0);
    let mut slots: Vec<Option<R>> = std::iter::repeat_with(|| None).take(items.len()).collect();
    std::thread::scope(|scope| {
        let workers: Vec<_> = (0..threads)
            .map(|_| {
                scope.spawn(|| {
                    let mut s = init();
                    let mut done = Vec::new();
                    loop {
                        let lo = next.fetch_add(batch, Ordering::Relaxed);
                        if lo >= items.len() {
                            break done;
                        }
                        let hi = (lo + batch).min(items.len());
                        for (i, t) in items[lo..hi].iter().enumerate() {
                            done.push((lo + i, f(&mut s, t)));
                        }
                    }
                })
            })
            .collect();
        for w in workers {
            for (i, r) in w.join().expect("grep worker panicked") {
                slots[i] = Some(r);
            }
        }
    });
    slots
        .into_iter()
        .map(|r| r.expect("every slot filled"))
        .collect()
}
