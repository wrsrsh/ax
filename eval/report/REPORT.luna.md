# ax eval report

generated 2026-09-28 from `runs/runs.jsonl`.

- agent: codex, codex codex-cli 0.156.0
- model: gpt-6-luna, effort medium
- ax commit: 15e61f1b8778a8713cc9e1bf0d424930b3379512, 2623aca190189dd4243052679f82d75cc0bcc0c4-dirty, 687338073221047ba63e22c2aea3a05148a423d1, 893530a822398f5c56b6c0241ab7c3c947ec4ca6-dirty
- tasks: 50 in final.jsonl (10 dev, 40 held-out); 40 with usable runs here
- runs: 850 real (28 dry runs ignored), 849 usable, 360 in this report (heldout split, model gpt-6-luna), 1 infra failures, 0 incomplete, 0 timed out (counted as unresolved)
- setups: A, B, C. A is the baseline (Ar for the raw-tools family); ratios and deltas are paired by task against it.

## summary

| setup | runs | tasks | pass rate | 95% CI | median tokens | median cost | median turns | median wall s |
|---|---|---|---|---|---|---|---|---|
| A | 120 | 40 | 100.0% | 100.0% to 100.0% | 237,642 | $0.007 | 9.0 | 62.5 |
| B | 120 | 40 | 97.5% | 93.3% to 100.0% | 410,560 | $0.010 | 17.5 | 105.0 |
| C | 120 | 40 | 99.2% | 97.5% to 100.0% | 408,857 | $0.010 | 16.0 | 106.5 |

pass rate by split:

| setup | dev | held-out |
|---|---|---|
| A | 100.0% (3/3) | 99.2% (238/240) |
| B | 100.0% (3/3) | 97.9% (235/240) |
| C | 100.0% (3/3) | 98.8% (237/240) |

## guardrail

- B: FAILED. pass rate -2.5 pp vs A, 95% CI -6.7 to +0.0 pp; allowed loss 5 pp.
- C: ok. pass rate -0.8 pp vs A, 95% CI -2.5 to +0.0 pp; allowed loss 5 pp.

## ratios vs baseline

median over tasks of (setup mean / baseline mean); below 1 means the ax setup used less.

| comparison | metric | median ratio | 95% CI | tasks |
|---|---|---|---|---|
| B/A | tokens | 1.69x | 1.54x to 1.95x | 40 |
| B/A | cost | 1.51x | 1.42x to 1.67x | 40 |
| B/A | turns | 1.87x | 1.60x to 2.00x | 40 |
| B/A | wall_seconds | 1.76x | 1.54x to 1.91x | 40 |
| C/A | tokens | 1.76x | 1.56x to 2.06x | 40 |
| C/A | cost | 1.49x | 1.34x to 1.67x | 40 |
| C/A | turns | 1.74x | 1.56x to 1.87x | 40 |
| C/A | wall_seconds | 1.64x | 1.44x to 1.88x | 40 |

## cost breakdown

median $ per run for each token class; in brackets, that class's share of the setup's total spend.

| setup | uncached input | cached input | cache writes | output | median total |
|---|---|---|---|---|---|
| A | $0.000 (0.9%) | $0.002 (34.8%) | $0.004 (43.4%) | $0.001 (20.8%) | $0.007 |
| B | $0.000 (1.0%) | $0.004 (39.2%) | $0.004 (35.9%) | $0.002 (23.8%) | $0.010 |
| C | $0.000 (1.0%) | $0.004 (40.1%) | $0.004 (35.9%) | $0.002 (23.0%) | $0.010 |

cache-write tokens are 96.9% of uncached input tokens (median over runs): codex counts cache writes inside input_tokens, and they bill at the cache-write rate instead of the input rate, so the uncached column is what was neither cached nor written.

paired by task against the baseline, per token class:

| comparison | class | median ratio | 95% CI | tasks |
|---|---|---|---|---|
| B/A | uncached input | 1.63x | 1.50x to 1.74x | 40 |
| B/A | cached input | 1.77x | 1.60x to 2.06x | 40 |
| B/A | cache writes | 1.21x | 1.12x to 1.31x | 40 |
| B/A | output | 1.86x | 1.61x to 1.94x | 40 |
| C/A | uncached input | 1.62x | 1.47x to 1.85x | 40 |
| C/A | cached input | 1.84x | 1.60x to 2.15x | 40 |
| C/A | cache writes | 1.19x | 1.12x to 1.26x | 40 |
| C/A | output | 1.74x | 1.53x to 1.87x | 40 |

