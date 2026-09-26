//! the file walk shared by find, map, grep and friends. defaults mirror
//! `rg --files`: .gitignore / .ignore / .rgignore respected (gitignore only
//! inside a git repo), hidden files skipped, symlinks not followed.
//! `all` is `rg -uu`: hidden + ignored files too.

use crate::{AxError, Ctx, Result, repo};
use ignore::WalkBuilder;
use ignore::overrides::OverrideBuilder;
use ignore::types::TypesBuilder;
use std::path::PathBuf;

#[derive(Debug, Clone, Default)]
pub struct WalkOpts {
    /// dirs (or files) to walk, relative to cwd. empty = repo root.
    pub roots: Vec<String>,
    /// rg-style `-g` globs; `!glob` excludes.
    pub globs: Vec<String>,
    /// rg file types (`-t ts`), using rg's built-in type table.
    pub types: Vec<String>,
    /// include hidden + ignored files.
    pub all: bool,
}

#[derive(Debug, Clone)]
pub struct Entry {
    pub abs: PathBuf,
    pub rel: String,
}

pub fn roots(ctx: &Ctx, opts: &WalkOpts) -> Result<Vec<PathBuf>> {
    if opts.roots.is_empty() {
        return Ok(vec![ctx.root.clone()]);
    }
    opts.roots
        .iter()
        .map(|r| {
            let abs = repo::absolute(&ctx.cwd, r.as_ref());
            if abs.exists() {
                Ok(abs)
            } else {
                Err(AxError(format!("no such path: {r}")))
            }
        })
        .collect()
}

pub fn builder(ctx: &Ctx, opts: &WalkOpts) -> Result<WalkBuilder> {
    let roots = roots(ctx, opts)?;
    let mut b = WalkBuilder::new(&roots[0]);
    for r in &roots[1..] {
        b.add(r);
    }
    b.add_custom_ignore_filename(".rgignore");
    if opts.all {
        b.standard_filters(false);
    }
    if !opts.globs.is_empty() {
        let mut ob = OverrideBuilder::new(&ctx.root);
        for g in &opts.globs {
            ob.add(g)
                .map_err(|e| AxError(format!("bad glob {g}: {e}")))?;
        }
        let ov = ob.build().map_err(|e| AxError(e.to_string()))?;
        b.overrides(ov);
    }
    if !opts.types.is_empty() {
        let mut tb = TypesBuilder::new();
        tb.add_defaults();
        for t in &opts.types {
            if !tb.definitions().iter().any(|d| d.name() == t) {
                return Err(AxError(format!(
                    "unknown file type {t:?} (rg's names: ts, js, py, rust, go, …)"
                )));
            }
            tb.select(t);
        }
        b.types(tb.build().map_err(|e| AxError(e.to_string()))?);
    }
    Ok(b)
}

/// every file under the roots, sorted by repo-relative path.
pub fn files(ctx: &Ctx, opts: &WalkOpts) -> Result<Vec<Entry>> {
    let mut out = Vec::new();
    for dent in builder(ctx, opts)?.build() {
        let Ok(dent) = dent else { continue };
        if !dent.file_type().is_some_and(|t| t.is_file()) {
            continue;
        }
        let abs = dent.into_path();
        let rel = repo::rel(&ctx.root, &abs);
        out.push(Entry { abs, rel });
    }
    out.sort_by(|a, b| a.rel.cmp(&b.rel));
    Ok(out)
}
