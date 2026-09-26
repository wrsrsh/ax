//! `ax find [name|glob] [--ext rs,ts] [--in dir] [--changed 1h] [--all]`
//!
//! a pattern with glob chars (`* ? [ {`) is an rg-style `-g` glob (so `*.rs`
//! matches at any depth, `src/**/*.ts` is anchored). anything else is a
//! smart-case substring match on the file name.

use crate::output::{Capped, Report, Summary};
use crate::walk::{self, WalkOpts};
use crate::{AxError, Ctx, Result};
use std::time::{Duration, SystemTime};

#[derive(Debug, Clone, Default)]
pub struct FindArgs {
    pub pattern: Option<String>,
    pub ext: Vec<String>,
    pub within: Vec<String>,
    pub changed: Option<String>,
    pub all: bool,
}

pub fn is_glob(p: &str) -> bool {
    p.contains(['*', '?', '[', '{'])
}

/// `90s`, `30m`, `1h`, `2d`, `1w`. bare numbers are seconds.
pub fn parse_age(s: &str) -> Result<Duration> {
    let s = s.trim();
    let split = s.find(|c: char| !c.is_ascii_digit()).unwrap_or(s.len());
    let (num, unit) = s.split_at(split);
    let n: u64 = num
        .parse()
        .map_err(|_| AxError(format!("bad --changed value {s:?} (try 30m, 1h, 2d)")))?;
    let secs = match unit {
        "" | "s" => n,
        "m" => n * 60,
        "h" => n * 3600,
        "d" => n * 86400,
        "w" => n * 7 * 86400,
        _ => {
            return Err(AxError(format!(
                "bad --changed unit {unit:?} (use s, m, h, d, w)"
            )));
        }
    };
    Ok(Duration::from_secs(secs))
}

pub fn run(ctx: &Ctx, args: &FindArgs) -> Result<Report> {
    let mut opts = WalkOpts {
        roots: args.within.clone(),
        all: args.all,
        ..Default::default()
    };
    let mut substring = None;
    if let Some(p) = &args.pattern {
        if is_glob(p) {
            opts.globs.push(p.clone());
        } else {
            substring = Some(p.clone());
        }
    }
    let exts: Vec<String> = args
        .ext
        .iter()
        .flat_map(|e| e.split(','))
        .map(|e| e.trim().trim_start_matches('.').to_string())
        .filter(|e| !e.is_empty())
        .collect();
    let cutoff = match &args.changed {
        Some(c) => Some(SystemTime::now() - parse_age(c)?),
        None => None,
    };

    let mut hits = Vec::new();
    for e in walk::files(ctx, &opts)? {
        let name = e.rel.rsplit('/').next().unwrap_or(&e.rel);
        if let Some(sub) = &substring {
            // a slash means "match the path", otherwise just the file name
            let hay = if sub.contains('/') {
                e.rel.as_str()
            } else {
                name
            };
            let ok = if sub.chars().any(|c| c.is_uppercase()) {
                hay.contains(sub.as_str())
            } else {
                hay.to_lowercase().contains(&sub.to_lowercase())
            };
            if !ok {
                continue;
            }
        }
        if !exts.is_empty() {
            let ext = name.rsplit_once('.').map(|(_, x)| x).unwrap_or("");
            if !exts.iter().any(|x| x == ext) {
                continue;
            }
        }
        if let Some(cut) = cutoff {
            let fresh = std::fs::metadata(&e.abs)
                .and_then(|m| m.modified())
                .is_ok_and(|t| t >= cut);
            if !fresh {
                continue;
            }
        }
        hits.push(e.rel);
    }

    let capped = Capped::new(hits, ctx.cfg.hit_cap());
    let mut what = Vec::new();
    if let Some(p) = &args.pattern {
        what.push(format!("matching {p:?}"));
    }
    if !exts.is_empty() {
        what.push(format!("with ext {}", exts.join(",")));
    }
    if let Some(c) = &args.changed {
        what.push(format!("changed in the last {c}"));
    }
    if !args.within.is_empty() {
        what.push(format!("in {}", args.within.join(", ")));
    }
    let mut summary = Summary::counted(
        "file",
        capped.total,
        capped.items.len(),
        &what.join(" "),
        "a longer name, a glob like 'src/**/*.ts', --ext or --in <dir>",
    );
    if capped.total == 0 && !args.all {
        summary
            .text
            .push_str(" (hidden + gitignored files skipped; --all includes them)");
    }

    let mut r = Report::new("find");
    r.lines = capped.items.clone();
    r.data = serde_json::json!({ "files": capped.items });
    r.summary = summary;
    Ok(r)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ages() {
        assert_eq!(parse_age("90").unwrap().as_secs(), 90);
        assert_eq!(parse_age("30m").unwrap().as_secs(), 1800);
        assert_eq!(parse_age("1h").unwrap().as_secs(), 3600);
        assert_eq!(parse_age("2d").unwrap().as_secs(), 172800);
        assert!(parse_age("1y").is_err());
        assert!(parse_age("h").is_err());
    }

    #[test]
    fn glob_detection() {
        assert!(is_glob("*.rs"));
        assert!(is_glob("src/{a,b}.ts"));
        assert!(!is_glob("router"));
        assert!(!is_glob("src/router.ts"));
    }
}
