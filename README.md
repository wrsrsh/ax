# ax

one little cli for the stuff coding agents do all day: look around a repo, find files, grep, read, edit.

the bet is that agents burn a lot of tokens and turns on clumsy file work (cat the whole file, grep with no context, retry a botched str_replace three times). ax tries to make each of those one bounded, anchored call. every line it prints looks like `14:a3f1  code` so edits can point at exact lines and get refused if the file moved under them.

then we actually check whether it helps. `eval/` runs codex on real tasks from a real repo with and without ax and counts what happens. if it doesn't help we'll say so.

## commands

- `ax map` – one-screen overview of a repo
- `ax find` – files by name or rg-style glob
- `ax grep` – rg-compatible search, hits grouped by file and enclosing function
- `ax outline`, `ax def`, `ax refs` – symbols, name-based
- `ax read` – files or line ranges, with `LINE:HASH` anchors
- `ax edit` – anchored edit ops from stdin
- `ax write` – a whole file from stdin (`--if <hash>` to overwrite)
- `ax patch` – a codex or unified patch from stdin
- `ax diff` – git status, stat and capped hunks
- `ax agent-help` – the note that goes in AGENTS.md (`--env` lists the `AX_*` knobs)

`--json` works everywhere, `--dry-run` on edit/write/patch.

## eval

every step is `uv run python -m ax_eval.<step>` from `eval/`. `mine` pulls merged hono PRs and splits each diff into a gold patch and hidden tests. `validate` runs those in docker and keeps tasks with real fail-to-pass tests. `statements` writes the instructions and the dev/held-out split. `runner` runs codex on each task per setup (`eval/setups` has the ax note and a placebo matched to it in tokens; `Ar`/`Br`/`Cr` are the same three with codex's code mode off, see `eval/report/codex_tools.md`). `grade` applies the agent's diff plus the hidden tests in a fresh container, and the hidden tests always win. `table` and `report` turn the runs into numbers. `fakeapi` stands in for the model so all of it can run without api calls, and `parity` / `patch_parity` check ax against rg and git apply. `chains` + `longrun` are the long-session version: a few tasks back to back in one codex thread, with the files changing under the agent in between (`eval/report/long_session_design.md`). output goes to `eval/tasks`, `eval/runs` and `eval/report`.

## dev

```
cd ax && cargo test
cd eval && uv run --dev pytest
```

the grade tests skip unless docker, the task images and `eval/.cache/hono-full` are around; the capture test needs codex.

planning + tracking lives in linear (team hug, project "ax: agent file CLI + benchmark"), not here. the code in here is just code.
