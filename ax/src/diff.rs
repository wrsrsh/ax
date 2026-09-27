//! `ax diff [--full|--stat] [paths…]`: what changed vs HEAD, in one bounded shot.
//! status + per-file +/- counts, untracked files with line counts, then the
//! hunks, capped at AX_DIFF_LINES (40) unless --full.

use crate::output::{Report, Summary};
use crate::{AxError, Ctx, Result, text};
use serde_json::json;
use std::path::Path;
use std::process::Command;

fn git(root: &Path, args: &[&str]) -> Result<String> {
    let out = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .map_err(|e| AxError(format!("couldn't run git: {e}")))?;
    if !out.status.success() {
        return Err(AxError(format!(
            "git {} failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&out.stderr).trim()
        )));
    }
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

#[derive(Debug, Clone, serde::Serialize)]
struct FileChange {
    status: String,
    path: String,
    added: Option<usize>,
    removed: Option<usize>,
}

pub fn run(ctx: &Ctx, full: bool, stat: bool, paths: &[String]) -> Result<Report> {
    let root = &ctx.root;
    // paths come in relative to cwd, git -C root wants them relative to root
    let paths: Vec<String> = paths
        .iter()
        .map(|p| crate::repo::rel(root, &crate::repo::absolute(&ctx.cwd, p.as_ref())))
        .collect();
    if git(root, &["rev-parse", "--is-inside-work-tree"]).is_err() {
        return Err(AxError("not a git repo, nothing to diff".into()));
    }
    let has_head = git(root, &["rev-parse", "--verify", "-q", "HEAD"]).is_ok();
    let branch = git(root, &["rev-parse", "--abbrev-ref", "HEAD"])
        .map(|b| b.trim().to_string())
        .unwrap_or_else(|_| "(no commits yet)".into());

    let git_paths = |args: &[&str]| {
        let mut a: Vec<&str> = args.to_vec();
        if !paths.is_empty() {
            a.push("--");
            a.extend(paths.iter().map(String::as_str));
        }
        git(root, &a)
    };

    // tracked changes vs HEAD (or vs the empty tree before the first commit)
    let base = if has_head {
        "HEAD"
    } else {
        "4b825dc642cb6eb9a060e54bf8d69288fbee4904" // git's empty tree
    };
    let numstat = git_paths(&["diff", base, "--numstat", "--no-renames"])?;
    let status = git_paths(&["status", "--porcelain=v1", "-uall", "--no-renames"])?;
    let patch = git_paths(&[
        "diff",
        base,
        "--no-color",
        "--no-ext-diff",
        "--no-renames",
        "-U3",
    ])?;

    let mut counts = std::collections::HashMap::new();
    for l in numstat.lines() {
        let mut it = l.splitn(3, '\t');
        if let (Some(a), Some(r), Some(p)) = (it.next(), it.next(), it.next()) {
            counts.insert(p.to_string(), (a.parse().ok(), r.parse().ok()));
        }
    }
    let mut changes = Vec::new();
    for l in status.lines() {
        if l.len() < 4 {
            continue;
        }
        let (st, p) = l.split_at(2);
        let p = p.trim_start().trim_matches('"').to_string();
        let (added, removed) = if st == "??" {
            let n = std::fs::read(root.join(&p))
                .ok()
                .filter(|b| !text::is_binary(b))
                .map(|b| text::line_count(&b));
            (n, Some(0))
        } else {
            counts.get(&p).copied().unwrap_or((None, None))
        };
        changes.push(FileChange {
            status: st.trim().to_string(),
            path: p,
            added,
            removed,
        });
    }

    let mut r = Report::new("diff");
    if changes.is_empty() {
        r.summary = Summary::plain(format!("no changes (clean working tree on {branch})."));
        r.data = json!({ "branch": branch, "files": [], "patch": "" });
        return Ok(r);
    }

    let plus: usize = changes.iter().filter_map(|c| c.added).sum();
    let minus: usize = changes.iter().filter_map(|c| c.removed).sum();
    let untracked = changes.iter().filter(|c| c.status == "??").count();
    r.lines.push(format!(
        "branch {branch} · {} changed{} · +{plus} -{minus}",
        text::plural(changes.len() - untracked, "file"),
        if untracked > 0 {
            format!(", {untracked} untracked")
        } else {
            String::new()
        }
    ));
    let w = changes
        .iter()
        .map(|c| c.path.len())
        .max()
        .unwrap_or(0)
        .min(60);
    for c in &changes {
        let stat = match (c.added, c.removed) {
            _ if c.status == "??" => c
                .added
                .map(|n| format!("new, {}", text::lines_label(n)))
                .unwrap_or_else(|| "new, binary".into()),
            (Some(a), Some(d)) => format!("+{a} -{d}"),
            _ => "binary".into(),
        };
        r.lines
            .push(format!("{:>2} {:<w$}  {stat}", c.status, c.path));
    }

    let patch_lines: Vec<&str> = patch.lines().collect();
    let cap = if full || !ctx.cfg.caps {
        usize::MAX
    } else {
        ctx.cfg.diff_lines
    };
    let shown = if stat { 0 } else { patch_lines.len().min(cap) };
    if shown > 0 {
        r.lines.push(String::new());
        r.lines
            .extend(patch_lines[..shown].iter().map(|l| l.to_string()));
    }
    let mut text = format!(
        "{} changed, +{plus} -{minus}.",
        text::plural(changes.len(), "file")
    );
    if stat {
        text.push_str(" stat only; `ax diff` for the hunks.");
    } else if shown < patch_lines.len() {
        text.push_str(&format!(
            " showed {shown} of {} diff lines; --stat for just the per-file counts, --full for every hunk, or `ax diff <path>` for one file.",
            patch_lines.len()
        ));
    }
    if untracked > 0 {
        text.push_str(" untracked files aren't in the hunks; `ax read` them.");
    }
    r.summary = Summary {
        total: changes.len(),
        shown: changes.len(),
        truncated: !stat && shown < patch_lines.len(),
        text,
    };
    r.data = json!({
        "branch": branch,
        "files": changes,
        "patch": patch_lines[..shown].join("\n"),
        "patch_lines": patch_lines.len(),
    });
    Ok(r)
}
