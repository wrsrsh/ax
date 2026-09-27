# long-session eval: results

17 chains (41 tasks) of 2-4 hono tasks run in one codex thread each, gpt-6-astra medium, ax `6873380`, the main run's note. between steps the checkout changes (insert / prettier / a real upstream diff). the jolt arm also edits a task file right after the agent's first read of it, mid-step. 1 rep each; A = stock codex, B = ax. ledger costs use the corrected formula. `ax_eval.longrun --summarize --runs-dir <dir>` regenerates the tables from `runs-long/` and `runs-long-jolt/` (gitignored, kept locally).

## between-step changes only

| setup | step | n | pass | regressed | stale | relocated | ambiguous | failed patches | off-target hunks (heuristic) | wrong place | mean $ | mean input tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 0 | 17 | 94.1% | 0 | 0 | 0 | - | 0 | 3 | 0 | 0.81 | 279,796 |
| A | 1 | 17 | 100.0% | 0 | 0 | 0 | - | 0 | 4 | 0 | 0.54 | 288,344 |
| A | 2 | 5 | 100.0% | 0 | 0 | 0 | - | 0 | 2 | 0 | 0.69 | 404,165 |
| A | 3 | 2 | 100.0% | 0 | 0 | 0 | - | 0 | 0 | 0 | 0.73 | 472,569 |
| B | 0 | 17 | 94.1% | 0 | 2 | 0 | - | 0 | 3 | 0 | 0.76 | 266,886 |
| B | 1 | 17 | 100.0% | 0 | 0 | 0 | - | 0 | 6 | 0 | 0.61 | 332,288 |
| B | 2 | 5 | 100.0% | 0 | 0 | 0 | - | 0 | 2 | 0 | 0.78 | 502,135 |
| B | 3 | 2 | 100.0% | 0 | 0 | 0 | - | 0 | 1 | 0 | 0.71 | 429,132 |

ax outcomes across all B steps: {'stale': 2, 'relocated': 0, 'ambiguous': 0}

## plus mid-step jolts

| setup | step | n | pass | regressed | stale | relocated | ambiguous | failed patches | off-target hunks (heuristic) | wrong place | mean $ | mean input tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 0 | 17 | 94.1% | 0 | 0 | 0 | - | 0 | 3 | 0 | 0.84 | 295,038 |
| A | 1 | 17 | 100.0% | 0 | 0 | 0 | - | 0 | 6 | 0 | 0.57 | 309,887 |
| A | 2 | 5 | 100.0% | 0 | 0 | 0 | - | 0 | 2 | 0 | 0.69 | 438,004 |
| A | 3 | 2 | 100.0% | 0 | 0 | 0 | - | 0 | 0 | 0 | 0.70 | 458,884 |
| B | 0 | 17 | 94.1% | 0 | 1 | 9 | - | 0 | 3 | 0 | 0.73 | 240,109 |
| B | 1 | 17 | 100.0% | 0 | 0 | 9 | - | 0 | 17 | 0 | 0.60 | 327,776 |
| B | 2 | 5 | 100.0% | 0 | 0 | 3 | - | 0 | 2 | 0 | 0.73 | 439,323 |
| B | 3 | 2 | 100.0% | 0 | 1 | 1 | - | 0 | 0 | 0 | 0.84 | 510,444 |

ax outcomes across all B steps: {'stale': 2, 'relocated': 22, 'ambiguous': 5}

## reading

- pass rate is identical in A and B in both arms (80/82 steps; the two misses are hono-5340 at step 0, the task that fails in every batch). 0 regressions of earlier steps, 0 clobbered lines, 0 wrong-place edits by the strict check in either setup or arm.
- without jolts nothing fires: the model re-reads before it edits, so changes between turns never reach an edit.
- with jolts the machinery engages in B: relocation fired 22 times, plus 2 stale and 5 ambiguous refusals, all recovered within the step. A shows 0 failed apply_patch calls in the same situations: codex's native patch tool matches on context lines, so an insertion above the edit doesn't break it either.
- so: ax's anchors and relocation work as designed under churn, and on this model they buy nothing over apply_patch's context matching. the off-target-hunk counts are the position heuristic reacting to inserted lines, not misplaced edits.
- later steps cost less than step 0 (context is mostly cached); B stays a little cheaper than A at every position in both arms except step 3 with jolts (n=2).