## adoption

fallback rate = share of file reads/searches/edits that didn't go through ax; script calls = inline python/node doing that work.

| setup | runs | runs using ax | median fallback rate | script calls | ax rejections | top ax commands |
|---|---|---|---|---|---|---|
| A | 120 | 0 (0.0%) | 100.0% | 11 | 0 | - |
| B | 120 | 120 (100.0%) | 0.9% | 1 | 81 | edit 727, read 580, diff 301, grep 250 |
| C | 120 | 120 (100.0%) | 0.6% | 8 | 109 | edit 749, read 562, diff 281, grep 258 |

## wins and losses

top 3 tasks per metric, by per-task ratio (or pass-rate delta) against the baseline.

### B vs A: resolved

- wins: none
- losses:
  - `hono-5379`: A 100.0%, B 33.3% (-67 pp); runs [A0](../runs/20260927T143849-hono-5379-A-r0-7740/events.jsonl) [A1](../runs/20260927T151345-hono-5379-A-r1-d5dd/events.jsonl) [A2](../runs/20260927T183006-hono-5379-A-r2-08e5/events.jsonl) [B0](../runs/20260927T180702-hono-5379-B-r0-31c8/events.jsonl) [B1](../runs/20260927T153944-hono-5379-B-r1-edce/events.jsonl) [B2](../runs/20260927T144416-hono-5379-B-r2-cb80/events.jsonl)
  - `hono-5256`: A 100.0%, B 66.7% (-33 pp); runs [A0](../runs/20260927T153630-hono-5256-A-r0-d8fd/events.jsonl) [A1](../runs/20260927T174436-hono-5256-A-r1-7596/events.jsonl) [A2](../runs/20260927T144454-hono-5256-A-r2-28cc/events.jsonl) [B0](../runs/20260927T152404-hono-5256-B-r0-ab3c/events.jsonl) [B1](../runs/20260927T143159-hono-5256-B-r1-506f/events.jsonl) [B2](../runs/20260927T180529-hono-5256-B-r2-9216/events.jsonl)

### B vs A: tokens

- wins:
  - `hono-5179`: A 1,713,364, B 0 (0.00x); runs [A0](../runs/20260927T152653-hono-5179-A-r0-8a46/events.jsonl) [A1](../runs/20260927T181237-hono-5179-A-r1-7d35/events.jsonl) [A2](../runs/20260927T151035-hono-5179-A-r2-0413/events.jsonl) [B0](../runs/20260927T181305-hono-5179-B-r0-3ec3/events.jsonl) [B1](../runs/20260927T164844-hono-5179-B-r1-b613/events.jsonl) [B2](../runs/20260927T153229-hono-5179-B-r2-3ffb/events.jsonl)
  - `hono-5094`: A 432,697, B 396,874 (0.92x); runs [A0](../runs/20260927T172223-hono-5094-A-r0-54c0/events.jsonl) [A1](../runs/20260927T162557-hono-5094-A-r1-ef3d/events.jsonl) [A2](../runs/20260927T171553-hono-5094-A-r2-a906/events.jsonl) [B0](../runs/20260927T163136-hono-5094-B-r0-df67/events.jsonl) [B1](../runs/20260927T165459-hono-5094-B-r1-b4c0/events.jsonl) [B2](../runs/20260927T155426-hono-5094-B-r2-f6da/events.jsonl)
  - `hono-5426`: A 227,095, B 226,695 (1.00x); runs [A0](../runs/20260927T183341-hono-5426-A-r0-c0dd/events.jsonl) [A1](../runs/20260927T154804-hono-5426-A-r1-e53d/events.jsonl) [A2](../runs/20260927T170619-hono-5426-A-r2-b45b/events.jsonl) [B0](../runs/20260927T150558-hono-5426-B-r0-15f5/events.jsonl) [B1](../runs/20260927T170337-hono-5426-B-r1-0e0d/events.jsonl) [B2](../runs/20260927T180852-hono-5426-B-r2-da28/events.jsonl)
