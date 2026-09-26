//! shared output rules:
//! - lines come out as `LINE:HASH  text` (or `LINE  text` with anchors off)
//! - results are capped, and every command ends with exactly one summary line
//!   saying totals, what got cut, and how to narrow
//! - `--json` wraps the same data in one object per call

use crate::config::Config;
use crate::hash::{line_hash, strip_eol};
use serde::Serialize;
use serde_json::Value;

/// `14:a3f1  code`. invalid utf-8 is shown lossily; the hash is still over the
/// raw bytes.
pub fn anchored(cfg: &Config, n: usize, line: &[u8]) -> String {
    let text = String::from_utf8_lossy(strip_eol(line));
    if cfg.anchors {
        format!("{n}:{}  {text}", line_hash(line))
    } else {
        format!("{n}  {text}")
    }
}

/// just the anchor, e.g. `14:a3f1`, used in json and edit feedback.
pub fn anchor(n: usize, line: &[u8]) -> String {
    format!("{n}:{}", line_hash(line))
}

/// keep at most `cap` items, remembering how many there were.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Capped<T> {
    pub items: Vec<T>,
    pub total: usize,
}

impl<T> Capped<T> {
    pub fn new(mut items: Vec<T>, cap: Option<usize>) -> Self {
        let total = items.len();
        if let Some(c) = cap {
            items.truncate(c);
        }
        Capped { items, total }
    }

    pub fn truncated(&self) -> bool {
        self.items.len() < self.total
    }
}

/// the one line every command ends with.
#[derive(Debug, Clone, Default, Serialize, PartialEq, Eq)]
pub struct Summary {
    pub total: usize,
    pub shown: usize,
    pub truncated: bool,
    pub text: String,
}

impl Summary {
    /// `noun` is singular ("hit", "file"); pluralized with an `s`.
    /// `scope` is extra context like "in 14 files"; `narrow` is the hint shown
    /// only when something was cut.
    pub fn counted(noun: &str, total: usize, shown: usize, scope: &str, narrow: &str) -> Self {
        let plural = |n: usize| {
            if n == 1 {
                noun.to_string()
            } else {
                format!("{noun}s")
            }
        };
        let scope = if scope.is_empty() {
            String::new()
        } else {
            format!(" {scope}")
        };
        let text = if total == 0 {
            format!("no {}{scope}.", plural(0))
        } else if shown < total {
            format!(
                "{total} {}{scope}, showing first {shown}. narrow with {narrow}.",
                plural(total)
            )
        } else {
            format!("{total} {}{scope}.", plural(total))
        };
        Summary {
            total,
            shown,
            truncated: shown < total,
            text,
        }
    }

    pub fn plain(text: impl Into<String>) -> Self {
        Summary {
            text: text.into(),
            ..Default::default()
        }
    }
}

/// what a command hands back to main: text lines + the same thing as json.
#[derive(Debug, Clone)]
pub struct Report {
    pub command: &'static str,
    pub lines: Vec<String>,
    pub data: Value,
    pub summary: Summary,
    /// output is still printed, but the exit code is 1 (e.g. one of several
    /// files in `ax read` didn't exist)
    pub failed: bool,
}

impl Report {
    pub fn new(command: &'static str) -> Self {
        Report {
            command,
            lines: Vec::new(),
            data: Value::Null,
            summary: Summary::default(),
            failed: false,
        }
    }

    /// text output, cut at line boundaries to stay under `max_bytes` so an
    /// agent harness never has to truncate it for us (and silently).
    pub fn render_text(&self, max_bytes: Option<usize>) -> String {
        let summary_len = self.summary.text.len() + 120;
        let budget = max_bytes.map(|m| m.saturating_sub(summary_len));
        let mut s = String::new();
        let mut shown = 0;
        for l in &self.lines {
            if budget.is_some_and(|b| s.len() + l.len() + 1 > b) {
                break;
            }
            s.push_str(l);
            s.push('\n');
            shown += 1;
        }
        s.push_str(&self.summary.text);
        if shown < self.lines.len() {
            s.push_str(&format!(
                " output cut at {} bytes (AX_MAX_BYTES): {} more lines not shown, narrow the call.",
                max_bytes.unwrap_or(0),
                self.lines.len() - shown
            ));
        }
        s.push('\n');
        s
    }

    pub fn render_json(&self) -> String {
        let v = serde_json::json!({
            "command": self.command,
            "data": self.data,
            "summary": self.summary,
        });
        let mut s = serde_json::to_string(&v).expect("report is valid json");
        s.push('\n');
        s
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn anchored_lines() {
        let c = Config::default();
        let l = anchored(&c, 14, b"  let x = 1;\n");
        assert!(l.starts_with("14:"), "{l}");
        assert!(l.ends_with("  let x = 1;"), "{l}");
        assert_eq!(l.split("  ").next().unwrap().len(), "14:".len() + 4);

        let off = Config {
            anchors: false,
            ..Config::default()
        };
        assert_eq!(anchored(&off, 3, b"x\r\n"), "3  x");
    }

    #[test]
    fn lossy_but_stable() {
        let c = Config::default();
        let l = anchored(&c, 1, &[b'a', 0xff, b'b']);
        assert!(l.ends_with("a\u{fffd}b"));
    }

    #[test]
    fn capping() {
        let c = Capped::new((0..120).collect::<Vec<_>>(), Some(50));
        assert_eq!(c.items.len(), 50);
        assert_eq!(c.total, 120);
        assert!(c.truncated());
        let u = Capped::new(vec![1, 2], None);
        assert!(!u.truncated());
    }

    #[test]
    fn summary_texts() {
        assert_eq!(
            Summary::counted("hit", 0, 0, "for \"foo\"", "").text,
            "no hits for \"foo\"."
        );
        assert_eq!(Summary::counted("file", 1, 1, "", "").text, "1 file.");
        let s = Summary::counted("hit", 120, 50, "in 14 files", "--in <dir> or -t <type>");
        assert_eq!(
            s.text,
            "120 hits in 14 files, showing first 50. narrow with --in <dir> or -t <type>."
        );
        assert!(s.truncated);
    }

    #[test]
    fn text_is_cut_at_the_byte_budget() {
        let mut r = Report::new("read");
        r.lines = (0..100)
            .map(|i| format!("line {i:03} {}", "x".repeat(40)))
            .collect();
        r.summary = Summary::plain("read 1 file.");
        let t = r.render_text(Some(1000));
        assert!(t.len() <= 1000 + 200, "{}", t.len());
        assert!(t.trim_end().ends_with("narrow the call."), "{t}");
        assert!(t.contains("more lines not shown"));
        assert_eq!(r.render_text(None).lines().count(), 101);
    }

    #[test]
    fn report_renders_both_ways() {
        let mut r = Report::new("grep");
        r.lines.push("src/a.rs".into());
        r.data = serde_json::json!({"hits": []});
        r.summary = Summary::counted("hit", 0, 0, "", "");
        assert_eq!(r.render_text(None), "src/a.rs\nno hits.\n");
        let v: Value = serde_json::from_str(&r.render_json()).unwrap();
        assert_eq!(v["command"], "grep");
        assert_eq!(v["summary"]["text"], "no hits.");
        assert_eq!(v["summary"]["truncated"], false);
    }
}
