//! `ax edit <path>` with ops on stdin. A and B are `LINE:HASH` anchors from
//! `ax read` / `ax grep`:
//!
//! ```text
//! @@ replace A[..B]          followed by the new lines
//! @@ insert after|before A   followed by the new lines
//! @@ delete A[..B]
//! @@ find                    followed by exact text (must occur exactly once)
//! @@ with                    followed by its replacement
//! ```
//!
//! a body line that really starts with `@@ ` is written as `\@@ …`.
//!
//! every op is resolved against the file as it was when the call started, so
//! line numbers never shift between ops. all ops apply or none do. anchors
//! whose line moved are found again by hash nearby (refused if that's
//! ambiguous); anchors whose content changed refuse the whole call and print
//! the current lines with fresh anchors.
//!
//! on success the echo is short: `path: +a -r (n ops)`, then only the lines
//! the ops changed with their new anchors (no context), capped at 12.
//!
//! the core (`apply`) is pure bytes-in / bytes-out so it can be property
//! tested against a dumb reference implementation.

use crate::config::Config;
use crate::hash::line_hash;
use crate::output::{Report, Summary, anchored};
use crate::{Ctx, fsio, hash, repo, text};
use serde_json::json;

/// how far (in lines) a moved anchor is searched for.
pub const RELOCATE_WINDOW: usize = 20;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Anchor {
    /// 1-based
    pub line: usize,
    /// None only when anchors are switched off (AX_NO_ANCHORS)
    pub hash: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Op {
    Replace {
        from: Anchor,
        to: Anchor,
        body: Vec<Vec<u8>>,
    },
    Insert {
        at: Anchor,
        after: bool,
        body: Vec<Vec<u8>>,
    },
    Delete {
        from: Anchor,
        to: Anchor,
    },
    FindWith {
        find: Vec<u8>,
        with: Vec<u8>,
    },
}

/// why an edit call wrote nothing.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Refusal {
    Syntax(String),
    /// the anchored line's content changed; `line` is where it pointed
    Stale {
        anchor: String,
        line: usize,
    },
    /// the anchored line moved and more than one candidate is nearby
    Ambiguous {
        anchor: String,
        candidates: Vec<usize>,
    },
    /// find text: 0 or >1 occurrences
    FindCount {
        count: usize,
        preview: String,
        /// 1-based lines of the occurrences (count > 1)
        lines: Vec<usize>,
        /// near misses (count == 0)
        near: Vec<crate::nearmiss::Candidate>,
    },
    /// two ops touch the same lines
    Overlap(String),
    /// the result doesn't parse where the original did (see parse guard)
    Parse(String),
}

