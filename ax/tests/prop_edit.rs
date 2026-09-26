//! ax's edit engine vs a deliberately dumb reference, on random files and ops.

use ax::config::Config;
use ax::edit::{Anchor, Op, Refusal, apply};
use ax::hash::line_hash;
use proptest::prelude::*;

const ALPHABET: &[&str] = &["a", "b", "x = 1", "  y", "\tz", "", "return a + b"];

#[derive(Debug, Clone)]
struct File {
    lines: Vec<String>,
    crlf: bool,
    final_nl: bool,
}

impl File {
    fn bytes(&self) -> Vec<u8> {
        let eol = if self.crlf { "\r\n" } else { "\n" };
        let mut s = self.lines.join(eol);
        if self.final_nl && !self.lines.is_empty() {
            s.push_str(eol);
        }
        s.into_bytes()
    }

    fn anchor(&self, n: usize) -> Anchor {
        Anchor {
            line: n,
            hash: Some(line_hash(self.lines[n - 1].as_bytes())),
        }
    }
}

#[derive(Debug, Clone)]
enum Spec {
    Replace(usize, usize, Vec<String>),
    Delete(usize, usize),
    Insert(usize, bool, Vec<String>),
}

fn file() -> impl Strategy<Value = File> {
    (
        prop::collection::vec(prop::sample::select(ALPHABET), 1..40),
        any::<bool>(),
        any::<bool>(),
    )
        .prop_map(|(l, crlf, final_nl)| File {
            // "a\n" with no final newline would be ambiguous with ["a", ""]
            final_nl: final_nl || l.last() == Some(&""),
            lines: l.into_iter().map(String::from).collect(),
            crlf,
        })
}

fn body() -> impl Strategy<Value = Vec<String>> {
    prop::collection::vec(prop::sample::select(&["new", "  new2", "", "b"][..]), 0..4)
        .prop_map(|v| v.into_iter().map(String::from).collect())
}

fn specs(n: usize) -> impl Strategy<Value = Vec<Spec>> {
    let one = (1..=n, 1..=n, body(), any::<bool>(), 0..3u8).prop_map(|(a, b, body, after, k)| {
        let (a, b) = (a.min(b), a.max(b));
        match k {
            0 => Spec::Replace(a, b, body),
            1 => Spec::Delete(a, b),
            _ => Spec::Insert(a, after, body),
        }
    });
    prop::collection::vec(one, 1..4)
}

fn to_ops(f: &File, specs: &[Spec]) -> Vec<Op> {
    let bytes = |v: &[String]| v.iter().map(|s| s.as_bytes().to_vec()).collect();
    specs
        .iter()
        .map(|s| match s {
            Spec::Replace(a, b, body) => Op::Replace {
                from: f.anchor(*a),
                to: f.anchor(*b),
                body: bytes(body),
            },
            Spec::Delete(a, b) => Op::Delete {
                from: f.anchor(*a),
                to: f.anchor(*b),
            },
            Spec::Insert(a, after, body) => Op::Insert {
                at: f.anchor(*a),
                after: *after,
                body: bytes(body),
            },
        })
        .collect()
}

/// the reference: splices on a Vec<String>, nothing clever.
fn reference(f: &File, specs: &[Spec]) -> Option<Vec<u8>> {
    let mut sp: Vec<(usize, usize, Vec<String>, usize)> = specs
        .iter()
        .enumerate()
        .map(|(i, s)| match s {
            Spec::Replace(a, b, body) => (a - 1, *b, body.clone(), i),
            Spec::Delete(a, b) => (a - 1, *b, vec![], i),
            Spec::Insert(a, true, body) => (*a, *a, body.clone(), i),
            Spec::Insert(a, false, body) => (a - 1, a - 1, body.clone(), i),
        })
        .collect();
    sp.sort_by_key(|s| (s.0, s.1, s.3));
    for w in sp.windows(2) {
        let (p, q) = (&w[0], &w[1]);
        if q.0 < p.1 || (p.0 == q.0 && p.1 > p.0 && q.1 > q.0) {
            return None;
        }
    }
    let mut out: Vec<String> = Vec::new();
    let mut cur = 0;
    for (s, e, body, _) in sp {
        out.extend(f.lines[cur..s].iter().cloned());
        out.extend(body);
        cur = e;
    }
    out.extend(f.lines[cur..].iter().cloned());
    // a file without any line break carries no CRLF information: ax uses \n
    let crlf = f.crlf && f.bytes().windows(2).any(|w| w == b"\r\n");
    Some(
        File {
            lines: out,
            crlf,
            final_nl: f.final_nl,
        }
        .bytes(),
    )
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(10_000))]

    #[test]
    fn ax_matches_reference((f, s) in file().prop_flat_map(|f| { let n = f.lines.len(); (Just(f), specs(n)) })) {
        let got = apply(&f.bytes(), &to_ops(&f, &s), &Config::default());
        match (reference(&f, &s), got) {
            (Some(want), Ok(a)) => prop_assert_eq!(want, a.bytes),
            (None, Err(Refusal::Overlap(_))) => {}
            (want, got) => prop_assert!(false, "reference {:?} vs ax {:?}", want.map(|b| String::from_utf8(b).unwrap()), got),
        }
    }
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(2_000))]

    /// change the anchored line to fresh content: the edit must be refused,
    /// and on disk the file must be byte-identical afterwards.
    #[test]
    fn stale_anchor_always_refused_and_file_untouched(
        (f, n) in file().prop_flat_map(|f| { let n = f.lines.len(); (Just(f), 1..=n) })
    ) {
        let mut f = f;
        f.lines[n - 1] = format!("unique line {n}");
        let old = f.anchor(n);
        let mut changed = f.clone();
        changed.lines[n - 1] = format!("changed {n}");
        // a 16-bit hash can collide with another line; that's relocation, not staleness
        prop_assume!(changed.lines.iter().all(|l| Some(line_hash(l.as_bytes())) != old.hash));

        let ops = vec![Op::Replace { from: old.clone(), to: old, body: vec![b"z".to_vec()] }];
        let r = apply(&changed.bytes(), &ops, &Config::default());
        prop_assert!(matches!(r, Err(Refusal::Stale { .. })), "{:?}", r);

        let t = tempfile::tempdir().unwrap();
        std::fs::create_dir(t.path().join(".git")).unwrap();
        let p = t.path().join("f.txt");
        std::fs::write(&p, changed.bytes()).unwrap();
        let ctx = ax::Ctx { cfg: Config::default(), cwd: t.path().to_path_buf(), root: t.path().canonicalize().unwrap() };
        let script = format!("@@ replace {}:{}\nz\n", n, line_hash(f.lines[n - 1].as_bytes()));
        let rep = ax::edit::run(&ctx, "f.txt", script.as_bytes(), false).unwrap();
        prop_assert!(rep.failed);
        prop_assert_eq!(std::fs::read(&p).unwrap(), changed.bytes());
    }
}
