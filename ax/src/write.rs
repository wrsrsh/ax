//! `ax write <path> [--if <hash>]`: stdin becomes the file. `--if` takes the
//! file hash from `ax read` and refuses if the file changed since.

use crate::output::{Report, Summary};
use crate::{AxError, Ctx, Result, fsio, hash, repo, text};
use serde_json::json;

pub struct WriteOpts<'a> {
    pub if_hash: Option<&'a str>,
    pub force: bool,
    pub dry_run: bool,
}

pub fn run(ctx: &Ctx, path: &str, opts: &WriteOpts, input: &[u8]) -> Result<Report> {
    let if_hash = opts.if_hash;
    let abs = fsio::target(ctx, path)?;
    let rel = repo::rel(&ctx.root, &abs);
    if abs.is_dir() {
        return Err(AxError(format!("{rel} is a directory")));
    }
    let old = std::fs::read(&abs).ok();
    let mut r = Report::new("write");
    let refuse = |r: &mut Report, msg: String, outcome: &str| {
        r.lines.push(msg);
        r.summary = Summary::plain(format!("nothing written ({outcome})."));
        r.failed = true;
        r.data = json!({"path": rel, "outcome": outcome});
    };
    if old.is_some() && if_hash.is_none() && !opts.force {
        refuse(
            &mut r,
            format!(
                "{rel} already exists. read it first and pass `--if <hash>` from the header, or --force to overwrite it blind."
            ),
            "error",
        );
        return Ok(r);
    }
    let enc = old
        .as_deref()
        .map(crate::enc::Enc::detect)
        .unwrap_or(crate::enc::Enc::Utf8);
    let encoded = match enc.encode(input) {
        Ok(b) => b,
        Err(c) => {
            refuse(
                &mut r,
                format!(
                    "{c:?} can't go in {rel}: it's {} and has no byte for that character",
                    enc.label()
                ),
                "error",
            );
            return Ok(r);
        }
    };
    let input: &[u8] = &encoded;
    let lines = crate::text::lines(input);
    if crate::text::looks_anchored(&lines) {
        refuse(
            &mut r,
            "the content starts with LINE:HASH anchors copied from ax output; send just the code, without the `12:a3f1  ` prefix".into(),
            "error",
        );
        return Ok(r);
    }
    if let Some(want) = if_hash {
        let have = old.as_deref().map(hash::file_hash);
        if have.as_deref() != Some(want) {
            let why = match &have {
                None => format!("{rel} doesn't exist, so it can't match --if {want}"),
                Some(h) => format!(
                    "{rel} changed since you read it (hash is {h}, --if said {want}); read it again"
                ),
            };
            r.lines.push(why);
            r.summary = Summary::plain("nothing written (stale).");
            r.failed = true;
            r.data = json!({"path": rel, "outcome": "stale"});
            return Ok(r);
        }
    }
    if ctx.cfg.parse_check
        && let Err(m) = crate::syntax::guard(&rel, old.as_deref(), input)
    {
        r.lines.push(m);
        r.summary = Summary::plain(
            "nothing written (parse-rejected). AX_NO_PARSE_CHECK=1 skips this check.",
        );
        r.failed = true;
        r.data = json!({"path": rel, "outcome": "parse-rejected"});
        return Ok(r);
    }
    if !opts.dry_run {
        fsio::atomic_write(&abs, input)?;
    }
    let n = text::line_count(input);
    let what = match &old {
        None => "created".to_string(),
        Some(o) => {
            let d = crate::edit::Doc::parse(o).lines.len();
            format!(
                "replaced ({} → {})",
                text::lines_label(d),
                text::lines_label(n)
            )
        }
    };
    let mut summary = format!(
        "{} {rel}: {what}, hash {}.",
        if opts.dry_run {
            "dry run, nothing written. would write"
        } else {
            "wrote"
        },
        hash::file_hash(input)
    );
    let old_lines: std::collections::HashSet<&[u8]> = old
        .as_deref()
        .map(|o| {
            crate::text::lines(o)
                .into_iter()
                .map(crate::hash::strip_eol)
                .collect()
        })
        .unwrap_or_default();
    let fresh: Vec<&[u8]> = lines
        .iter()
        .map(|l| crate::hash::strip_eol(l))
        .filter(|l| !old_lines.contains(l))
        .collect();
    let ws = crate::text::trailing_ws(&fresh);
    if ws > 0 {
        summary.push_str(&format!(" note: {ws} new line(s) end in whitespace."));
    }
    if !input.is_empty() && !input.ends_with(b"\n") {
        summary.push_str(" note: no newline at end of file.");
    }
    r.summary = Summary::plain(summary);
    r.data = json!({
        "path": rel,
        "outcome": "ok",
        "created": old.is_none(),
        "lines": n,
        "hash": hash::file_hash(input),
        "dry_run": opts.dry_run,
    });
    Ok(r)
}
