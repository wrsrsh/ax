# ax across models and tool modes

held-out hono tasks, codex 0.156.0, medium effort, ax `6873380`, the main run's note. paired by task, 10k bootstrap, 95% CIs. costs on the corrected formula (cache writes bill once). `REPORT.md` (astra) and `REPORT.luna.md` (luna) have the full tables; `long_session.md` has the chained runs.

| | astra A/B/C (3 reps) | astra raw Ar/Br/Cr (1 rep) | luna A/B/C (3 reps) |
|---|---|---|---|
| pass A | 98.3% (95.0%–100.0%) | 97.5% (92.5%–100.0%) | 100.0% (100.0%–100.0%) |
| pass B | 98.3% (95.0%–100.0%) | 97.5% (92.5%–100.0%) | 97.5% (93.3%–100.0%) |
| pass C | 98.3% (95.0%–100.0%) | 97.5% (92.5%–100.0%) | 99.2% (97.5%–100.0%) |
| tokens B/A | 0.94x (0.90–1.03) | 0.83x (0.73–0.93) | 1.69x (1.54–1.95) |
| cost B/A | 0.95x (0.90–0.97) | 0.89x (0.85–0.96) | 1.51x (1.42–1.67) |
| tool calls B/A | 1.04x (1.00–1.14) | 0.80x (0.71–0.89) | 1.87x (1.60–2.00) |
| wall B/A | 1.02x (0.98–1.08) | 0.98x (0.86–1.04) | 1.76x (1.54–1.91) |
| cost C/A | 0.94x (0.90–0.96) | 0.87x (0.81–0.94) | 1.49x (1.34–1.67) |

code mode itself (same letter, raw / code mode, astra):

| | tokens | cost | tool calls | wall |
|---|---|---|---|---|
| Ar/A | 1.65x (1.33–1.74) | 1.13x (1.05–1.16) | 0.80x (0.71–0.84) | 1.53x (1.34–1.61) |
| Br/B | 1.35x (1.21–1.43) | 1.05x (1.01–1.11) | 0.61x (0.54–0.67) | 1.36x (1.29–1.44) |
| Cr/C | 1.30x (1.17–1.40) | 1.03x (0.97–1.09) | 0.58x (0.57–0.63) | 1.37x (1.23–1.46) |

## what it says

- astra (the strong model): pass rate at the ceiling everywhere; ax is 5-6% cheaper with intervals that clear 1.0, otherwise a wash.
- code mode off: stock codex gets 13% dearer and 1.5x slower without its js tool (fewer, fatter turns); with ax on the path the penalty is 5%. ax's edge over stock holds in the raw family too.
- luna (the cheap model): also at the ceiling in A (100%), and ax makes it 1.5x dearer, 1.7x more tokens, 1.9x more tool calls. it adopts ax fully but produces bad anchors and flags ax doesn't take (`grep -n`, several files to one `ax edit`, `find <glob> <dir>`): 81 refusals and 200+ usage errors per 120 runs that astra never hit. the refusals are correct; the retries are the cost.
- so the sign of the effect depends on the model: a small win for a model that uses the tool cleanly, a real loss for one that doesn't. the usage-error half of luna's overhead is addressable (some already is: find paths, grep -m; `grep -n` and one-file-per-edit are the next two).
