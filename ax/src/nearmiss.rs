//! when exact text isn't found, say where it almost is and why it missed.
//! nothing here is ever used to apply an edit, only to explain a refusal.

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Candidate {
    /// 0-based first line of the near match
    pub start: usize,
    pub len: usize,
    pub why: &'static str,
}

fn trim_end(s: &[u8]) -> &[u8] {
    let n = s
        .iter()
        .rposition(|b| !b.is_ascii_whitespace())
        .map_or(0, |i| i + 1);
    &s[..n]
}

fn tabs_as_spaces(s: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(s.len());
    for &b in trim_end(s) {
        if b == b'\t' {
            out.extend_from_slice(b"    ");
        } else {
            out.push(b);
        }
    }
    out
}

fn no_indent(s: &[u8]) -> Vec<u8> {
    let s = trim_end(s);
    let i = s
        .iter()
        .position(|b| !b.is_ascii_whitespace())
        .unwrap_or(s.len());
    s[i..].to_vec()
}

fn loose(s: &[u8]) -> Vec<u8> {
    s.iter()
        .filter(|b| !b.is_ascii_whitespace())
        .map(|&b| if b == b'\'' || b == b'`' { b'"' } else { b })
        .collect()
}

type Norm = fn(&[u8]) -> Vec<u8>;

const LEVELS: [(Norm, &str); 4] = [
    (|s| trim_end(s).to_vec(), "trailing whitespace differs"),
    (
        tabs_as_spaces,
        "tabs vs spaces: the file indents with tabs where your text has spaces (or the other way round)",
    ),
    (no_indent, "indentation differs"),
    (loose, "quotes or spacing inside the line differ"),
];

/// does `window` match `want` under `norm`? the first wanted line may be the
/// tail of a file line and the last one its head, like a text search would.
fn fits(window: &[&[u8]], want: &[&[u8]], norm: Norm) -> bool {
    let k = want.len();
    if k == 1 {
        let (w, l) = (norm(want[0]), norm(window[0]));
        return !w.is_empty() && memchr::memmem::find(&l, &w).is_some();
    }
    window.iter().zip(want).enumerate().all(|(i, (l, w))| {
        let (l, w) = (norm(l), norm(w));
        if i == 0 {
            l.ends_with(&w)
        } else if i + 1 == k {
            l.starts_with(&w)
        } else {
            l == w
        }
    })
}

/// near matches of `want` (lines, no terminators) in `lines`, loosest level
/// last. only the first level that matches anything is reported.
pub fn candidates(lines: &[&[u8]], want: &[&[u8]], max: usize) -> Vec<Candidate> {
    let want: Vec<&[u8]> = {
        let mut w = want.to_vec();
        while w.len() > 1 && w.last().is_some_and(|l| l.is_empty()) {
            w.pop();
        }
        w
    };
    let k = want.len();
    if k == 0 || k > lines.len() || want.iter().all(|l| trim_end(l).is_empty()) {
        return Vec::new();
    }
    for (norm, why) in LEVELS {
        let found: Vec<Candidate> = (0..=lines.len() - k)
            .filter(|&i| fits(&lines[i..i + k], &want, norm))
            .take(max)
            .map(|start| Candidate { start, len: k, why })
            .collect();
        if !found.is_empty() {
            return found;
        }
    }
    Vec::new()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn c(file: &str, want: &str) -> Vec<(usize, &'static str)> {
        let lines: Vec<&[u8]> = file.lines().map(str::as_bytes).collect();
        let want: Vec<&[u8]> = want.split('\n').map(str::as_bytes).collect();
        candidates(&lines, &want, 5)
            .into_iter()
            .map(|c| (c.start, c.why))
            .collect()
    }

    #[test]
    fn each_level() {
        assert_eq!(c("a\nfoo();  \nb", "foo();")[0].1, LEVELS[0].1);
        assert_eq!(
            c("func f() {\n\treturn 1\n}", "    return 1\n}")[0],
            (1, LEVELS[1].1)
        );
        assert_eq!(
            c("x\n      y = 1\n      z\n", "  y = 1\n  z")[0].1,
            LEVELS[2].1
        );
        assert_eq!(c("s = 'hi'\n", "s = \"hi\"")[0].1, LEVELS[3].1);
        assert!(c("nothing here\n", "totally different").is_empty());
    }

    #[test]
    fn multi_line_and_cap() {
        let file = "x\n  a\n  b\ny\n  a\n  b\n";
        let got = c(file, "a\nb");
        assert_eq!(got.iter().map(|g| g.0).collect::<Vec<_>>(), vec![1, 4]);
    }
}
