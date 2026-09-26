//! line hits (grep, refs) grouped by file, then by enclosing symbol:
//!
//! ```text
//! src/hono-base.ts
//!   @ Hono.fetch  (method 380-392)
//!   384:9c2e      return this.#dispatch(request, executionCtx, env, request.method)
//! ```
//!
//! code lines are printed exactly as they are in the file (behind the anchor)
//! so they can be copied or anchored in an edit; symbol info goes on its own
//! `@` line instead of being glued onto the code.

use crate::config::Config;
use crate::output::{anchor, anchored};
use crate::syntax::{self, Lang, Symbol};
use serde::Serialize;
use serde_json::{Value, json};

#[derive(Debug, Clone)]
pub struct Hit {
    pub rel: String,
    /// 1-based
    pub line: usize,
    pub bytes: Vec<u8>,
    pub symbol: Option<Symbol>,
    /// a -C context line rather than a match
    pub context: bool,
}

#[derive(Serialize)]
struct HitJson<'a> {
    path: &'a str,
    line: usize,
    anchor: String,
    text: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    symbol: Option<&'a str>,
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    context: bool,
}

/// symbols for a file if we speak its language (and symbols aren't switched off).
pub fn symbols_for(cfg: &Config, rel: &str, src: &[u8]) -> Vec<Symbol> {
    if !cfg.symbols {
        return Vec::new();
    }
    let Some(lang) = Lang::from_path(rel) else {
        return Vec::new();
    };
    syntax::parse(lang, src)
        .map(|t| syntax::symbols(lang, &t, src))
        .unwrap_or_default()
}

/// with context lines around, match lines get a `>` in the gutter so you can
/// tell them apart; without context every line is a match and the gutter is
/// blank.
pub fn render(cfg: &Config, hits: &[Hit]) -> Vec<String> {
    let mut out = Vec::new();
    let mut cur_file: Option<&str> = None;
    let mut cur_sym: Option<&str> = None;
    let mut last_line = 0usize;
    let marks = hits.iter().any(|h| h.context);
    for h in hits {
        let sym = h.symbol.as_ref().map(|s| s.path.as_str());
        if cur_file != Some(h.rel.as_str()) {
            out.push(h.rel.clone());
            cur_file = Some(&h.rel);
            cur_sym = None;
        } else if h.line > last_line + 1 && sym == cur_sym {
            // gap inside the same symbol; a new `@` header already makes a
            // jump obvious
            out.push("  …".into());
        }
        if sym != cur_sym {
            match &h.symbol {
                Some(s) => out.push(format!(
                    "  @ {}  ({} {}-{})",
                    s.path, s.kind, s.start, s.end
                )),
                None => out.push("  @ (top level)".into()),
            }
            cur_sym = sym;
        }
        let gutter = if marks && !h.context { "> " } else { "  " };
        out.push(format!("{gutter}{}", anchored(cfg, h.line, &h.bytes)));
        last_line = h.line;
    }
    out
}

pub fn to_json(hits: &[Hit]) -> Value {
    let v: Vec<HitJson> = hits
        .iter()
        .map(|h| HitJson {
            path: &h.rel,
            line: h.line,
            anchor: anchor(h.line, &h.bytes),
            text: String::from_utf8_lossy(crate::hash::strip_eol(&h.bytes)).into_owned(),
            symbol: h.symbol.as_ref().map(|s| s.path.as_str()),
            context: h.context,
        })
        .collect();
    json!(v)
}

pub fn files_in(hits: &[Hit]) -> usize {
    let mut n = 0;
    let mut last: Option<&str> = None;
    for h in hits {
        if last != Some(h.rel.as_str()) {
            n += 1;
            last = Some(&h.rel);
        }
    }
    n
}

/// word characters for identifier matching (covers js `$` too).
pub fn is_word(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_' || b == b'$'
}

/// byte offsets of whole-word occurrences of `needle` in `hay`.
pub fn word_matches(hay: &[u8], needle: &[u8]) -> Vec<usize> {
    memchr::memmem::find_iter(hay, needle)
        .filter(|&i| {
            let before = i == 0 || !is_word(hay[i - 1]);
            let j = i + needle.len();
            let after = j >= hay.len() || !is_word(hay[j]);
            before && after
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn words() {
        assert_eq!(
            word_matches(b"foo foobar _foo foo.x $foo foo", b"foo"),
            vec![0, 16, 27]
        );
        assert!(word_matches(b"", b"foo").is_empty());
    }

    #[test]
    fn grouping() {
        let cfg = Config {
            anchors: false,
            ..Config::default()
        };
        let sym = Symbol {
            kind: "method",
            name: "m".into(),
            path: "A.m".into(),
            start: 2,
            end: 9,
            depth: 1,
        };
        let h = |rel: &str, line, s: Option<Symbol>| Hit {
            rel: rel.into(),
            line,
            bytes: format!("line{line}\n").into_bytes(),
            symbol: s,
            context: false,
        };
        let hits = vec![
            h("a.ts", 1, None),
            h("a.ts", 3, Some(sym.clone())),
            h("a.ts", 4, Some(sym)),
            h("b.ts", 7, None),
        ];
        assert_eq!(
            render(&cfg, &hits),
            vec![
                "a.ts",
                "  1  line1",
                "  @ A.m  (method 2-9)",
                "  3  line3",
                "  4  line4",
                "b.ts",
                "  7  line7",
            ]
        );
        assert_eq!(files_in(&hits), 2);
    }
}
