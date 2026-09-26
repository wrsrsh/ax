//! `ax patch`: Codex `*** Begin Patch` or unified diff on stdin, many files,
//! all-or-nothing. Context must match exactly; a unified hunk that doesn't
//! match at its stated line is looked for elsewhere (nearest match wins), the
//! way `git apply` does without fuzz.

use crate::edit::Doc;
use crate::output::{Report, Summary, anchored};
use crate::{AxError, Ctx, Result, fsio, hash, repo, text};
use serde_json::json;
use std::path::PathBuf;

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Hunk {
    pub old: Vec<Vec<u8>>,
    pub new: Vec<Vec<u8>>,
    /// 1-based old start line (unified diffs)
    pub hint: Option<usize>,
    /// `@@ def foo` in Codex patches: seek past a line containing this first
    pub seek: Option<Vec<u8>>,
    pub context: usize,
    pub old_no_eol: bool,
    pub new_no_eol: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FilePatch {
    Add {
        path: String,
        lines: Vec<Vec<u8>>,
        no_eol: bool,
    },
    Delete {
        path: String,
    },
    Update {
        path: String,
        move_to: Option<String>,
        hunks: Vec<Hunk>,
    },
}

fn perr(msg: impl Into<String>) -> AxError {
    AxError(format!("bad patch: {}", msg.into()))
}

pub fn parse(input: &[u8]) -> Result<Vec<FilePatch>> {
    let text = String::from_utf8_lossy(input).replace("\r\n", "\n");
    let lines: Vec<&str> = text.lines().collect();
    if lines.iter().any(|l| l.trim() == "*** Begin Patch") {
        parse_codex(&lines)
    } else if lines
        .iter()
        .any(|l| l.starts_with("--- ") || l.starts_with("diff --git "))
    {
        parse_unified(&lines)
    } else {
        Err(perr(
            "expected `*** Begin Patch` or a unified diff (`--- a/x` / `+++ b/x`)",
        ))
    }
}

fn parse_codex(lines: &[&str]) -> Result<Vec<FilePatch>> {
    let start = lines
        .iter()
        .position(|l| l.trim() == "*** Begin Patch")
        .unwrap()
        + 1;
    let mut out = Vec::new();
    let mut i = start;
    while i < lines.len() {
        let l = lines[i];
        if l.trim() == "*** End Patch" {
            return Ok(out);
        }
        if let Some(p) = l.strip_prefix("*** Add File: ") {
            i += 1;
            let mut body = Vec::new();
            while i < lines.len() && !lines[i].starts_with("*** ") {
                let b = lines[i].strip_prefix('+').ok_or_else(|| {
                    perr(format!(
                        "added file line must start with '+': {:?}",
                        lines[i]
                    ))
                })?;
                body.push(b.as_bytes().to_vec());
                i += 1;
            }
            out.push(FilePatch::Add {
                path: p.trim().into(),
                lines: body,
                no_eol: false,
            });
        } else if let Some(p) = l.strip_prefix("*** Delete File: ") {
            out.push(FilePatch::Delete {
                path: p.trim().into(),
            });
            i += 1;
        } else if let Some(p) = l.strip_prefix("*** Update File: ") {
            i += 1;
            let mut move_to = None;
            if let Some(m) = lines.get(i).and_then(|l| l.strip_prefix("*** Move to: ")) {
                move_to = Some(m.trim().to_string());
                i += 1;
            }
            let mut hunks: Vec<Hunk> = Vec::new();
            let mut cur = Hunk::default();
            let flush = |cur: &mut Hunk, hunks: &mut Vec<Hunk>| {
                if !cur.old.is_empty() || !cur.new.is_empty() {
                    hunks.push(std::mem::take(cur));
                }
            };
            while i < lines.len()
                && !(lines[i].starts_with("*** ") && lines[i] != "*** End of File")
            {
                let l = lines[i];
                if l == "*** End of File" {
                    i += 1;
                    continue;
                }
                if let Some(rest) = l.strip_prefix("@@") {
                    flush(&mut cur, &mut hunks);
                    let s = rest.trim();
                    cur.seek = (!s.is_empty()).then(|| s.as_bytes().to_vec());
                } else if let Some(t) = l.strip_prefix('+') {
                    cur.new.push(t.as_bytes().to_vec());
                } else if let Some(t) = l.strip_prefix('-') {
                    cur.old.push(t.as_bytes().to_vec());
                } else {
                    let t = l.strip_prefix(' ').unwrap_or(l);
                    cur.old.push(t.as_bytes().to_vec());
                    cur.new.push(t.as_bytes().to_vec());
                    cur.context += 1;
                }
                i += 1;
            }
            flush(&mut cur, &mut hunks);
            if hunks.is_empty() && move_to.is_none() {
                return Err(perr(format!("`*** Update File: {p}` has no changes")));
            }
            out.push(FilePatch::Update {
                path: p.trim().into(),
                move_to,
                hunks,
            });
        } else if l.trim().is_empty() {
            i += 1;
        } else {
            return Err(perr(format!("unexpected line {l:?}")));
        }
    }
    Err(perr("missing `*** End Patch`"))
}

fn strip_ab(p: &str) -> Option<String> {
    let p = p.split('\t').next().unwrap_or(p).trim();
    if p == "/dev/null" {
        return None;
    }
    Some(
        p.strip_prefix("a/")
            .or_else(|| p.strip_prefix("b/"))
            .unwrap_or(p)
            .to_string(),
    )
}

fn hunk_counts(h: &str) -> Option<(usize, usize, usize)> {
    let mut it = h.split_whitespace().skip(1);
    let range = |s: &str| -> Option<(usize, usize)> {
        let (a, b) = s.split_once(',').unwrap_or((s, "1"));
        Some((a.parse().ok()?, b.parse().ok()?))
    };
    let (os, oc) = range(it.next()?.strip_prefix('-')?)?;
    let (_, nc) = range(it.next()?.strip_prefix('+')?)?;
    Some((os, oc, nc))
}

fn parse_unified(lines: &[&str]) -> Result<Vec<FilePatch>> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < lines.len() {
        let (mut from, mut to, mut deleted) = (None, None, false);
        let git_header = lines[i].starts_with("diff --git ");
        if git_header {
            i += 1;
            while i < lines.len()
                && !lines[i].starts_with("diff --git ")
                && !lines[i].starts_with("--- ")
            {
                let l = lines[i];
                if let Some(r) = l.strip_prefix("rename from ") {
                    from = Some(r.trim().to_string());
                } else if let Some(r) = l.strip_prefix("rename to ") {
                    to = Some(r.trim().to_string());
                } else if l.starts_with("deleted file mode") {
                    deleted = true;
                }
                i += 1;
            }
        }
        let has_body =
            i + 1 < lines.len() && lines[i].starts_with("--- ") && lines[i + 1].starts_with("+++ ");
        if !has_body {
            if let (Some(f), Some(t)) = (from, to) {
                out.push(FilePatch::Update {
                    path: f,
                    move_to: Some(t),
                    hunks: vec![],
                });
            } else if !git_header {
                i += 1;
            }
            continue;
        }
        let old = strip_ab(&lines[i][4..]);
        let new = strip_ab(&lines[i + 1][4..]);
        i += 2;
        let mut hunks = Vec::new();
        while i < lines.len() && lines[i].starts_with("@@ ") {
            let (os, mut oc, mut nc) = hunk_counts(lines[i])
                .ok_or_else(|| perr(format!("bad hunk header {:?}", lines[i])))?;
            let mut hunk = Hunk {
                hint: Some(os),
                ..Default::default()
            };
            i += 1;
            let mut last = ' ';
            while i < lines.len() && (oc > 0 || nc > 0 || lines[i].starts_with("\\ ")) {
                let l = lines[i];
                if l.starts_with("\\ ") {
                    match last {
                        '-' => hunk.old_no_eol = true,
                        '+' => hunk.new_no_eol = true,
                        _ => {
                            hunk.old_no_eol = true;
                            hunk.new_no_eol = true;
                        }
                    }
                } else if let Some(t) = l.strip_prefix('+') {
                    hunk.new.push(t.as_bytes().to_vec());
                    nc = nc.saturating_sub(1);
                    last = '+';
                } else if let Some(t) = l.strip_prefix('-') {
                    hunk.old.push(t.as_bytes().to_vec());
                    oc = oc.saturating_sub(1);
                    last = '-';
                } else {
                    let t = l.strip_prefix(' ').unwrap_or(l);
                    hunk.old.push(t.as_bytes().to_vec());
                    hunk.new.push(t.as_bytes().to_vec());
                    hunk.context += 1;
                    oc = oc.saturating_sub(1);
                    nc = nc.saturating_sub(1);
                    last = ' ';
                }
                i += 1;
            }
            hunks.push(hunk);
        }
        match (old, new) {
            (None, Some(p)) => {
                let h = hunks.into_iter().next().unwrap_or_default();
                out.push(FilePatch::Add {
                    path: p,
                    lines: h.new,
                    no_eol: h.new_no_eol,
                });
            }
            (Some(p), None) => out.push(FilePatch::Delete { path: p }),
            (Some(p), Some(_)) if deleted => out.push(FilePatch::Delete { path: p }),
            (Some(p), Some(q)) => {
                let move_to = to.or((p != q).then_some(q));
                out.push(FilePatch::Update {
                    path: from.unwrap_or(p),
                    move_to,
                    hunks,
                });
            }
            (None, None) => return Err(perr("diff from /dev/null to /dev/null")),
        }
    }
    if out.is_empty() {
        return Err(perr("no file changes found"));
    }
    Ok(out)
}