- losses:
  - `hono-5020`: A 149,996, B 816,745 (5.45x); runs [A0](../runs/20260927T183303-hono-5020-A-r0-eae6/events.jsonl) [A1](../runs/20260927T144131-hono-5020-A-r1-224c/events.jsonl) [A2](../runs/20260927T161629-hono-5020-A-r2-174e/events.jsonl) [B0](../runs/20260927T172045-hono-5020-B-r0-aa74/events.jsonl) [B1](../runs/20260927T160709-hono-5020-B-r1-b922/events.jsonl) [B2](../runs/20260927T164733-hono-5020-B-r2-67c3/events.jsonl)
  - `hono-5204`: A 422,141, B 1,365,165 (3.23x); runs [A0](../runs/20260927T153927-hono-5204-A-r0-e13f/events.jsonl) [A1](../runs/20260927T173158-hono-5204-A-r1-5630/events.jsonl) [A2](../runs/20260927T182702-hono-5204-A-r2-edd2/events.jsonl) [B0](../runs/20260927T151727-hono-5204-B-r0-7742/events.jsonl) [B1](../runs/20260927T173514-hono-5204-B-r1-b812/events.jsonl) [B2](../runs/20260927T150655-hono-5204-B-r2-3568/events.jsonl)
  - `hono-5059`: A 123,992, B 345,556 (2.79x); runs [A0](../runs/20260927T163306-hono-5059-A-r0-b322/events.jsonl) [A1](../runs/20260927T153507-hono-5059-A-r1-973a/events.jsonl) [A2](../runs/20260927T174154-hono-5059-A-r2-4e97/events.jsonl) [B0](../runs/20260927T164926-hono-5059-B-r0-d6e7/events.jsonl) [B1](../runs/20260927T171415-hono-5059-B-r1-a7d7/events.jsonl) [B2](../runs/20260927T162438-hono-5059-B-r2-6495/events.jsonl)

### B vs A: cost

- wins:
  - `hono-5179`: A $0.027, B $0.000 (0.00x); runs [A0](../runs/20260927T152653-hono-5179-A-r0-8a46/events.jsonl) [A1](../runs/20260927T181237-hono-5179-A-r1-7d35/events.jsonl) [A2](../runs/20260927T151035-hono-5179-A-r2-0413/events.jsonl) [B0](../runs/20260927T181305-hono-5179-B-r0-3ec3/events.jsonl) [B1](../runs/20260927T164844-hono-5179-B-r1-b613/events.jsonl) [B2](../runs/20260927T153229-hono-5179-B-r2-3ffb/events.jsonl)
  - `hono-5426`: A $0.007, B $0.007 (0.96x); runs [A0](../runs/20260927T183341-hono-5426-A-r0-c0dd/events.jsonl) [A1](../runs/20260927T154804-hono-5426-A-r1-e53d/events.jsonl) [A2](../runs/20260927T170619-hono-5426-A-r2-b45b/events.jsonl) [B0](../runs/20260927T150558-hono-5426-B-r0-15f5/events.jsonl) [B1](../runs/20260927T170337-hono-5426-B-r1-0e0d/events.jsonl) [B2](../runs/20260927T180852-hono-5426-B-r2-da28/events.jsonl)
  - `hono-5094`: A $0.011, B $0.011 (0.96x); runs [A0](../runs/20260927T172223-hono-5094-A-r0-54c0/events.jsonl) [A1](../runs/20260927T162557-hono-5094-A-r1-ef3d/events.jsonl) [A2](../runs/20260927T171553-hono-5094-A-r2-a906/events.jsonl) [B0](../runs/20260927T163136-hono-5094-B-r0-df67/events.jsonl) [B1](../runs/20260927T165459-hono-5094-B-r1-b4c0/events.jsonl) [B2](../runs/20260927T155426-hono-5094-B-r2-f6da/events.jsonl)
