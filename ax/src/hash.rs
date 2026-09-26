//! line + file hashes.
//!
//! a line hash is 4 lowercase hex chars: the low 16 bits of fnv-1a (64-bit)
//! over the line's exact bytes, *without* its terminator (`\n` or `\r\n`).
//! so `foo\r\n` and `foo\n` hash the same, but trailing spaces, tabs, a lone
//! `\r` in the middle, or invalid utf-8 all change it.
//!
//! a file hash is 8 hex chars: the low 32 bits of fnv-1a over the whole file.
//! both are for "did this change under me" checks, not security.

const FNV_OFFSET: u64 = 0xcbf2_9ce4_8422_2325;
const FNV_PRIME: u64 = 0x0000_0100_0000_01b3;

pub fn fnv1a(bytes: &[u8]) -> u64 {
    let mut h = FNV_OFFSET;
    for &b in bytes {
        h ^= b as u64;
        h = h.wrapping_mul(FNV_PRIME);
    }
    h
}

/// strip one trailing `\n` or `\r\n`.
pub fn strip_eol(line: &[u8]) -> &[u8] {
    let line = line.strip_suffix(b"\n").unwrap_or(line);
    line.strip_suffix(b"\r").unwrap_or(line)
}

pub fn line_hash(line: &[u8]) -> String {
    format!("{:04x}", fnv1a(strip_eol(line)) & 0xffff)
}

pub fn file_hash(bytes: &[u8]) -> String {
    format!("{:08x}", fnv1a(bytes) & 0xffff_ffff)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fnv_known_vectors() {
        // standard fnv-1a 64 test vectors
        assert_eq!(fnv1a(b""), 0xcbf29ce484222325);
        assert_eq!(fnv1a(b"a"), 0xaf63dc4c8601ec8c);
        assert_eq!(fnv1a(b"foobar"), 0x85944171f73967e8);
    }

    #[test]
    fn line_hash_is_four_hex_chars() {
        let h = line_hash(b"let x = 1;");
        assert_eq!(h.len(), 4);
        assert!(
            h.chars()
                .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
        );
    }

    #[test]
    fn terminators_dont_matter_but_content_does() {
        assert_eq!(line_hash(b"foo\n"), line_hash(b"foo"));
        assert_eq!(line_hash(b"foo\r\n"), line_hash(b"foo"));
        assert_ne!(line_hash(b"foo "), line_hash(b"foo"));
        assert_ne!(line_hash(b"\tfoo"), line_hash(b"    foo"));
        assert_ne!(line_hash(b"fo\ro"), line_hash(b"foo"));
    }

    #[test]
    fn non_utf8_is_fine() {
        let h = line_hash(&[0xff, 0xfe, b'x']);
        assert_eq!(h.len(), 4);
        assert_ne!(h, line_hash(b"x"));
    }

    #[test]
    fn file_hash_sees_everything() {
        assert_eq!(file_hash(b"a\n").len(), 8);
        assert_ne!(file_hash(b"a\n"), file_hash(b"a\r\n"));
        assert_ne!(file_hash(b"a\n"), file_hash(b"a"));
    }
}