fn content(doc: &Doc, i: usize) -> &[u8] {
    let c = &doc.lines[i].0;
    if i == 0 {
        c.strip_prefix(b"\xEF\xBB\xBF").unwrap_or(c)
    } else {
        c
    }
}

/// where `hunk.old` sits in `doc`, searching from `from`. a BOM is invisible.
fn locate(doc: &Doc, hunk: &Hunk, from: usize) -> Option<usize> {
    let n = doc.lines.len();
    let k = hunk.old.len();
    let at = |i: usize| i + k <= n && (0..k).all(|j| content(doc, i + j) == hunk.old[j].as_slice());
    let mut start = from;
    if let Some(s) = &hunk.seek {
        let found = (from..n).find(|&i| memchr::memmem::find(content(doc, i), s).is_some())?;
        start = found + 1;
        if k == 0 {
            return Some(start);
        }
    }
    if k == 0 {
        // unified `@@ -h,0` inserts after line h (h = 0: at the top)
        return Some(hunk.hint.map_or(n, |h| h.min(n)).max(start));
    }
    if let Some(h) = hunk.hint {
        let h = h.saturating_sub(1);
        if h >= start && at(h) {
            return Some(h);
        }
        return (start..=n.saturating_sub(k))
            .filter(|&i| at(i))
            .min_by_key(|&i| i.abs_diff(h));
    }
    (start..=n.saturating_sub(k)).find(|&i| at(i))
}