- losses:
  - `hono-5020`: A $0.005, B $0.017 (3.47x); runs [A0](../runs/20260927T183303-hono-5020-A-r0-eae6/events.jsonl) [A1](../runs/20260927T144131-hono-5020-A-r1-224c/events.jsonl) [A2](../runs/20260927T161629-hono-5020-A-r2-174e/events.jsonl) [B0](../runs/20260927T172045-hono-5020-B-r0-aa74/events.jsonl) [B1](../runs/20260927T160709-hono-5020-B-r1-b922/events.jsonl) [B2](../runs/20260927T164733-hono-5020-B-r2-67c3/events.jsonl)
  - `hono-5204`: A $0.011, B $0.025 (2.38x); runs [A0](../runs/20260927T153927-hono-5204-A-r0-e13f/events.jsonl) [A1](../runs/20260927T173158-hono-5204-A-r1-5630/events.jsonl) [A2](../runs/20260927T182702-hono-5204-A-r2-edd2/events.jsonl) [B0](../runs/20260927T151727-hono-5204-B-r0-7742/events.jsonl) [B1](../runs/20260927T173514-hono-5204-B-r1-b812/events.jsonl) [B2](../runs/20260927T150655-hono-5204-B-r2-3568/events.jsonl)
  - `hono-5380`: A $0.011, B $0.024 (2.23x); runs [A0](../runs/20260927T152239-hono-5380-A-r0-ea02/events.jsonl) [A1](../runs/20260927T180304-hono-5380-A-r1-1276/events.jsonl) [A2](../runs/20260927T172703-hono-5380-A-r2-1313/events.jsonl) [B0](../runs/20260927T161659-hono-5380-B-r0-1ded/events.jsonl) [B1](../runs/20260927T174738-hono-5380-B-r1-7c41/events.jsonl) [B2](../runs/20260927T163004-hono-5380-B-r2-d047/events.jsonl)

### B vs A: turns

- wins: none
- losses:
  - `hono-5020`: A 6, B 25 (4.47x); runs [A0](../runs/20260927T183303-hono-5020-A-r0-eae6/events.jsonl) [A1](../runs/20260927T144131-hono-5020-A-r1-224c/events.jsonl) [A2](../runs/20260927T161629-hono-5020-A-r2-174e/events.jsonl) [B0](../runs/20260927T172045-hono-5020-B-r0-aa74/events.jsonl) [B1](../runs/20260927T160709-hono-5020-B-r1-b922/events.jsonl) [B2](../runs/20260927T164733-hono-5020-B-r2-67c3/events.jsonl)
  - `hono-5059`: A 6, B 19 (3.00x); runs [A0](../runs/20260927T163306-hono-5059-A-r0-b322/events.jsonl) [A1](../runs/20260927T153507-hono-5059-A-r1-973a/events.jsonl) [A2](../runs/20260927T174154-hono-5059-A-r2-4e97/events.jsonl) [B0](../runs/20260927T164926-hono-5059-B-r0-d6e7/events.jsonl) [B1](../runs/20260927T171415-hono-5059-B-r1-a7d7/events.jsonl) [B2](../runs/20260927T162438-hono-5059-B-r2-6495/events.jsonl)
  - `hono-5280`: A 7, B 21 (2.82x); runs [A0](../runs/20260927T150523-hono-5280-A-r0-86c3/events.jsonl) [A1](../runs/20260927T171945-hono-5280-A-r1-2993/events.jsonl) [A2](../runs/20260927T174716-hono-5280-A-r2-c7d2/events.jsonl) [B0](../runs/20260927T170824-hono-5280-B-r0-c6da/events.jsonl) [B1](../runs/20260927T150233-hono-5280-B-r1-07c8/events.jsonl) [B2](../runs/20260927T161434-hono-5280-B-r2-e07f/events.jsonl)

### B vs A: wall_seconds

