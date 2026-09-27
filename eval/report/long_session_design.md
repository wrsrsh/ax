# long sessions: does ax's safety stuff ever fire?

## why this and not the ablation

the main run (360 held-out runs, codex 0.156.0 on gpt-6-astra, medium) says ax is about a wash on pass rate (98.3% everywhere) and a bit cheaper (B/A cost 0.95x). what it can't say anything about is the part of ax that's supposed to matter most: hash anchors, relocation, stale-edit refusals, the parse guard. across 120 B runs they refused 0 edits and relocated 0; C had 4 rejections. that's not because they work silently, it's because nothing ever goes stale: a run is ~60 s, the model reads a file and edits it two turns later, and nobody else touches the tree.

the per-feature ablation planned for m7 would turn those features off one at a time on the same tasks. it would measure nothing, because the features don't fire on these tasks. so instead: make sessions long and make the files move.

## the setup

a **chain** is 2-4 tasks from `tasks/final.jsonl` done back to back by one agent, in one container and one codex thread:

1. step 0: `codex exec` with task 1's instruction, like the main runner.
2. the harness applies a **world change** to the checkout.
3. step 1: `codex exec resume <thread>` with task 2's instruction. the model still has everything it read in step 0 in context, and some of that is now wrong.
4. repeat until the chain is done.

the model is never told the world changed. the prompt for each step is just that task's instruction, same text as in the main run. that's on purpose: an agent in a real repo doesn't get told when a teammate pushed or a formatter hook ran.

setups are A (stock codex + placebo note) vs B (stock codex + ax). C can run too, but A vs B is the comparison.

### chains (`ax_eval.chains`, `tasks/chains.jsonl`)

no two tasks in final.jsonl share a base commit, so a chain runs at an **anchor**: the base of its earliest task (by pr). a candidate chain is kept only if, in a container of the shared task image (one lockfile, so one image per chain):

- no task's fix commit is already an ancestor of the anchor,
- every gold patch applies on top of the ones before it (and on top of any upstream diff in between),
- every hidden test patch applies with its files reset to the anchor.

then `--validate` reruns the hidden tests at the anchor for every step, the same way `validate.py` does (1 run without the fix, 3 with, network off), with the earlier steps' gold patches in place. each step gets its own fail-to-pass / pass-to-pass lists, and an `at_end` list: the tests that still pass once the whole chain's golds are in (that's what regressions are checked against, so a later task legitimately changing behaviour doesn't count against an earlier one). a chain with a step that has no fail-to-pass left is dropped, and retried once without that step.

pairs that share a source file are tried first, then chains grow greedily to 4. every task is in at most one chain.

