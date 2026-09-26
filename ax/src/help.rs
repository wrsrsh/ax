//! `ax agent-help`: the note that goes in AGENTS.md / CLAUDE.md.

use crate::output::{Report, Summary};
use serde_json::json;

pub const NOTE: &str = "\
## ax
`ax` is installed. Use it instead of cat/sed/grep/find/apply_patch for reading, searching and editing files.
- `ax map` one-screen overview of the repo. start here.
- `ax find <name|glob>` files (gitignore-aware). `ax grep <pattern> [paths]` takes rg flags (-F -w -i -t -g -C -l -c); hits come grouped by file and enclosing function.
- `ax outline <file|dir>`, `ax def <sym>`, `ax refs <sym>`: symbols. name-based, not type-aware.
- `ax read <path[:a-b]>...` many files or ranges in one call. long files show an outline + the first 200 lines.
Every line comes back as `LINE:HASH  code`. The prefix isn't part of the line: never copy it into code or count it toward line width. Edits point at those anchors:
```
ax edit src/app.ts <<'EOF'
@@ replace 12:a3f1..15:9c2e
new lines here
@@ insert after 20:77b0
more lines
@@ delete 30:1b2c
@@ find
exact old text (must match once)
@@ with
new text
EOF
```
`ax write <path> --if <hash>` replaces a whole file (new files need no --if), `ax patch` applies a Codex or unified patch from stdin, `--dry-run` previews any of them, `ax diff` shows your changes.
Stale anchors, edits that break the syntax and failed patches write nothing and show you the current lines. Every command ends with one line saying what was cut and how to narrow.
";

pub const ENV: &str = "\
AX_NO_CAPS=1         no hit / window / line caps
AX_NO_ANCHORS=1      plain `12  code` lines; edits take bare line numbers
AX_NO_SYMBOLS=1      no `@ symbol` headers in grep/refs
AX_NO_PARSE_CHECK=1  edits/writes/patches skip the tree-sitter guard
AX_NO_RELOCATE=1     moved anchors are refused instead of found again
AX_MAX_HITS=n        hit cap for grep/find/refs/def (50)
AX_READ_WINDOW=n     lines per read window (200)
AX_LONG_FILE=n       files longer than this get outline + window (300)
AX_MAX_BYTES=n       text output cap per call, cut at line boundaries (24000)
AX_LOG=<file>        append one json line per call
";

pub fn run(env: bool) -> Report {
    let mut r = Report::new("agent-help");
    let text = if env { ENV } else { NOTE };
    r.lines = text.lines().map(str::to_string).collect();
    r.summary = Summary::plain(if env {
        "knobs are read per call; unset means default."
    } else {
        "paste this into AGENTS.md or CLAUDE.md."
    });
    r.data = json!({ "text": text });
    r
}