- wins:
  - `hono-5102`: A 188.7, B 94.3 (0.50x); runs [A0](../runs/20260927T183117-hono-5102-A-r0-0503/events.jsonl) [A1](../runs/20260927T175959-hono-5102-A-r1-a13a/events.jsonl) [A2](../runs/20260927T163336-hono-5102-A-r2-0d54/events.jsonl) [B0](../runs/20260927T181506-hono-5102-B-r0-07d4/events.jsonl) [B1](../runs/20260927T174805-hono-5102-B-r1-60fc/events.jsonl) [B2](../runs/20260927T183650-hono-5102-B-r2-aa2d/events.jsonl)
  - `hono-5292`: A 91.7, B 73.3 (0.80x); runs [A0](../runs/20260927T170246-hono-5292-A-r0-4ca1/events.jsonl) [A1](../runs/20260927T163048-hono-5292-A-r1-4954/events.jsonl) [A2](../runs/20260927T151036-hono-5292-A-r2-d9be/events.jsonl) [B0](../runs/20260927T161653-hono-5292-B-r0-3cb4/events.jsonl) [B1](../runs/20260927T153820-hono-5292-B-r1-bc1c/events.jsonl) [B2](../runs/20260927T155941-hono-5292-B-r2-f60a/events.jsonl)
  - `hono-5092`: A 148.0, B 146.0 (0.99x); runs [A0](../runs/20260927T173815-hono-5092-A-r0-a965/events.jsonl) [A1](../runs/20260927T160156-hono-5092-A-r1-6346/events.jsonl) [A2](../runs/20260927T150400-hono-5092-A-r2-3b1e/events.jsonl) [B0](../runs/20260927T164750-hono-5092-B-r0-269b/events.jsonl) [B1](../runs/20260927T161533-hono-5092-B-r1-8244/events.jsonl) [B2](../runs/20260927T162158-hono-5092-B-r2-7c93/events.jsonl)
- losses:
  - `hono-5020`: A 34.0, B 187.3 (5.51x); runs [A0](../runs/20260927T183303-hono-5020-A-r0-eae6/events.jsonl) [A1](../runs/20260927T144131-hono-5020-A-r1-224c/events.jsonl) [A2](../runs/20260927T161629-hono-5020-A-r2-174e/events.jsonl) [B0](../runs/20260927T172045-hono-5020-B-r0-aa74/events.jsonl) [B1](../runs/20260927T160709-hono-5020-B-r1-b922/events.jsonl) [B2](../runs/20260927T164733-hono-5020-B-r2-67c3/events.jsonl)
  - `hono-5380`: A 68.7, B 258.0 (3.76x); runs [A0](../runs/20260927T152239-hono-5380-A-r0-ea02/events.jsonl) [A1](../runs/20260927T180304-hono-5380-A-r1-1276/events.jsonl) [A2](../runs/20260927T172703-hono-5380-A-r2-1313/events.jsonl) [B0](../runs/20260927T161659-hono-5380-B-r0-1ded/events.jsonl) [B1](../runs/20260927T174738-hono-5380-B-r1-7c41/events.jsonl) [B2](../runs/20260927T163004-hono-5380-B-r2-d047/events.jsonl)
  - `hono-5205`: A 62.0, B 195.7 (3.16x); runs [A0](../runs/20260927T150123-hono-5205-A-r0-d891/events.jsonl) [A1](../runs/20260927T160215-hono-5205-A-r1-c4ea/events.jsonl) [A2](../runs/20260927T143204-hono-5205-A-r2-d960/events.jsonl) [B0](../runs/20260927T153819-hono-5205-B-r0-4db3/events.jsonl) [B1](../runs/20260927T154716-hono-5205-B-r1-d9b8/events.jsonl) [B2](../runs/20260927T163656-hono-5205-B-r2-ff58/events.jsonl)

### C vs A: resolved

- wins: none
- losses:
  - `hono-5379`: A 100.0%, C 66.7% (-33 pp); runs [A0](../runs/20260927T143849-hono-5379-A-r0-7740/events.jsonl) [A1](../runs/20260927T151345-hono-5379-A-r1-d5dd/events.jsonl) [A2](../runs/20260927T183006-hono-5379-A-r2-08e5/events.jsonl) [C0](../runs/20260927T172958-hono-5379-C-r0-d841/events.jsonl) [C1](../runs/20260927T172802-hono-5379-C-r1-ec09/events.jsonl) [C2](../runs/20260927T143718-hono-5379-C-r2-68b5/events.jsonl)

### C vs A: tokens

