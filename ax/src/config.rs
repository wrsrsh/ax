//! knobs, all read from env so ablations don't need code changes.
//!
//! | env                  | default | effect                                  |
//! |----------------------|---------|-----------------------------------------|
//! | AX_NO_CAPS=1         | off     | no hit / window caps                    |
//! | AX_NO_ANCHORS=1      | off     | print `14  code` instead of `14:a3f1  code` |
//! | AX_NO_SYMBOLS=1      | off     | no enclosing-symbol tags on grep hits   |
//! | AX_NO_PARSE_CHECK=1  | off     | edits skip the tree-sitter parse guard  |
//! | AX_NO_RELOCATE=1     | off     | moved anchors are refused, not relocated |
//! | AX_MAX_HITS=n        | 50      | grep/find/refs hit cap                  |
//! | AX_READ_WINDOW=n     | 200     | lines per read window                   |
//! | AX_LONG_FILE=n       | 300     | files longer than this get an outline   |
//! | AX_MAX_BYTES=n       | 24000   | text output cap per call (~7k tokens)   |

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Config {
    pub caps: bool,
    pub anchors: bool,
    pub symbols: bool,
    pub parse_check: bool,
    pub relocate: bool,
    pub max_hits: usize,
    pub read_window: usize,
    pub long_file: usize,
    pub max_bytes: usize,
}

impl Default for Config {
    fn default() -> Self {
        Config {
            caps: true,
            anchors: true,
            symbols: true,
            parse_check: true,
            relocate: true,
            max_hits: 50,
            read_window: 200,
            long_file: 300,
            max_bytes: 24_000,
        }
    }
}

impl Config {
    pub fn from_env() -> Self {
        Self::from_lookup(|k| std::env::var(k).ok())
    }

    pub fn from_lookup(get: impl Fn(&str) -> Option<String>) -> Self {
        let off = |k: &str| get(k).is_some_and(|v| !v.is_empty() && v != "0");
        let num = |k: &str, d: usize| {
            get(k)
                .and_then(|v| v.parse().ok())
                .filter(|&n| n > 0)
                .unwrap_or(d)
        };
        let d = Config::default();
        Config {
            caps: !off("AX_NO_CAPS"),
            anchors: !off("AX_NO_ANCHORS"),
            symbols: !off("AX_NO_SYMBOLS"),
            parse_check: !off("AX_NO_PARSE_CHECK"),
            relocate: !off("AX_NO_RELOCATE"),
            max_hits: num("AX_MAX_HITS", d.max_hits),
            read_window: num("AX_READ_WINDOW", d.read_window),
            long_file: num("AX_LONG_FILE", d.long_file),
            max_bytes: num("AX_MAX_BYTES", d.max_bytes),
        }
    }

    /// the hit cap to apply, or None when caps are off.
    pub fn hit_cap(&self) -> Option<usize> {
        self.caps.then_some(self.max_hits)
    }

    pub fn byte_cap(&self) -> Option<usize> {
        self.caps.then_some(self.max_bytes)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn cfg(pairs: &[(&str, &str)]) -> Config {
        let m: HashMap<String, String> = pairs
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect();
        Config::from_lookup(|k| m.get(k).cloned())
    }

    #[test]
    fn defaults() {
        assert_eq!(cfg(&[]), Config::default());
    }

    #[test]
    fn switches_and_numbers() {
        let c = cfg(&[
            ("AX_NO_CAPS", "1"),
            ("AX_NO_ANCHORS", "yes"),
            ("AX_NO_SYMBOLS", "0"),
            ("AX_READ_WINDOW", "100"),
            ("AX_MAX_HITS", "nope"),
        ]);
        assert!(!c.caps && !c.anchors && c.symbols);
        assert_eq!(c.read_window, 100);
        assert_eq!(c.max_hits, 50);
        assert_eq!(c.hit_cap(), None);
    }
}
