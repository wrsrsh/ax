//! `ax write <path> [--if <hash>]`: stdin becomes the file. `--if` takes the
//! file hash from `ax read` and refuses if the file changed since.

use crate::output::{Report, Summary};
use crate::{AxError, Ctx, Result, fsio, hash, repo, text};
use serde_json::json;

pub fn run(ctx: &Ctx, path: &str, if_hash: Option<&str>, input: &[u8]) -> Result<Report> {
    let abs = fsio::target(ctx, path)?;
    let rel = repo::rel(&ctx.root, &abs);
    if abs.is_dir() {
        return Err(AxError(format!("{rel} is a directory")));
    }
    let old = std::fs::read(&abs).ok();
    let mut r = Report::new("write");
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
    fsio::atomic_write(&abs, input)?;
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
    r.summary = Summary::plain(format!(
        "wrote {rel}: {what}, hash {}.",
        hash::file_hash(input)
    ));
    r.data = json!({
        "path": rel,
        "outcome": "ok",
        "created": old.is_none(),
        "lines": n,
        "hash": hash::file_hash(input),
    });
    Ok(r)
}
