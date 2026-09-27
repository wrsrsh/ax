## ax
`ax` is installed. Use it instead of cat/sed/grep/find/apply_patch to read, search and edit files.
- `ax read <path[:a-b]>...` many files or ranges in one call. long files show an outline + the first 200 lines.
- `ax grep <pattern> [paths]` takes rg flags (-F -w -i -t -g -C -l -c -m); hits are grouped by file and function. `ax find <name|glob> [paths]` lists files.
- `ax outline <file|dir>...`, `ax def <sym>`, `ax refs <sym>`: symbols. name-based, not type-aware.
- `ax map [path]`: optional overview when you don't know the repo.
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
`ax edit` echoes only the changed lines, with new anchors. `ax write <path> --if <hash>` replaces a whole file (new files need no --if), `ax patch` applies a Codex or unified patch from stdin, `--dry-run` previews any of them.
Check your work with `ax diff --stat`, and `ax diff <path>` for one file's hunks.
Stale anchors, syntax-breaking edits and failed patches write nothing and show the current lines. Every command ends with one line saying what was cut and how to narrow.