result: **17 chains, 41 of the 50 tasks** (12 of length 2, 3 of length 3, 2 of length 4), over all 6 task images. 6 chains have consecutive tasks that edit the same file (`src/client/client.ts` three times, `ipaddr.ts`, `accept.ts`, `jsx/dom/render.ts`). one 4-chain lost a step in validation (hono-5204 has no fail-to-pass test once hono-5179's fix is in) and came back as a 3-chain. rebuild with:

```
cd eval && uv run python -m ax_eval.chains --validate --jobs 4   # ~5 min, $0
```

### world changes

one per gap between steps, rotated by chain index, 24 in total:

| kind | what it does | count |
|---|---|---|
| `insert` | a 3-line comment block at the top of each file, and above the top-level declaration enclosing each of the agent's earlier edits (mid-file for files it hasn't touched). only goes above lines that start a top-level declaration at column 0, and keeps doc comments attached, so it can't land inside an expression. every line number below it shifts by 3+ | 10 (3 are fallbacks from upstream) |
| `fmt` | `node_modules/.bin/prettier --write --print-width 60` (offline, the repo's own prettier) over the chain's files plus whatever the agent touched. rewraps a lot of lines, so both line numbers and line contents change | 9 |
| `upstream` | a real later hono commit's diff (src files only, <= 80 lines) that touches the files done so far and isn't one of the chain's fixes. chosen so every later gold patch still applies after it, and it's part of the validated reference state, so its behaviour change is accounted for. never scheduled after a fmt in the same chain (it can't land on rewrapped code). on the agent's tree it's `git apply`, then a per-file 3-way `git merge-file` against the commit's parent, all or nothing; if the agent's edits conflict with it, the harness does an insert instead and `world.json` says so | 5 |

the file set is the chain's source files plus anything the agent edited, so the files the model has already read are the ones that move. insert and fmt don't change behaviour, so they're left out of the validation reference (prettier is behaviour-preserving; the insert is comments at declaration boundaries). upstream is in it. the dry runs back that up: across 164 graded steps (stub and fake api, every chain, A and B) no pass-to-pass test broke.

### `--jolt`: files moving mid-step

between-step changes only bite if the model reuses what it remembers from an earlier step. with `--jolt` the harness also inserts the comment block into a task file right after the agent's first successful read of it (ax read, cat, sed, head, ...), once per step. that's the case ax's anchors are actually built for: read at turn t, the file changes, edit at turn t+2. it's a separate arm, not mixed into the main one. with a real model there are seconds between the read and the next request, so the harness wins the race; against the fake api it sometimes doesn't, which doesn't matter there.

### running it (`ax_eval.longrun`)

reuses the main runner's container setup, isolation probe, drive loop, ledger and budget code (imported from `runner.py`; `start_container` and `probe` were pulled out of `run_one` for that). per chain run:

- one container at the anchor, probe checks every hidden test file of every step is absent.
- after each step, the working tree is snapshotted as an unreferenced commit (temp index, `git commit-tree`), so the agent's index and refs aren't touched. `final.diff` = anchor to snapshot (what gets graded), `delta.diff` = this step only (world changes excluded).
- `codex exec resume` in 0.156.0 has no `-C`, so it runs with `docker exec -w /w`; the session has to be on disk, so no `--ephemeral`. everything else is the main runner's flags.
- `turn.completed` usage after a resume is the thread's running total (checked against the fake api: 3600 after step 0, 8400 after step 1 = 3600 + 4 x 1200), so per-step tokens and cost are the difference to the step before. thread totals are kept as `thread_*`.
- grading: each step's cumulative diff goes through `grade.grade` in a fresh container at the anchor with that step's own test lists (hidden tests win, same as the main run). the agent's container never sees a hidden test, and a later step can't change an earlier step's grade. at the end every earlier step is graded again on the last diff, against its `at_end` tests.
- ledger: one row per step in `runs/ledger.jsonl`, tagged with `chain`, so the $2,000 cap covers both benchmarks. a chain is reserved against the budget as est x its longest length. `est_from_ledger` keeps chain steps and single runs apart.
- an infra failure anywhere retries the whole chain under a new run id (the old dir stays, `retried_as` set), same as the main runner.

## metrics, per step

| metric | where it comes from |
|---|---|
| pass rate by position in the chain | `resolved` per step; compare A vs B at the same position |
| stale-anchor refusals | AX_LOG outcomes `stale` / `ambiguous` (B). A's nearest thing is failed `apply_patch` calls (context didn't match), reported as `failed_patches` |
| relocations | AX_LOG `relocated`: ax found the moved line and applied the edit there |
| wrong-place edits | `target_check`: each gold hunk is located in the file as it was when the step started (matching letters/digits only, so a reformat doesn't lose it); each agent hunk is on target if it's within 15 lines of one, off target if not or in a file the gold patch doesn't touch. `wrong_place` = off-target hunks and the step's tests fail. raw `off_target` / `on_target` / `unlocated` hunk counts are kept too |
| clobbered earlier edits | `regressed`: the step passed at its own end but its `at_end` tests fail on the last diff. `touched_prior_lines`: lines this step removed that an earlier step of the agent had added (text match, whitespace-blind) |
| tokens / cost per step | per-step usage as above; `input_tokens`, `cached_input_tokens`, `output_tokens`, `cost` |

`uv run python -m ax_eval.longrun --summarize` prints one row per (setup, position).

## what this can show, and what it can't

it can show whether, once files really do move under the agent, ax's anchors do anything visible: how often B's edits get refused or relocated, whether A's edits land in the wrong place more, whether either setup breaks an earlier step's work, and what that costs per step.

it can't show:

- **that it happens in the wild.** the world changes are synthetic. insert is filler comments; a print-width of 60 isn't anyone's style. only upstream is real code. this is a stress test with a known mechanism, not a sample of real sessions.
- **much about pass rate.** single tasks sit at 98%. chains might pull that down, but with 17 chains x 2 setups x 3 repeats a few points either way is noise. the event counts are the point.
- **anything if the model just re-reads.** if gpt-6-astra re-reads every file before editing it after a new prompt, stale anchors never happen in either setup. that's a real answer too ("the machinery doesn't matter for this model"), and `--jolt` is there to push past it.
- **A's staleness directly.** there's no refusal in A: sed and python edits land silently, apply_patch fails on context. A's side is `failed_patches` + wrong-place + regressions, which is indirect.
- **wrong-place precisely.** it's a heuristic: a model refactoring near but outside the gold hunks counts as off target, a reformat can make a gold hunk unlocatable (`unlocated`), and "off target and failing" isn't proof the edit went to the wrong line. read the flagged steps by hand before claiming anything.

confounds:

- **context growth.** step k carries steps 0..k-1 in context. cost, tokens and maybe pass rate change with position for reasons that have nothing to do with ax, so only compare A vs B at the same position, never step 0 vs step 3.
- **task order.** chains are always in pr order, since the anchor has to be the earliest base. a harder task late in a chain looks like a long-context effect. with 2-4 steps and fixed order there's no counterbalancing; per-position results are per-task-position, not "late in a session" in general.
- **what the world change hits.** most chains (11/17) have consecutive tasks in different files, so a between-step change only matters if the model reuses an earlier read. the 6 same-file chains and `--jolt` carry most of the signal; report them separately.
- **the main run's tool-surface confound still applies.** A edits with codex's native apply_patch, B goes through the shell into ax.
- **dev tasks.** 10 of the 41 chain tasks are dev-split tasks (the main report was held-out only). they were used for piloting, not tuned on, and pass rate is at the ceiling anyway, but it's a difference from the main run.
- **prettier's noise.** fmt makes the graded diff large. it doesn't change behaviour, but it does make `delta.diff` and the clobber text match noisier for the step after a fmt.

## dry runs ($0)

- `chains --validate`: 17 chains, 41 tasks, every step with fail-to-pass tests at the anchor. ~5 min.
- stub agent, all 17 chains x A and B (`longrun --agent stub --parallel 3`): 34 chain runs, 82 steps, 0 infra failures, every grade clean (no errors, no broken pass-to-pass).
- codex against the fake api, all 17 chains x A and B (`longrun --agent codex --dry-run --parallel 3`): 34 chain runs, 82 steps, 0 infra failures. that exercises exec + resume, every world change kind, per-step grading and the end-of-chain regrade. world changes as applied: 20 insert, 18 fmt, 6 upstream clean, 4 upstream fell back to insert (chain-04 and chain-14, where the fake's edit, always appended at the end of the file, sits right where the upstream diff lands).
- the fake script makes step k's second edit from what step k-1 read, which is the thing that should go stale. over the 24 such edits in B, the remembered anchor is always line 3: after an insert ax relocated 10, refused 1 as ambiguous, 1 was fine; after a fmt it refused 1 as stale and 8 were fine (line 3 is usually an import prettier leaves alone); after an upstream diff all 3 were fine. a real model's anchors will be spread over the file, so expect more of them to move. A's `sed -i '3a ...'` from the remembered line number never fails, it just lands wherever line 3 is now; on chain-00 that's inside the harness's comment block. so the counters do move once the world does, which is the whole point, and A's side really is silent.
- usage per step on chain-00: 3600 / 4800 input tokens (thread totals 3600 / 8400).
- tests: `tests/test_chains.py`, `tests/test_longrun.py`: pure parts, plus in docker a stub chain per setup, a stub chain per fmt/upstream world change (pass-to-pass must survive it) and a fake-api codex chain (per-step usage, relocation fires). docker ones skip without the images.

## the paid run

needs the gate approved first. same api as the main run (manifests there have `--api-base-url https://saturday.services.ai.azure.com/openai/v1`), run from the main checkout so the budget reads the real ledger:

```
cd eval
uv run python -m ax_eval.longrun --chains all --setups A B --repeats 3 --seed 7 \
  --agent codex --paid --api-base-url https://saturday.services.ai.azure.com/openai/v1 --env-key <the main run's key var> \
  --turn-cap 60 --est 1.5 --parallel 3
```

cost: 17 chains x 2 setups x 3 repeats = 102 chain runs, 246 steps. at the $1/step prior that's ~$246. later steps carry more context (mostly cached input), so $1.5/step is the conservative number the budget gate is given: ~$370 worst case. the `--jolt` arm is the same size again (~$246, add `--jolt` and a separate `--runs-dir`). a 1-repeat smoke first (82 steps, ~$82) is the cheap way to see whether anything fires at all before paying for repeats.