- wins:
  - `hono-5179`: A 1,713,364, C 0 (0.00x); runs [A0](../runs/20260927T152653-hono-5179-A-r0-8a46/events.jsonl) [A1](../runs/20260927T181237-hono-5179-A-r1-7d35/events.jsonl) [A2](../runs/20260927T151035-hono-5179-A-r2-0413/events.jsonl) [C0](../runs/20260927T144947-hono-5179-C-r0-4c36/events.jsonl) [C1](../runs/20260927T163557-hono-5179-C-r1-26f5/events.jsonl) [C2](../runs/20260927T173145-hono-5179-C-r2-d700/events.jsonl)
- losses:
  - `hono-5110`: A 193,731, C 566,360 (2.92x); runs [A0](../runs/20260927T181314-hono-5110-A-r0-c62c/events.jsonl) [A1](../runs/20260927T143036-hono-5110-A-r1-d679/events.jsonl) [A2](../runs/20260927T172702-hono-5110-A-r2-31a5/events.jsonl) [C0](../runs/20260927T153144-hono-5110-C-r0-a168/events.jsonl) [C1](../runs/20260927T173820-hono-5110-C-r1-5822/events.jsonl) [C2](../runs/20260927T171023-hono-5110-C-r2-29eb/events.jsonl)
  - `hono-5283`: A 277,038, C 785,909 (2.84x); runs [A0](../runs/20260927T145249-hono-5283-A-r0-fede/events.jsonl) [A1](../runs/20260927T144751-hono-5283-A-r1-6808/events.jsonl) [A2](../runs/20260927T153403-hono-5283-A-r2-7f12/events.jsonl) [C0](../runs/20260927T174605-hono-5283-C-r0-3a5c/events.jsonl) [C1](../runs/20260927T174454-hono-5283-C-r1-d38d/events.jsonl) [C2](../runs/20260927T182910-hono-5283-C-r2-9d54/events.jsonl)
  - `hono-5020`: A 149,996, C 405,055 (2.70x); runs [A0](../runs/20260927T183303-hono-5020-A-r0-eae6/events.jsonl) [A1](../runs/20260927T144131-hono-5020-A-r1-224c/events.jsonl) [A2](../runs/20260927T161629-hono-5020-A-r2-174e/events.jsonl) [C0](../runs/20260927T162334-hono-5020-C-r0-1b72/events.jsonl) [C1](../runs/20260927T173521-hono-5020-C-r1-19cc/events.jsonl) [C2](../runs/20260927T164319-hono-5020-C-r2-f185/events.jsonl)

### C vs A: cost

- wins:
  - `hono-5179`: A $0.027, C $0.000 (0.00x); runs [A0](../runs/20260927T152653-hono-5179-A-r0-8a46/events.jsonl) [A1](../runs/20260927T181237-hono-5179-A-r1-7d35/events.jsonl) [A2](../runs/20260927T151035-hono-5179-A-r2-0413/events.jsonl) [C0](../runs/20260927T144947-hono-5179-C-r0-4c36/events.jsonl) [C1](../runs/20260927T163557-hono-5179-C-r1-26f5/events.jsonl) [C2](../runs/20260927T173145-hono-5179-C-r2-d700/events.jsonl)
- losses:
  - `hono-5110`: A $0.006, C $0.013 (2.23x); runs [A0](../runs/20260927T181314-hono-5110-A-r0-c62c/events.jsonl) [A1](../runs/20260927T143036-hono-5110-A-r1-d679/events.jsonl) [A2](../runs/20260927T172702-hono-5110-A-r2-31a5/events.jsonl) [C0](../runs/20260927T153144-hono-5110-C-r0-a168/events.jsonl) [C1](../runs/20260927T173820-hono-5110-C-r1-5822/events.jsonl) [C2](../runs/20260927T171023-hono-5110-C-r2-29eb/events.jsonl)
  - `hono-5283`: A $0.008, C $0.017 (2.20x); runs [A0](../runs/20260927T145249-hono-5283-A-r0-fede/events.jsonl) [A1](../runs/20260927T144751-hono-5283-A-r1-6808/events.jsonl) [A2](../runs/20260927T153403-hono-5283-A-r2-7f12/events.jsonl) [C0](../runs/20260927T174605-hono-5283-C-r0-3a5c/events.jsonl) [C1](../runs/20260927T174454-hono-5283-C-r1-d38d/events.jsonl) [C2](../runs/20260927T182910-hono-5283-C-r2-9d54/events.jsonl)
  - `hono-5311`: A $0.009, C $0.019 (2.07x); runs [A0](../runs/20260927T164055-hono-5311-A-r0-a0ec/events.jsonl) [A1](../runs/20260927T162042-hono-5311-A-r1-8771/events.jsonl) [A2](../runs/20260927T175118-hono-5311-A-r2-18a1/events.jsonl) [C0](../runs/20260927T152256-hono-5311-C-r0-5be8/events.jsonl) [C1](../runs/20260927T150447-hono-5311-C-r1-2569/events.jsonl) [C2](../runs/20260927T150045-hono-5311-C-r2-6d5c/events.jsonl)