impl Refusal {
    pub fn outcome(&self) -> &'static str {
        match self {
            Refusal::Syntax(_) | Refusal::Overlap(_) => "error",
            Refusal::Stale { .. } => "stale",
            Refusal::Ambiguous { .. } => "ambiguous",
            Refusal::FindCount { .. } => "no-match",
            Refusal::Parse(_) => "parse-rejected",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Applied {
    pub bytes: Vec<u8>,
    pub added: usize,
    pub removed: usize,
    pub relocated: usize,
    /// what each splice really changed, unchanged edge lines trimmed off:
    /// (0-based start line in the new file, lines added there, lines removed)
    pub regions: Vec<(usize, usize, usize)>,
}

fn parse_anchor(tok: &str, cfg: &Config) -> Result<Anchor, Refusal> {
    let (n, h) = match tok.split_once(':') {
        Some((n, h)) => (n, Some(h)),
        None => (tok, None),
    };
    let line: usize = n.parse().ok().filter(|&n| n > 0).ok_or_else(|| {
        Refusal::Syntax(format!(
            "bad anchor {tok:?}, expected LINE:HASH like 12:a3f1"
        ))
    })?;
    match h {
        Some(h) if h.len() == 4 && h.chars().all(|c| c.is_ascii_hexdigit()) => Ok(Anchor {
            line,
            hash: Some(h.to_ascii_lowercase()),
        }),
        Some(_) => Err(Refusal::Syntax(format!(
            "bad anchor {tok:?}: the hash is the 4 hex chars after the colon"
        ))),
        None if !cfg.anchors => Ok(Anchor { line, hash: None }),
        None => Err(Refusal::Syntax(format!(
            "anchor {tok:?} has no hash; use LINE:HASH from `ax read` or `ax grep`"
        ))),
    }
}

fn parse_range(s: &str, cfg: &Config) -> Result<(Anchor, Anchor), Refusal> {
    match s.split_once("..") {
        Some((a, b)) => Ok((parse_anchor(a.trim(), cfg)?, parse_anchor(b.trim(), cfg)?)),
        None => {
            let a = parse_anchor(s.trim(), cfg)?;
            Ok((a.clone(), a))
        }
    }
}

/// parse the op script from stdin.
pub fn parse_ops(input: &[u8], cfg: &Config) -> Result<Vec<Op>, Refusal> {
    let text = String::from_utf8_lossy(input);
    let mut lines: Vec<&str> = text.split('\n').collect();
    if lines.last() == Some(&"") {
        lines.pop(); // trailing newline of stdin ends the last line, it isn't a line
    }
    // (header, body)
    let mut blocks: Vec<(String, Vec<Vec<u8>>)> = Vec::new();
    for l in lines {
        let l = l.strip_suffix('\r').unwrap_or(l);
        if let Some(h) = l.strip_prefix("@@ ").or_else(|| (l == "@@").then_some("")) {
            blocks.push((h.trim().to_string(), Vec::new()));
        } else if let Some((_, body)) = blocks.last_mut() {
            let l = l
                .strip_prefix('\\')
                .filter(|r| r.starts_with("@@"))
                .unwrap_or(l);
            body.push(l.as_bytes().to_vec());
        } else if !l.trim().is_empty() {
            return Err(Refusal::Syntax(format!(
                "expected an op header like `@@ replace 12:a3f1`, got {l:?}"
            )));
        }
    }
    if blocks.is_empty() {
        return Err(Refusal::Syntax("no ops on stdin".into()));
    }
    let mut ops = Vec::new();
    let mut it = blocks.into_iter().peekable();
    while let Some((h, body)) = it.next() {
        let (verb, rest) = h.split_once(' ').unwrap_or((h.as_str(), ""));
        let op = match verb {
            "replace" => {
                let (from, to) = parse_range(rest, cfg)?;
                Op::Replace { from, to, body }
            }
            "delete" => {
                if body.iter().any(|b| !b.is_empty()) {
                    return Err(Refusal::Syntax("`@@ delete` takes no body".into()));
                }
                let (from, to) = parse_range(rest, cfg)?;
                Op::Delete { from, to }
            }
            "insert" => {
                let (side, a) = rest.trim().split_once(' ').ok_or_else(|| {
                    Refusal::Syntax(
                        "use `@@ insert after 12:a3f1` or `@@ insert before 12:a3f1`".into(),
                    )
                })?;
                let after = match side {
                    "after" => true,
                    "before" => false,
                    _ => {
                        return Err(Refusal::Syntax(format!(
                            "insert where? `after` or `before`, got {side:?}"
                        )));
                    }
                };
                Op::Insert {
                    at: parse_anchor(a.trim(), cfg)?,
                    after,
                    body,
                }
            }
            "find" => {
                let Some((wh, with)) = it.next() else {
                    return Err(Refusal::Syntax(
                        "`@@ find` needs a following `@@ with`".into(),
                    ));
                };
                if wh != "with" {
                    return Err(Refusal::Syntax(format!(
                        "`@@ find` must be followed by `@@ with`, got `@@ {wh}`"
                    )));
                }
                if body.is_empty() || body.iter().all(|b| b.is_empty()) {
                    return Err(Refusal::Syntax("`@@ find` text is empty".into()));
                }
                Op::FindWith {
                    find: body.join(&b"\n"[..]),
                    with: with.join(&b"\n"[..]),
                }
            }
            "with" => {
                return Err(Refusal::Syntax(
                    "`@@ with` without a `@@ find` before it".into(),
                ));
            }
            other => {
                return Err(Refusal::Syntax(format!(
                    "unknown op {other:?} (replace, insert, delete, find/with)"
                )));
            }
        };
        ops.push(op);
    }
    Ok(ops)
}

/// a file as lines that each remember their own terminator.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Doc {
    pub lines: Vec<(Vec<u8>, Vec<u8>)>,
    pub eol: Vec<u8>,
    pub bom: bool,
}

const BOM: &[u8] = b"\xEF\xBB\xBF";

impl Doc {
    pub fn parse(src: &[u8]) -> Doc {
        let mut lines = Vec::new();
        let (mut crlf, mut lf) = (0, 0);
        for l in src.split_inclusive(|&b| b == b'\n') {
            let (content, term) = if let Some(c) = l.strip_suffix(b"\r\n") {
                crlf += 1;
                (c, &b"\r\n"[..])
            } else if let Some(c) = l.strip_suffix(b"\n") {
                lf += 1;
                (c, &b"\n"[..])
            } else {
                (l, &b""[..])
            };
            lines.push((content.to_vec(), term.to_vec()));
        }
        Doc {
            lines,
            eol: if crlf > lf {
                b"\r\n".to_vec()
            } else {
                b"\n".to_vec()
            },
            bom: src.starts_with(BOM),
        }
    }

