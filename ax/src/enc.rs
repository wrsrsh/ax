//! files that aren't UTF-8 are read and written as Windows-1252 (a superset of
//! Latin-1 for printable text), so é stays one byte instead of turning into
//! U+FFFD or a UTF-8 pair in the middle of a 1252 file.

use encoding_rs::WINDOWS_1252;
use std::borrow::Cow;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Enc {
    Utf8,
    Win1252,
}

impl Enc {
    pub fn detect(bytes: &[u8]) -> Enc {
        if std::str::from_utf8(bytes).is_ok() {
            Enc::Utf8
        } else {
            Enc::Win1252
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            Enc::Utf8 => "utf-8",
            Enc::Win1252 => "windows-1252",
        }
    }

    /// agent text (UTF-8) in this file's encoding. Err names the first
    /// character that has no Windows-1252 byte.
    pub fn encode<'a>(self, text: &'a [u8]) -> Result<Cow<'a, [u8]>, char> {
        let Enc::Win1252 = self else {
            return Ok(Cow::Borrowed(text));
        };
        let Ok(s) = std::str::from_utf8(text) else {
            return Ok(Cow::Borrowed(text));
        };
        let mut out = Vec::with_capacity(s.len());
        for c in s.chars() {
            let mut buf = [0u8; 4];
            let (b, _, bad) = WINDOWS_1252.encode(c.encode_utf8(&mut buf));
            if bad {
                return Err(c);
            }
            out.extend_from_slice(&b);
        }
        Ok(Cow::Owned(out))
    }
}

/// one line for display: UTF-8 as is, anything else as Windows-1252.
pub fn show(line: &[u8]) -> Cow<'_, str> {
    match std::str::from_utf8(line) {
        Ok(s) => Cow::Borrowed(s),
        Err(_) => WINDOWS_1252.decode_without_bom_handling(line).0,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip() {
        let raw = b"caf\xe9 \x80 \xfc";
        assert_eq!(Enc::detect(raw), Enc::Win1252);
        assert_eq!(show(raw), "café € ü");
        assert_eq!(
            Enc::Win1252.encode("café € ü".as_bytes()).unwrap().as_ref(),
            raw
        );
        assert_eq!(Enc::Win1252.encode("漢".as_bytes()), Err('漢'));
        assert_eq!(Enc::detect("café".as_bytes()), Enc::Utf8);
        assert_eq!(
            Enc::Utf8.encode("漢".as_bytes()).unwrap().as_ref(),
            "漢".as_bytes()
        );
    }
}
