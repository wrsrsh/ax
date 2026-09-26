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
