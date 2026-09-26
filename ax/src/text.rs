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
    fn binary() {
        assert!(is_binary(b"ab\0c"));
        assert!(!is_binary("héllo".as_bytes()));
    }
}