struct Patched {
    bytes: Vec<u8>,
    added: usize,
    removed: usize,
    regions: Vec<(usize, usize)>,
}

fn apply_hunks(ctx: &Ctx, rel: &str, src: &[u8], hunks: &[Hunk]) -> Result<Patched> {
    let enc = crate::enc::Enc::detect(src);
    let conv = |b: &[u8]| {
        enc.encode(b).map(|c| c.into_owned()).map_err(|c| {
            AxError(format!(
                "{rel}: {c:?} can't go in this file: it's {} and has no byte for that character",
                enc.label()
            ))
        })
    };
    let hunks: Vec<Hunk> = hunks
        .iter()
        .map(|h| {
            Ok(Hunk {
                old: h.old.iter().map(|l| conv(l)).collect::<Result<_>>()?,
                new: h.new.iter().map(|l| conv(l)).collect::<Result<_>>()?,
                seek: h.seek.as_deref().map(conv).transpose()?,
                ..h.clone()
            })
        })
        .collect::<Result<_>>()?;
    let hunks = hunks.as_slice();
    let doc = Doc::parse(src);
    let had_nl = doc.ends_with_newline();
    let mut out: Vec<(Vec<u8>, Vec<u8>)> = Vec::new();
    let mut regions = Vec::new();
    let (mut added, mut removed) = (0, 0);
    let mut cursor = 0;
    let mut ends_no_eol = None;
    for (hi, h) in hunks.iter().enumerate() {
        let Some(at) = locate(&doc, h, cursor) else {
            let near = h.hint.unwrap_or(cursor + 1);
            let mut msg = format!(
                "{rel}: hunk {} of {} doesn't match the file. expected:\n",
                hi + 1,
                hunks.len()
            );
            for o in h.old.iter().take(8) {
                msg.push_str(&format!("  {}\n", crate::enc::show(o)));
            }
            let contents: Vec<&[u8]> = (0..doc.lines.len()).map(|i| content(&doc, i)).collect();
            let want: Vec<&[u8]> = h.old.iter().map(Vec::as_slice).collect();
            let close = crate::nearmiss::candidates(&contents, &want, 3);
            if let Some(c) = close.first() {
                msg.push_str(&format!("closest: {}. the real lines:\n", c.why));
                for c in &close {
                    for l in c.start + 1..=c.start + c.len {
                        msg.push_str(&crate::edit::around(&ctx.cfg, src, l, 0).join("\n"));
                        msg.push('\n');
                    }
                }
            } else {
                msg.push_str("nothing close either. current lines there:\n");
                msg.push_str(&crate::edit::around(&ctx.cfg, src, near, 4).join("\n"));
            }
            return Err(AxError(msg.trim_end().to_string()));
        };
        out.extend(doc.lines[cursor..at].iter().cloned());
        regions.push((out.len(), h.new.len()));
        for (i, c) in h.new.iter().enumerate() {
            let term = doc
                .lines
                .get(at + i)
                .filter(|_| i < h.old.len())
                .map(|(_, t)| t.clone())
                .unwrap_or_else(|| doc.eol.clone());
            out.push((c.clone(), term));
        }
        added += h.new.len() - h.context;
        removed += h.old.len() - h.context;
        cursor = at + h.old.len();
        if cursor == doc.lines.len() && (h.new_no_eol || h.old_no_eol) {
            ends_no_eol = Some(h.new_no_eol);
        }
    }
    out.extend(doc.lines[cursor..].iter().cloned());
    let keep_nl = match ends_no_eol {
        Some(no) => !no,
        None => had_nl,
    };
    let n = out.len();
    for (i, (_, t)) in out.iter_mut().enumerate() {
        if i + 1 < n || keep_nl {
            if t.is_empty() {
                *t = doc.eol.clone();
            }
        } else {
            t.clear();
        }
    }
    let bytes = Doc {
        lines: out,
        eol: doc.eol.clone(),
        bom: doc.bom,
    }
    .render();
    Ok(Patched {
        bytes,
        added,
        removed,
        regions,
    })
}