    pub fn ends_with_newline(&self) -> bool {
        self.lines.last().is_none_or(|(_, t)| !t.is_empty())
    }

    /// line `i` without its terminator. a BOM is invisible.
    pub fn content(&self, i: usize) -> &[u8] {
        let c = &self.lines[i].0;
        if i == 0 {
            c.strip_prefix(BOM).unwrap_or(c)
        } else {
            c
        }
    }

    /// push `new` in place of lines [start, end): each new line keeps the
    /// terminator of the old line in its slot, extra ones get the file's eol.
    pub fn push_replacement(
        &self,
        out: &mut Vec<(Vec<u8>, Vec<u8>)>,
        start: usize,
        end: usize,
        new: &[Vec<u8>],
    ) {
        for (i, c) in new.iter().enumerate() {
            let term = if start + i < end {
                self.lines[start + i].1.clone()
            } else {
                self.eol.clone()
            };
            out.push((c.clone(), term));
        }
    }

    /// `lines` rendered as this file: every line but the last gets a
    /// terminator, the last one only if `final_newline`.
    pub fn rebuild(&self, mut lines: Vec<(Vec<u8>, Vec<u8>)>, final_newline: bool) -> Vec<u8> {
        let n = lines.len();
        for (i, (_, t)) in lines.iter_mut().enumerate() {
            if i + 1 < n || final_newline {
                if t.is_empty() {
                    *t = self.eol.clone();
                }
            } else {
                t.clear();
            }
        }
        Doc {
            lines,
            eol: self.eol.clone(),
            bom: self.bom,
        }
        .render()
    }

