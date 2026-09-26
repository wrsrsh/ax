//! byte-level text helpers shared by read, grep and edit.

/// number of lines the way an editor counts them: a trailing newline doesn't
/// start a new line, a missing one doesn't lose the last line.
pub fn line_count(b: &[u8]) -> usize {
    if b.is_empty() {
        return 0;
    }
    let nl = b.iter().filter(|&&c| c == b'\n').count();
    nl + usize::from(b.last() != Some(&b'\n'))
}

/// split into lines, each keeping its terminator (`\n` or `\r\n`).
pub fn lines(b: &[u8]) -> Vec<&[u8]> {
    b.split_inclusive(|&c| c == b'\n').collect()
}

/// crude but standard (same as git/grep): a nul byte in the first 8k.
pub fn is_binary(b: &[u8]) -> bool {
    b.iter().take(8192).any(|&c| c == 0)
}

/// `1 line`, `2 lines`.
pub fn lines_label(n: usize) -> String {
    if n == 1 {
        "1 line".into()
    } else {
        format!("{n} lines")
    }
}

/// `12:a3f1  code` pasted back as code: most non-empty lines start with an
/// ax anchor.
pub fn looks_anchored<L: AsRef<[u8]>>(lines: &[L]) -> bool {
    let is_anchor = |l: &[u8]| {
        let l = l.trim_ascii_start();
        let digits = l.iter().take_while(|b| b.is_ascii_digit()).count();
        digits > 0
            && l.get(digits) == Some(&b':')
            && l.len() >= digits + 7
            && l[digits + 1..digits + 5]
                .iter()
                .all(|b| b.is_ascii_hexdigit())
            && &l[digits + 5..digits + 7] == b"  "
    };
    let nonempty: Vec<&[u8]> = lines
        .iter()
        .map(AsRef::as_ref)
        .filter(|l| !l.trim_ascii().is_empty())
        .collect();
    let hits = nonempty.iter().filter(|l| is_anchor(l)).count();
    hits >= 1 && hits * 2 >= nonempty.len()
}

/// lines that end in spaces or tabs.
pub fn trailing_ws<L: AsRef<[u8]>>(lines: &[L]) -> usize {
    lines
        .iter()
        .filter(|l| {
            let l = crate::hash::strip_eol(l.as_ref());
            l.last().is_some_and(|b| *b == b' ' || *b == b'\t')
        })
        .count()
}

/// `1 file`, `3 files`.
pub fn plural(n: usize, noun: &str) -> String {
    if n == 1 {
        format!("1 {noun}")
    } else {
        format!("{n} {noun}s")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn counts() {
        assert_eq!(line_count(b""), 0);
        assert_eq!(line_count(b"a"), 1);
        assert_eq!(line_count(b"a\n"), 1);
        assert_eq!(line_count(b"a\nb"), 2);
        assert_eq!(line_count(b"a\r\nb\r\n"), 2);
        assert_eq!(line_count(b"\n\n"), 2);
    }

    #[test]
    fn splits_keep_terminators() {
        assert_eq!(lines(b"a\r\nb\nc"), vec![&b"a\r\n"[..], b"b\n", b"c"]);
        assert!(lines(b"").is_empty());
    }

    #[test]
    fn anchored_bodies() {
        assert!(looks_anchored(&[
            "12:a3f1  let x = 1",
            "13:00ff  let y = 2"
        ]));
        assert!(looks_anchored(&["  7:beef  return 1"]));
        assert!(!looks_anchored(&["let x = 1", "12:a3f1  y"][..1]));
        assert!(!looks_anchored(&["a", "b", "12:a3f1  y"]));
        assert!(!looks_anchored(&["time: 12:30  ok"]));
        assert!(!looks_anchored::<&str>(&[]));
    }

    #[test]
    fn trailing() {
        assert_eq!(trailing_ws(&["a ", "b", "c\t\n", "d\n"]), 2);
    }

    #[test]
    fn binary() {
        assert!(is_binary(b"ab\0c"));
        assert!(!is_binary("héllo".as_bytes()));
    }
}