pub fn run(ctx: &Ctx, input: &[u8], dry_run: bool) -> Result<Report> {
    let patches = parse(input)?;
    let added: Vec<&[u8]> = patches
        .iter()
        .flat_map(|p| match p {
            FilePatch::Add { lines, .. } => lines.iter().map(Vec::as_slice).collect::<Vec<_>>(),
            FilePatch::Update { hunks, .. } => hunks
                .iter()
                .flat_map(|h| {
                    h.new
                        .iter()
                        .filter(|l| !h.old.contains(l))
                        .map(Vec::as_slice)
                })
                .collect(),
            FilePatch::Delete { .. } => Vec::new(),
        })
        .collect();
    if text::looks_anchored(&added) {
        return Err(AxError(
            "the added lines start with LINE:HASH anchors copied from ax output; send just the code, without the `12:a3f1  ` prefix. nothing written.".into(),
        ));
    }
    let resolve = |p: &str| -> Result<(PathBuf, String)> {
        let abs = fsio::target(ctx, p)?;
        let rel = repo::rel(&ctx.root, &abs);
        Ok((abs, rel))
    };
    let mut writes: Vec<(PathBuf, Option<Vec<u8>>)> = Vec::new();
    let mut lines = Vec::new();
    let mut shown = Vec::new();
    let (mut plus, mut minus) = (0, 0);
    for fp in &patches {
        match fp {
            FilePatch::Add {
                path,
                lines: body,
                no_eol,
            } => {
                let (abs, rel) = resolve(path)?;
                if abs.exists() {
                    return Err(AxError(format!(
                        "{rel} already exists; use an Update, not Add"
                    )));
                }
                let mut b = body.join(&b"\n"[..]);
                if !body.is_empty() && !no_eol {
                    b.push(b'\n');
                }
                plus += body.len();
                lines.push(format!("A {rel}  +{}", body.len()));
                writes.push((abs, Some(b)));
            }
            FilePatch::Delete { path } => {
                let (abs, rel) = resolve(path)?;
                let old = std::fs::read(&abs)
                    .map_err(|_| AxError(format!("can't delete {rel}: no such file")))?;
                let n = text::line_count(&old);
                minus += n;
                lines.push(format!("D {rel}  -{n}"));
                writes.push((abs, None));
            }
            FilePatch::Update {
                path,
                move_to,
                hunks,
            } => {
                let (abs, rel) = resolve(path)?;
                let src = std::fs::read(&abs)
                    .map_err(|_| AxError(format!("can't update {rel}: no such file")))?;
                if text::is_binary(&src) {
                    return Err(AxError(format!("{rel} looks binary; not patching it")));
                }
                let Patched {
                    bytes,
                    added: a,
                    removed: r,
                    regions,
                } = apply_hunks(ctx, &rel, &src, hunks)?;
                plus += a;
                minus += r;
                match move_to {
                    Some(to) => {
                        let (dst, drel) = resolve(to)?;
                        if dst.exists() && dst != abs {
                            return Err(AxError(format!(
                                "can't move {rel} to {drel}: it already exists"
                            )));
                        }
                        lines.push(format!("R {rel} -> {drel}  +{a} -{r}"));
                        writes.push((abs, None));
                        shown.push((drel, bytes.clone(), regions));
                        writes.push((dst, Some(bytes)));
                    }
                    None => {
                        lines.push(format!("M {rel}  +{a} -{r}"));
                        shown.push((rel, bytes.clone(), regions));
                        writes.push((abs, Some(bytes)));
                    }
                }
            }
        }
    }
    if ctx.cfg.parse_check {
        for (abs, new) in &writes {
            let Some(new) = new else { continue };
            let rel = repo::rel(&ctx.root, abs);
            let old = std::fs::read(abs).ok();
            crate::syntax::guard(&rel, old.as_deref(), new).map_err(|m| {
                AxError(format!(
                    "{m}\nnothing written. AX_NO_PARSE_CHECK=1 skips this check."
                ))
            })?;
        }
    }
    if !dry_run {
        fsio::atomic_write_all(&writes)?;
    }

    let mut r = Report::new("patch");
    r.lines = lines;
    let mut budget = ctx.cfg.read_window;
    for (rel, bytes, regions) in &shown {
        if budget == 0 {
            break;
        }
        let ls = text::lines(bytes);
        r.lines
            .push(format!("{rel}  (hash {})", hash::file_hash(bytes)));
        for &(start, len) in regions {
            let lo = start.saturating_sub(1);
            let hi = (start + len.max(1) + 1).min(ls.len());
            for (n, l) in ls.iter().enumerate().take(hi).skip(lo) {
                if budget == 0 {
                    break;
                }
                r.lines.push(format!("  {}", anchored(&ctx.cfg, n + 1, l)));
                budget -= 1;
            }
            r.lines.push("  …".into());
        }
        r.lines.pop();
    }
    let mut summary = format!(
        "{} {} (+{plus} -{minus}).",
        if dry_run {
            "dry run, nothing written. would patch"
        } else {
            "patched"
        },
        text::plural(patches.len(), "file")
    );
    let ws = text::trailing_ws(&added);
    if ws > 0 {
        summary.push_str(&format!(" note: {ws} added line(s) end in whitespace."));
    }
    r.summary = Summary::plain(summary);
    r.data = json!({
        "files": patches.len(),
        "added": plus,
        "removed": minus,
        "changes": r.lines.iter().take(patches.len()).collect::<Vec<_>>(),
    });
    Ok(r)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codex_format() {
        let p = b"*** Begin Patch\n*** Add File: a.txt\n+hi\n*** Update File: b.ts\n@@ function f\n-  return 1\n+  return 2\n*** Delete File: c.ts\n*** End Patch\n";
        let v = parse(p).unwrap();
        assert_eq!(v.len(), 3);
        assert!(matches!(&v[0], FilePatch::Add { path, .. } if path == "a.txt"));
        match &v[1] {
            FilePatch::Update { hunks, .. } => {
                assert_eq!(hunks[0].seek.as_deref(), Some(&b"function f"[..]));
                assert_eq!(hunks[0].old, vec![b"  return 1".to_vec()]);
            }
            _ => panic!(),
        }
        assert!(matches!(&v[2], FilePatch::Delete { .. }));
    }

    #[test]
    fn unified_format() {
        let p = b"diff --git a/x.ts b/x.ts\nindex 1..2 100644\n--- a/x.ts\n+++ b/x.ts\n@@ -2,3 +2,3 @@\n a\n-b\n+B\n c\n--- /dev/null\n+++ b/new.ts\n@@ -0,0 +1 @@\n+n\n\\ No newline at end of file\n";
        let v = parse(p).unwrap();
        assert_eq!(v.len(), 2);
        match &v[0] {
            FilePatch::Update { path, hunks, .. } => {
                assert_eq!(path, "x.ts");
                assert_eq!(hunks[0].hint, Some(2));
                assert_eq!(hunks[0].old.len(), 3);
            }
            _ => panic!(),
        }
        assert!(matches!(&v[1], FilePatch::Add { no_eol: true, .. }));
    }

    #[test]
    fn locate_prefers_hint_then_nearest() {
        let doc = Doc::parse(b"x\ny\nx\ny\nx\ny\n");
        let h = Hunk {
            old: vec![b"x".to_vec(), b"y".to_vec()],
            hint: Some(5),
            ..Default::default()
        };
        assert_eq!(locate(&doc, &h, 0), Some(4));
        let h = Hunk {
            old: vec![b"x".to_vec()],
            hint: Some(3),
            ..Default::default()
        };
        assert_eq!(locate(&doc, &h, 0), Some(2));
        let h = Hunk {
            old: vec![b"zzz".to_vec()],
            hint: Some(1),
            ..Default::default()
        };
        assert_eq!(locate(&doc, &h, 0), None);
    }

    #[test]
    fn garbage_is_rejected() {
        assert!(parse(b"hello").is_err());
        assert!(parse(b"*** Begin Patch\n*** Update File: a\n").is_err());
    }
}
