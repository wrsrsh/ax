# ax

one little cli for the stuff coding agents do all day: look around a repo, find files, grep, read, edit.

the bet is that agents burn a lot of tokens and turns on clumsy file work (cat the whole file, grep with no context, retry a botched str_replace three times). ax tries to make each of those one bounded, anchored call. every line it prints looks like `14:a3f1  code` so edits can point at exact lines and get refused if the file moved under them.

then we actually check whether it helps. `eval/` runs claude code on real tasks from a real repo with and without ax and counts what happens. if it doesn't help we'll say so.

## layout

- `ax/` – the rust crate
- `eval/` – python (uv): task miner, runner, parsers, stats
- `eval/tasks`, `eval/runs`, `eval/report` – generated stuff

## dev

```
cd ax && cargo test
cd eval && uv run --dev pytest
```

planning + tracking lives in linear (team hug, project "ax: agent file CLI + benchmark"), not here. the code in here is just code.