### C vs A: turns

- wins: none
- losses:
  - `hono-5283`: A 8, C 23 (2.96x); runs [A0](../runs/20260927T145249-hono-5283-A-r0-fede/events.jsonl) [A1](../runs/20260927T144751-hono-5283-A-r1-6808/events.jsonl) [A2](../runs/20260927T153403-hono-5283-A-r2-7f12/events.jsonl) [C0](../runs/20260927T174605-hono-5283-C-r0-3a5c/events.jsonl) [C1](../runs/20260927T174454-hono-5283-C-r1-d38d/events.jsonl) [C2](../runs/20260927T182910-hono-5283-C-r2-9d54/events.jsonl)
  - `hono-5059`: A 6, C 16 (2.53x); runs [A0](../runs/20260927T163306-hono-5059-A-r0-b322/events.jsonl) [A1](../runs/20260927T153507-hono-5059-A-r1-973a/events.jsonl) [A2](../runs/20260927T174154-hono-5059-A-r2-4e97/events.jsonl) [C0](../runs/20260927T144835-hono-5059-C-r0-1845/events.jsonl) [C1](../runs/20260927T183716-hono-5059-C-r1-5d2f/events.jsonl) [C2](../runs/20260927T172243-hono-5059-C-r2-0155/events.jsonl)
  - `hono-5311`: A 11, C 27 (2.50x); runs [A0](../runs/20260927T164055-hono-5311-A-r0-a0ec/events.jsonl) [A1](../runs/20260927T162042-hono-5311-A-r1-8771/events.jsonl) [A2](../runs/20260927T175118-hono-5311-A-r2-18a1/events.jsonl) [C0](../runs/20260927T152256-hono-5311-C-r0-5be8/events.jsonl) [C1](../runs/20260927T150447-hono-5311-C-r1-2569/events.jsonl) [C2](../runs/20260927T150045-hono-5311-C-r2-6d5c/events.jsonl)

### C vs A: wall_seconds

- wins:
  - `hono-5357`: A 109.3, C 78.7 (0.72x); runs [A0](../runs/20260927T175404-hono-5357-A-r0-2490/events.jsonl) [A1](../runs/20260927T150613-hono-5357-A-r1-91da/events.jsonl) [A2](../runs/20260927T154731-hono-5357-A-r2-e0b3/events.jsonl) [C0](../runs/20260927T174815-hono-5357-C-r0-bf91/events.jsonl) [C1](../runs/20260927T152724-hono-5357-C-r1-d5d6/events.jsonl) [C2](../runs/20260927T154035-hono-5357-C-r2-12c9/events.jsonl)
  - `hono-5102`: A 188.7, C 163.0 (0.86x); runs [A0](../runs/20260927T183117-hono-5102-A-r0-0503/events.jsonl) [A1](../runs/20260927T175959-hono-5102-A-r1-a13a/events.jsonl) [A2](../runs/20260927T163336-hono-5102-A-r2-0d54/events.jsonl) [C0](../runs/20260927T163243-hono-5102-C-r0-aeee/events.jsonl) [C1](../runs/20260927T181015-hono-5102-C-r1-5e5f/events.jsonl) [C2](../runs/20260927T151857-hono-5102-C-r2-fef0/events.jsonl)
  - `hono-5092`: A 148.0, C 128.3 (0.87x); runs [A0](../runs/20260927T173815-hono-5092-A-r0-a965/events.jsonl) [A1](../runs/20260927T160156-hono-5092-A-r1-6346/events.jsonl) [A2](../runs/20260927T150400-hono-5092-A-r2-3b1e/events.jsonl) [C0](../runs/20260927T145358-hono-5092-C-r0-64cd/events.jsonl) [C1](../runs/20260927T160656-hono-5092-C-r1-b5fc/events.jsonl) [C2](../runs/20260927T152350-hono-5092-C-r2-de56/events.jsonl)