    /// a BOM the file had is put back even if an edit replaced line 1.
    pub fn render(&self) -> Vec<u8> {
        let mut out = Vec::new();
        if self.bom && !self.lines.first().is_some_and(|(c, _)| c.starts_with(BOM)) {
            out.extend_from_slice(BOM);
        }
        for (c, t) in &self.lines {
            out.extend_from_slice(c);
            out.extend_from_slice(t);
        }
        out
    }
}

fn hash_of(doc: &Doc, idx: usize) -> String {
    line_hash(&doc.lines[idx].0)
}

/// 0-based index of the anchored line in `doc`, relocating if allowed.
fn resolve(doc: &Doc, a: &Anchor, cfg: &Config, relocated: &mut usize) -> Result<usize, Refusal> {
    let n = doc.lines.len();
    let label = match &a.hash {
        Some(h) => format!("{}:{h}", a.line),
        None => a.line.to_string(),
    };
    let Some(h) = &a.hash else {
        return if a.line <= n {
            Ok(a.line - 1)
        } else {
            Err(Refusal::Stale {
                anchor: label,
                line: a.line,
            })
        };
    };
    if a.line <= n && &hash_of(doc, a.line - 1) == h {
        return Ok(a.line - 1);
    }
    if cfg.relocate {
        let center = a.line.saturating_sub(1).min(n.saturating_sub(1));
        let lo = center.saturating_sub(RELOCATE_WINDOW);
        let hi = (center + RELOCATE_WINDOW + 1).min(n);
        let found: Vec<usize> = (lo..hi).filter(|&i| &hash_of(doc, i) == h).collect();
        match found.len() {
            1 => {
                *relocated += 1;
                return Ok(found[0]);
            }
            0 => {}
            _ => {
                return Err(Refusal::Ambiguous {
                    anchor: label,
                    candidates: found.iter().map(|i| i + 1).collect(),
                });
            }
        }
    }
    Err(Refusal::Stale {
        anchor: label,
        line: a.line,
    })
}

/// lines [start, end) of a range op, as 0-based half-open indices.
fn resolve_range(
    doc: &Doc,
    from: &Anchor,
    to: &Anchor,
    cfg: &Config,
    relocated: &mut usize,
) -> Result<(usize, usize), Refusal> {
    let a = resolve(doc, from, cfg, relocated)?;
    let b = if to == from {
        a
    } else {
        resolve(doc, to, cfg, relocated)?
    };
    if b < a {
        return Err(Refusal::Syntax(format!(
            "range {}..{} runs backwards",
            from.line, to.line
        )));
    }
    Ok((a, b + 1))
}

/// replace lines [start, end) with `new` (contents; terminators decided later).
#[derive(Debug, Clone)]
struct Splice {
    start: usize,
    end: usize,
    new: Vec<Vec<u8>>,
    order: usize,
}

fn to_splices(
    doc: &Doc,
    ops: &[Op],
    cfg: &Config,
    relocated: &mut usize,
) -> Result<Vec<Splice>, Refusal> {
    let mut out = Vec::new();
    for (order, op) in ops.iter().enumerate() {
        let s = match op {
            Op::Replace { from, to, body } => {
                let (start, end) = resolve_range(doc, from, to, cfg, relocated)?;
                Splice {
                    start,
                    end,
                    new: body.clone(),
                    order,
                }
            }
            Op::Delete { from, to } => {
                let (start, end) = resolve_range(doc, from, to, cfg, relocated)?;
                Splice {
                    start,
                    end,
                    new: Vec::new(),
                    order,
                }
            }
            Op::Insert { at, after, body } => {
                let i = resolve(doc, at, cfg, relocated)? + usize::from(*after);
                Splice {
                    start: i,
                    end: i,
                    new: body.clone(),
                    order,
                }
            }
            Op::FindWith { find, with } => find_splice(doc, find, with, order)?,
        };
        out.push(s);
    }
    out.sort_by_key(|s| (s.start, s.end, s.order));
    for w in out.windows(2) {
        let (p, q) = (&w[0], &w[1]);
        // touching is fine (replace 3-5 then insert at 6); sharing lines isn't,
        // and neither is an insert landing strictly inside a replaced range
        if q.start < p.end || (p.start == q.start && p.end > p.start && q.end > q.start) {
            return Err(Refusal::Overlap(format!(
                "ops {} and {} touch the same lines ({}-{} and {}-{}); merge them into one op",
                p.order + 1,
                q.order + 1,
                p.start + 1,
                p.end,
                q.start + 1,
                q.end
            )));
        }
    }
    Ok(out)
}

/// exact-text find over the file's lines joined with `\n` (so CRLF files work
/// with plain `\n` find text). turns the match into a splice of whole lines.
fn find_splice(doc: &Doc, find: &[u8], with: &[u8], order: usize) -> Result<Splice, Refusal> {
    let contents: Vec<&[u8]> = (0..doc.lines.len()).map(|i| doc.content(i)).collect();
    let mut joined = Vec::new();
    let mut starts = Vec::with_capacity(contents.len());
    for (i, c) in contents.iter().enumerate() {
        if i > 0 {
            joined.push(b'\n');
        }
        starts.push(joined.len());
        joined.extend_from_slice(c);
    }
    let line_of = |off: usize| starts.partition_point(|&st| st <= off) - 1;
    let end_of = |l: usize| starts[l] + contents[l].len();
    let hits: Vec<usize> = memchr::memmem::find_iter(&joined, find).collect();
    if hits.len() != 1 {
        let preview = String::from_utf8_lossy(&find[..find.len().min(60)]).into_owned();
        let want: Vec<&[u8]> = find.split(|&b| b == b'\n').collect();
        return Err(Refusal::FindCount {
            count: hits.len(),
            preview,
            lines: hits.iter().take(10).map(|&h| line_of(h) + 1).collect(),
            near: if hits.is_empty() {
                crate::nearmiss::candidates(&contents, &want, 5)
            } else {
                Vec::new()
            },
        });
    }
    let (s, e) = (hits[0], hits[0] + find.len());
    let first = line_of(s);
    // the line holding the match's end. if the match swallowed a line break,
    // the next line's content starts right at `e` and must be kept, so it
    // joins the splice too.
    let end_line = if joined[e - 1] == b'\n' {
        line_of(e)
    } else {
        line_of(e - 1)
    };
    let mut text = joined[starts[first]..s].to_vec();
    text.extend_from_slice(with);
    text.extend_from_slice(&joined[e..end_of(end_line)]);
    Ok(Splice {
        start: first,
        end: end_line + 1,
        new: text.split(|&b| b == b'\n').map(<[u8]>::to_vec).collect(),
        order,
    })
}

/// resolve + apply ops to `src`. pure: no disk, no parse guard.
pub fn apply(src: &[u8], ops: &[Op], cfg: &Config) -> Result<Applied, Refusal> {
    let doc = Doc::parse(src);
    let mut relocated = 0;
    let splices = to_splices(&doc, ops, cfg, &mut relocated)?;

    let mut out: Vec<(Vec<u8>, Vec<u8>)> = Vec::with_capacity(doc.lines.len());
    let mut regions = Vec::new();
    let (mut added, mut removed) = (0, 0);
    let mut cursor = 0;
    for s in &splices {
        out.extend(doc.lines[cursor..s.start].iter().cloned());
        let old: Vec<&Vec<u8>> = doc.lines[s.start..s.end].iter().map(|(c, _)| c).collect();
        // count +/- like a diff would: unchanged leading/trailing lines don't count
        let pre = old
            .iter()
            .zip(&s.new)
            .take_while(|(a, b)| a.as_slice() == b.as_slice())
            .count();
        let post = old[pre..]
            .iter()
            .rev()
            .zip(s.new[pre..].iter().rev())
            .take_while(|(a, b)| a.as_slice() == b.as_slice())
            .count();
        let (del, add) = (old.len() - pre - post, s.new.len() - pre - post);
        removed += del;
        added += add;
        if add + del > 0 {
            regions.push((out.len() + pre, add, del));
        }
        doc.push_replacement(&mut out, s.start, s.end, &s.new);
        cursor = s.end;
    }
    out.extend(doc.lines[cursor..].iter().cloned());
    Ok(Applied {
        bytes: doc.rebuild(out, doc.ends_with_newline()),
        added,
        removed,
        relocated,
        regions,
    })
}

/// the current lines around `line` with fresh anchors, for refusals.
pub fn around(cfg: &Config, src: &[u8], line: usize, radius: usize) -> Vec<String> {
    let lines = crate::text::lines(src);
    if lines.is_empty() {
        return vec!["  (file is empty)".into()];
    }
    let c = line.clamp(1, lines.len());
    let lo = c.saturating_sub(radius).max(1);
    let hi = (c + radius).min(lines.len());
    (lo..=hi)
        .map(|n| format!("  {}", anchored(cfg, n, lines[n - 1])))
        .collect()
}

fn refusal_report(ctx: &Ctx, rel: &str, src: &[u8], why: &Refusal) -> Report {
    let mut r = Report::new("edit");
    let (msg, show): (String, Vec<String>) = match why {
        Refusal::Syntax(m) | Refusal::Overlap(m) | Refusal::Parse(m) => (m.clone(), Vec::new()),
        Refusal::Stale { anchor, line } => (
            format!("stale anchor {anchor}: that line changed since you read it. current lines:"),
            around(&ctx.cfg, src, *line, 3),
        ),
        Refusal::Ambiguous { anchor, candidates } => (
            format!(
                "anchor {anchor} moved and now matches lines {}; use one of these anchors or @@ find:",
                candidates
                    .iter()
                    .map(|c| c.to_string())
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
            candidates
                .iter()
                .flat_map(|&c| around(&ctx.cfg, src, c, 0))
                .collect(),
        ),
        Refusal::FindCount {
            count: 0,
            preview,
            near,
            ..
        } if near.is_empty() => (
            format!(
                "find text not found: {preview:?}, not even loosely (ignoring whitespace and quotes). check it with ax grep."
            ),
            Vec::new(),
        ),
        Refusal::FindCount {
            count: 0,
            preview,
            near,
            ..
        } => (
            format!(
                "find text {preview:?} isn't in the file exactly. closest: {}. the real lines, to anchor with @@ replace or copy exactly:",
                near[0].why
            ),
            near.iter()
                .map(|c| {
                    (c.start + 1..=c.start + c.len)
                        .flat_map(|l| around(&ctx.cfg, src, l, 0))
                        .collect::<Vec<_>>()
                })
                .collect::<Vec<_>>()
                .join(&"  …".to_string()),
        ),
        Refusal::FindCount {
            count,
            preview,
            lines,
            ..
        } => (
            format!(
                "find text {preview:?} occurs {count} times; add surrounding lines to make it unique, or use one of these anchors:"
            ),
            lines
                .iter()
                .flat_map(|&l| around(&ctx.cfg, src, l, 0))
                .collect(),
        ),
    };
    r.lines.push(format!("{rel}: {msg}"));
    r.lines.extend(show);
    r.summary = Summary::plain(format!("nothing written ({}).", why.outcome()));
    r.failed = true;
    r.data = json!({ "path": rel, "outcome": why.outcome(), "error": msg });
    r
}

/// changed lines an edit echoes back before pointing at `ax read`.
const EDIT_SHOW: usize = 12;

/// the success echo: just the lines each op changed, with their new anchors,
/// no unchanged context. a pure delete gets a one-line marker. capped at
/// `cap` rows, then one line saying which range holds the rest.
fn changed_rows(
    cfg: &Config,
    rel: &str,
    new_lines: &[&[u8]],
    regions: &[(usize, usize, usize)],
    cap: usize,
    dry_run: bool,
) -> Vec<String> {
    // (1-based line the row is about, text)
    let mut rows: Vec<(usize, String)> = Vec::new();
    for &(start, add, del) in regions {
        if add == 0 {
            let at = if start < new_lines.len() {
                format!("above line {}", start + 1)
            } else {
                "at the end".to_string()
            };
            rows.push((
                (start + 1).min(new_lines.len().max(1)),
                format!("  (-{} {at})", text::plural(del, "line")),
            ));
            continue;
        }
        for (n, l) in new_lines.iter().enumerate().skip(start).take(add) {
            rows.push((n + 1, format!("  {}", anchored(cfg, n + 1, l))));
        }
    }
    if rows.len() <= cap {
        return rows.into_iter().map(|(_, r)| r).collect();
    }
    let rest = &rows[cap..];
    let (a, b) = (rest[0].0, rest[rest.len() - 1].0);
    let mut out: Vec<String> = rows[..cap].iter().map(|(_, r)| r.clone()).collect();
    out.push(if dry_run {
        // nothing on disk to read yet
        format!("  … {} more (lines {a}-{b})", rest.len())
    } else {
        format!("  … {} more; ax read {rel}:{a}-{b} to see", rest.len())
    });
    out
}

/// the agent writes UTF-8; a Windows-1252 file needs its text in 1252.
fn transcode(ops: Vec<Op>, enc: crate::enc::Enc) -> Result<Vec<Op>, Refusal> {
    let e = |b: &[u8]| enc.encode_owned(b).map_err(Refusal::Syntax);
    let lines = |v: Vec<Vec<u8>>| v.iter().map(|b| e(b)).collect::<Result<Vec<_>, _>>();
    ops.into_iter()
        .map(|op| {
            Ok(match op {
                Op::Replace { from, to, body } => Op::Replace {
                    from,
                    to,
                    body: lines(body)?,
                },
                Op::Insert { at, after, body } => Op::Insert {
                    at,
                    after,
                    body: lines(body)?,
                },
                Op::FindWith { find, with } => Op::FindWith {
                    find: e(&find)?,
                    with: e(&with)?,
                },
                d @ Op::Delete { .. } => d,
            })
        })
        .collect()
}

pub fn run(ctx: &Ctx, path: &str, input: &[u8], dry_run: bool) -> crate::Result<Report> {
    let abs = fsio::target(ctx, path)?;
    let rel = repo::rel(&ctx.root, &abs);
    if !abs.is_file() {
        return Err(crate::AxError(format!(
            "no such file {rel} (use `ax write` to create one)"
        )));
    }
    let src = std::fs::read(&abs)?;
    if text::is_binary(&src) {
        return Err(crate::AxError(format!(
            "{rel} looks binary; not editing it"
        )));
    }
    // (applied, op count, new lines ending in whitespace)
    let attempt = || -> Result<(Applied, usize, usize), Refusal> {
        let ops = parse_ops(input, &ctx.cfg)?;
        let new_text: Vec<&[u8]> = ops
            .iter()
            .flat_map(|op| -> Vec<&[u8]> {
                match op {
                    Op::Replace { body, .. } | Op::Insert { body, .. } => {
                        body.iter().map(Vec::as_slice).collect()
                    }
                    Op::FindWith { with, .. } => with.split(|&b| b == b'\n').collect(),
                    Op::Delete { .. } => Vec::new(),
                }
            })
            .collect();
        if text::looks_anchored(&new_text) {
            return Err(Refusal::Syntax(
                "the new lines start with LINE:HASH anchors copied from ax output; send just the code, without the `12:a3f1  ` prefix".into(),
            ));
        }
        let ws = text::trailing_ws(&new_text);
        let ops = transcode(ops, crate::enc::Enc::detect(&src))?;
        let applied = apply(&src, &ops, &ctx.cfg)?;
        if ctx.cfg.parse_check {
            crate::syntax::guard(&rel, Some(&src), &applied.bytes).map_err(Refusal::Parse)?;
        }
        Ok((applied, ops.len(), ws))
    };
    let (applied, n_ops, ws) = match attempt() {
        Ok(a) => a,
        Err(e) => return Ok(refusal_report(ctx, &rel, &src, &e)),
    };
    if applied.bytes != src && !dry_run {
        fsio::atomic_write(&abs, &applied.bytes)?;
    }

    let new_lines = text::lines(&applied.bytes);
    let mut r = Report::new("edit");
    r.lines.push(format!(
        "{rel}: +{} -{} ({}{})",
        applied.added,
        applied.removed,
        text::plural(n_ops, "op"),
        if applied.relocated > 0 {
            format!(", {} relocated", applied.relocated)
        } else {
            String::new()
        }
    ));
    let cap = if ctx.cfg.caps { EDIT_SHOW } else { usize::MAX };
    r.lines.extend(changed_rows(
        &ctx.cfg,
        &rel,
        &new_lines,
        &applied.regions,
        cap,
        dry_run,
    ));
    let new_hash = hash::file_hash(&applied.bytes);
    let mut summary = if applied.bytes == src {
        "no change (the ops produced the same bytes).".to_string()
    } else if dry_run {
        format!(
            "dry run: nothing written. {rel} would be {} (hash {new_hash}).",
            text::lines_label(new_lines.len()),
        )
    } else {
        format!(
            "wrote {rel} ({}, hash {new_hash}). anchors above are fresh.",
            text::lines_label(new_lines.len()),
        )
    };
    if ws > 0 {
        summary.push_str(&format!(" note: {ws} new line(s) end in whitespace."));
    }
    r.summary = Summary::plain(summary);
    r.data = json!({
        "path": rel,
        "outcome": if applied.relocated > 0 { "relocated" } else { "ok" },
        "added": applied.added,
        "removed": applied.removed,
        "relocated": applied.relocated,
        "hash": new_hash,
        "dry_run": dry_run,
    });
    Ok(r)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cfg() -> Config {
        Config::default()
    }

    fn a(src: &str, n: usize) -> String {
        let l = src.split_inclusive('\n').nth(n - 1).unwrap();
        format!("{n}:{}", line_hash(l.as_bytes()))
    }

    fn run(src: &str, script: &str) -> Result<String, Refusal> {
        let ops = parse_ops(script.as_bytes(), &cfg())?;
        apply(src.as_bytes(), &ops, &cfg()).map(|r| String::from_utf8(r.bytes).unwrap())
    }

    const SRC: &str = "one\ntwo\nthree\nfour\nfive\n";

    #[test]
    fn replace_insert_delete() {
        let s = format!("@@ replace {}\nTWO\n", a(SRC, 2));
        assert_eq!(run(SRC, &s).unwrap(), "one\nTWO\nthree\nfour\nfive\n");
        let s = format!("@@ replace {}..{}\nX\n", a(SRC, 2), a(SRC, 4));
        assert_eq!(run(SRC, &s).unwrap(), "one\nX\nfive\n");
        let s = format!("@@ insert after {}\nnew\n", a(SRC, 5));
        assert_eq!(run(SRC, &s).unwrap(), "one\ntwo\nthree\nfour\nfive\nnew\n");
        let s = format!("@@ insert before {}\n0\n", a(SRC, 1));
        assert_eq!(run(SRC, &s).unwrap(), "0\none\ntwo\nthree\nfour\nfive\n");
        let s = format!("@@ delete {}..{}\n", a(SRC, 1), a(SRC, 2));
        assert_eq!(run(SRC, &s).unwrap(), "three\nfour\nfive\n");
        // replace with nothing = delete
        let s = format!("@@ replace {}\n", a(SRC, 3));
        assert_eq!(run(SRC, &s).unwrap(), "one\ntwo\nfour\nfive\n");
    }

    #[test]
    fn many_ops_use_original_numbering() {
        let s = format!(
            "@@ delete {}\n@@ replace {}\nFOUR\n@@ insert after {}\nzero-and-a-half\n",
            a(SRC, 2),
            a(SRC, 4),
            a(SRC, 1)
        );
        assert_eq!(
            run(SRC, &s).unwrap(),
            "one\nzero-and-a-half\nthree\nFOUR\nfive\n"
        );
    }

    #[test]
    fn overlap_is_refused() {
        let s = format!(
            "@@ replace {}..{}\nX\n@@ delete {}\n",
            a(SRC, 2),
            a(SRC, 3),
            a(SRC, 3)
        );
        assert!(matches!(run(SRC, &s), Err(Refusal::Overlap(_))));
        // insert inside a replaced range
        let s = format!(
            "@@ replace {}..{}\nX\n@@ insert after {}\nY\n",
            a(SRC, 2),
            a(SRC, 4),
            a(SRC, 2)
        );
        assert!(matches!(run(SRC, &s), Err(Refusal::Overlap(_))));
        // touching is fine
        let s = format!(
            "@@ replace {}\nX\n@@ insert after {}\nY\n",
            a(SRC, 2),
            a(SRC, 2)
        );
        assert_eq!(run(SRC, &s).unwrap(), "one\nX\nY\nthree\nfour\nfive\n");
    }

    #[test]
    fn stale_moved_and_ambiguous() {
        // content changed: stale
        let s = "@@ replace 2:0000\nX\n";
        assert!(matches!(run(SRC, s), Err(Refusal::Stale { line: 2, .. })));
        // moved by 2 lines: relocated
        let moved = format!("a\nb\n{SRC}");
        let s = format!("@@ replace {}\nTWO\n", a(SRC, 2));
        let ops = parse_ops(s.as_bytes(), &cfg()).unwrap();
        let r = apply(moved.as_bytes(), &ops, &cfg()).unwrap();
        assert_eq!(r.relocated, 1);
        assert_eq!(
            String::from_utf8(r.bytes).unwrap(),
            "a\nb\none\nTWO\nthree\nfour\nfive\n"
        );
        // moved but relocation off: stale
        let off = Config {
            relocate: false,
            ..cfg()
        };
        assert!(matches!(
            apply(moved.as_bytes(), &ops, &off),
            Err(Refusal::Stale { .. })
        ));
        // two candidates nearby: ambiguous
        let dup = "x\ntwo\ny\ntwo\nz\n";
        let s = format!("@@ replace 1:{}\nX\n", line_hash(b"two"));
        assert!(matches!(run(dup, &s), Err(Refusal::Ambiguous { .. })));
        // way out of the window: stale
        let far = format!("{}{SRC}", "pad\n".repeat(50));
        assert!(matches!(
            apply(far.as_bytes(), &ops, &cfg()),
            Err(Refusal::Stale { .. })
        ));
    }

    #[test]
    fn find_with() {
        let s = "@@ find\nthree\n@@ with\n3\n";
        assert_eq!(run(SRC, s).unwrap(), "one\ntwo\n3\nfour\nfive\n");
        // partial line
        let s = "@@ find\nhre\n@@ with\nHRE\n";
        assert_eq!(run(SRC, s).unwrap(), "one\ntwo\ntHREe\nfour\nfive\n");
        // multi-line across lines
        let s = "@@ find\nwo\nthr\n@@ with\nWO-THR\n";
        assert_eq!(run(SRC, s).unwrap(), "one\ntWO-THRee\nfour\nfive\n");
        // must be unique
        let s = "@@ find\no\n@@ with\n0\n";
        assert!(matches!(
            run(SRC, s),
            Err(Refusal::FindCount { count: 3, .. })
        ));
        let s = "@@ find\nnope\n@@ with\nx\n";
        assert!(matches!(
            run(SRC, s),
            Err(Refusal::FindCount { count: 0, .. })
        ));
        // with can add lines
        let s = "@@ find\nfive\n@@ with\nfive\nsix\n";
        assert_eq!(run(SRC, s).unwrap(), "one\ntwo\nthree\nfour\nfive\nsix\n");
        // with can be empty (deletes the text, line stays)
        let s = "@@ find\nfour\n@@ with\n";
        assert_eq!(run(SRC, s).unwrap(), "one\ntwo\nthree\n\nfive\n");
    }

    #[test]
    fn line_endings_bom_and_final_newline_survive() {
        let crlf = "a\r\nb\r\nc\r\n";
        let s = format!("@@ replace {}\nB\nB2\n", a(crlf, 2));
        assert_eq!(run(crlf, &s).unwrap(), "a\r\nB\r\nB2\r\nc\r\n");
        let s = "@@ find\nb\n@@ with\nbb\n";
        assert_eq!(run(crlf, s).unwrap(), "a\r\nbb\r\nc\r\n");

        let no_nl = "a\nb";
        let s = format!("@@ insert after {}\nc\n", a(no_nl, 2));
        assert_eq!(run(no_nl, &s).unwrap(), "a\nb\nc");
        let s = format!("@@ delete {}\n", a(no_nl, 2));
        assert_eq!(run(no_nl, &s).unwrap(), "a");

        let bom = "\u{feff}first\nsecond\n";
        let s = format!("@@ replace {}\nFIRST\n", a(bom, 1));
        assert_eq!(run(bom, &s).unwrap(), "\u{feff}FIRST\nsecond\n");

        let tabs = "\tx\n\t\ty\n";
        let s = format!("@@ replace {}\n\t\tY\n", a(tabs, 2));
        assert_eq!(run(tabs, &s).unwrap(), "\tx\n\t\tY\n");
    }

    #[test]
    fn counts_and_regions() {
        let s = format!("@@ replace {}..{}\ntwo\nTHREE\n", a(SRC, 2), a(SRC, 3));
        let ops = parse_ops(s.as_bytes(), &cfg()).unwrap();
        let r = apply(SRC.as_bytes(), &ops, &cfg()).unwrap();
        assert_eq!((r.added, r.removed), (1, 1));
        assert_eq!(r.regions, vec![(2, 1, 1)]);
    }

    #[test]
    fn syntax_errors() {
        let e = |s: &str| matches!(parse_ops(s.as_bytes(), &cfg()), Err(Refusal::Syntax(_)));
        assert!(e(""));
        assert!(e("hello\n"));
        assert!(e("@@ replace 2\nx\n")); // no hash
        assert!(e("@@ replace 2:zz\nx\n"));
        assert!(e("@@ insert 2:abcd\nx\n"));
        assert!(e("@@ frob 2:abcd\n"));
        assert!(e("@@ find\nx\n"));
        assert!(e("@@ with\nx\n"));
        assert!(e("@@ delete 1:abcd\nbody\n"));
        // hashless anchors are fine when anchors are off (ablation)
        let off = Config {
            anchors: false,
            ..cfg()
        };
        assert!(parse_ops(b"@@ replace 2\nx\n", &off).is_ok());
    }

    #[test]
    fn escaped_header_lines_in_body() {
        let s = format!("@@ replace {}\n\\@@ not a header\n", a(SRC, 1));
        assert_eq!(
            run(SRC, &s).unwrap(),
            "@@ not a header\ntwo\nthree\nfour\nfive\n"
        );
    }
}