- losses:
  - `hono-5059`: A 33.7, C 140.0 (4.16x); runs [A0](../runs/20260927T163306-hono-5059-A-r0-b322/events.jsonl) [A1](../runs/20260927T153507-hono-5059-A-r1-973a/events.jsonl) [A2](../runs/20260927T174154-hono-5059-A-r2-4e97/events.jsonl) [C0](../runs/20260927T144835-hono-5059-C-r0-1845/events.jsonl) [C1](../runs/20260927T183716-hono-5059-C-r1-5d2f/events.jsonl) [C2](../runs/20260927T172243-hono-5059-C-r2-0155/events.jsonl)
  - `hono-5110`: A 48.7, C 173.3 (3.56x); runs [A0](../runs/20260927T181314-hono-5110-A-r0-c62c/events.jsonl) [A1](../runs/20260927T143036-hono-5110-A-r1-d679/events.jsonl) [A2](../runs/20260927T172702-hono-5110-A-r2-31a5/events.jsonl) [C0](../runs/20260927T153144-hono-5110-C-r0-a168/events.jsonl) [C1](../runs/20260927T173820-hono-5110-C-r1-5822/events.jsonl) [C2](../runs/20260927T171023-hono-5110-C-r2-29eb/events.jsonl)
  - `hono-5197`: A 28.3, C 93.3 (3.29x); runs [A0](../runs/20260927T153749-hono-5197-A-r0-33c5/events.jsonl) [A1](../runs/20260927T175849-hono-5197-A-r1-80a4/events.jsonl) [A2](../runs/20260927T183542-hono-5197-A-r2-f452/events.jsonl) [C0](../runs/20260927T163956-hono-5197-C-r0-141d/events.jsonl) [C1](../runs/20260927T171154-hono-5197-C-r1-cc32/events.jsonl) [C2](../runs/20260927T161247-hono-5197-C-r2-2208/events.jsonl)

## verdict

rule: a metric counts as helped or hurt only when its 95% CI excludes no change (ratio 1.0, or 0 pp for pass rate). otherwise: no measurable difference.

- pass rate is at the ceiling (95%+ in every setup), so it can't separate the setups here; the comparison rests on tokens, cost, turns and wall time.

- **B vs A**
  - pass rate: no measurable difference. -2.5 pp vs A, 95% CI -6.7 to +0.0 pp
  - tokens: hurt. median 1.69x of A, 95% CI 1.54x to 1.95x
  - cost: hurt. median 1.51x of A, 95% CI 1.42x to 1.67x
  - turns: hurt. median 1.87x of A, 95% CI 1.60x to 2.00x
  - wall_seconds: hurt. median 1.76x of A, 95% CI 1.54x to 1.91x
- **C vs A**
  - pass rate: no measurable difference. -0.8 pp vs A, 95% CI -2.5 to +0.0 pp
  - tokens: hurt. median 1.76x of A, 95% CI 1.56x to 2.06x
  - cost: hurt. median 1.49x of A, 95% CI 1.34x to 1.67x
  - turns: hurt. median 1.74x of A, 95% CI 1.56x to 1.87x
  - wall_seconds: hurt. median 1.64x of A, 95% CI 1.44x to 1.88x

## limitations

- tool-surface confound: B and C reach ax through the shell tool, while A edits with codex's native apply_patch. differences mix ax itself with the cost of going through the shell (quoting, heredocs, output formatting).
- single repo: every task comes from hono (typescript). other languages, repo sizes and layouts aren't covered.
- single agent and model: codex on one model at one reasoning effort. other agents may use tools very differently.
- tasks are mined from merged PRs with hidden tests; rewritten instructions can still leak or under-specify the fix.
- CIs are over tasks with a handful of reps each; small task counts give wide intervals, so "no measurable difference" is not the same as "no difference".

stats: ax_eval.stats.summary.
