# ax eval report

generated 2026-09-27 from `runs/runs.jsonl`.

- agent: codex, codex codex-cli 0.156.0
- model: gpt-6-astra, effort medium
- ax commit: 687338073221047ba63e22c2aea3a05148a423d1, 893530a822398f5c56b6c0241ab7c3c947ec4ca6
- tasks: 50 in final.jsonl (10 dev, 40 held-out); 40 with usable runs here
- runs: 438 real (35 dry runs ignored), 438 usable, 411 in this report (heldout split, model gpt-6-astra), 0 infra failures, 0 incomplete, 0 timed out (counted as unresolved)
- setups: A, Ar, B, Br, C, Cr. A is the baseline (Ar for the raw-tools family); ratios and deltas are paired by task against it.

## summary

| setup | runs | tasks | pass rate | 95% CI | median tokens | median cost | median turns | median wall s |
|---|---|---|---|---|---|---|---|---|
| A | 120 | 40 | 98.3% | 95.0% to 100.0% | 194,480 | $0.657 | 12.0 | 58.0 |
| Ar | 19 | 19 | 100.0% | 100.0% to 100.0% | 354,574 | $0.757 | 9.0 | 87.0 |
| B | 120 | 40 | 98.3% | 95.0% to 100.0% | 202,588 | $0.650 | 13.0 | 60.0 |
| Br | 15 | 15 | 100.0% | 100.0% to 100.0% | 200,524 | $0.704 | 7.0 | 73.0 |
| C | 120 | 40 | 98.3% | 95.0% to 100.0% | 201,326 | $0.661 | 14.0 | 61.0 |
| Cr | 17 | 17 | 100.0% | 100.0% to 100.0% | 221,325 | $0.604 | 7.0 | 76.0 |

pass rate by split:

| setup | dev | held-out |
|---|---|---|
| A | 100.0% (3/3) | 98.5% (128/130) |
| Ar | - | 100.0% (19/19) |
| B | 100.0% (3/3) | 98.4% (121/123) |
| Br | - | 100.0% (15/15) |
| C | 100.0% (3/3) | 98.4% (123/125) |
| Cr | - | 100.0% (17/17) |

## guardrail

- B: ok. pass rate +0.0 pp vs A, 95% CI +0.0 to +0.0 pp; allowed loss 5 pp.
- Br: ok. pass rate +0.0 pp vs A, 95% CI +0.0 to +0.0 pp; allowed loss 5 pp.
- C: ok. pass rate +0.0 pp vs A, 95% CI +0.0 to +0.0 pp; allowed loss 5 pp.
- Cr: ok. pass rate +0.0 pp vs A, 95% CI +0.0 to +0.0 pp; allowed loss 5 pp.

## ratios vs baseline

median over tasks of (setup mean / baseline mean); below 1 means the ax setup used less.

| comparison | metric | median ratio | 95% CI | tasks |
|---|---|---|---|---|
| B/A | tokens | 0.94x | 0.90x to 1.03x | 40 |
| B/A | cost | 0.95x | 0.90x to 0.97x | 40 |
| B/A | turns | 1.04x | 1.00x to 1.14x | 40 |
| B/A | wall_seconds | 1.02x | 0.98x to 1.08x | 40 |
| Br/Ar | tokens | 0.77x | 0.60x to 1.02x | 8 |
| Br/Ar | cost | 0.79x | 0.70x to 0.89x | 8 |
| Br/Ar | turns | 0.82x | 0.56x to 0.88x | 8 |
| Br/Ar | wall_seconds | 0.89x | 0.65x to 1.29x | 8 |
| C/A | tokens | 0.98x | 0.89x to 1.03x | 40 |
| C/A | cost | 0.94x | 0.90x to 0.96x | 40 |
| C/A | turns | 1.03x | 0.99x to 1.12x | 40 |
| C/A | wall_seconds | 1.04x | 0.97x to 1.08x | 40 |
| Cr/Ar | tokens | 0.77x | 0.56x to 1.22x | 9 |
| Cr/Ar | cost | 0.86x | 0.73x to 1.14x | 9 |
| Cr/Ar | turns | 0.80x | 0.60x to 1.00x | 9 |
| Cr/Ar | wall_seconds | 0.88x | 0.69x to 1.19x | 9 |

## cost breakdown

median $ per run for each token class; in brackets, that class's share of the setup's total spend.

| setup | uncached input | cached input | cache writes | output | median total |
|---|---|---|---|---|---|
| A | $0.000 (0.0%) | $0.161 (28.8%) | $0.405 (56.2%) | $0.094 (15.0%) | $0.657 |
| Ar | $0.000 (0.1%) | $0.320 (44.8%) | $0.364 (42.7%) | $0.083 (12.4%) | $0.757 |
| B | $0.000 (0.0%) | $0.170 (29.7%) | $0.383 (55.9%) | $0.087 (14.3%) | $0.650 |
| Br | $0.000 (0.1%) | $0.173 (36.0%) | $0.325 (51.1%) | $0.073 (12.9%) | $0.704 |
| C | $0.000 (0.0%) | $0.169 (29.3%) | $0.387 (56.2%) | $0.092 (14.5%) | $0.661 |
| Cr | $0.000 (0.1%) | $0.198 (38.6%) | $0.335 (47.8%) | $0.098 (13.5%) | $0.604 |

cache-write tokens are 99.9% of uncached input tokens (median over runs). parse.cost bills both at their own rate, so if codex counts cache writes inside input_tokens, the uncached line double-counts them.

paired by task against the baseline, per token class:

| comparison | class | median ratio | 95% CI | tasks |
|---|---|---|---|---|
| B/A | uncached input | 1.05x | 1.00x to 1.11x | 40 |
| B/A | cached input | 0.94x | 0.90x to 1.06x | 40 |
| B/A | cache writes | 0.93x | 0.91x to 0.99x | 40 |
| B/A | output | 0.91x | 0.85x to 0.94x | 40 |
| Br/Ar | uncached input | 0.88x | 0.72x to 1.20x | 8 |
| Br/Ar | cached input | 0.75x | 0.58x to 1.06x | 8 |
| Br/Ar | cache writes | 0.88x | 0.80x to 0.98x | 8 |
| Br/Ar | output | 0.92x | 0.79x to 1.03x | 8 |
| C/A | uncached input | 1.08x | 1.03x to 1.12x | 40 |
| C/A | cached input | 0.98x | 0.89x to 1.06x | 40 |
| C/A | cache writes | 0.93x | 0.91x to 0.96x | 40 |
| C/A | output | 0.93x | 0.88x to 0.95x | 40 |
| Cr/Ar | uncached input | 0.92x | 0.64x to 1.15x | 9 |
| Cr/Ar | cached input | 0.75x | 0.52x to 1.22x | 9 |
| Cr/Ar | cache writes | 0.99x | 0.87x to 1.07x | 9 |
| Cr/Ar | output | 0.94x | 0.74x to 1.17x | 9 |

## code mode vs raw tools

same letter, codex's code mode (one `exec` js tool) vs plain function tools. paired by task; pass-rate delta and median ratios.

| comparison | metric | value | 95% CI | tasks |
|---|---|---|---|---|
| Ar-A | pass_rate | +0.000 | +0.000 to +0.000 | - |
| Ar/A | tokens | 1.73x | 1.20x to 1.93x | 19 |
| Ar/A | cost | 1.17x | 1.12x to 1.25x | 19 |
| Ar/A | turns | 0.79x | 0.70x to 0.83x | 19 |
| Ar/A | wall_seconds | 1.57x | 1.33x to 1.76x | 19 |
| Ar/A | cost_uncached | 1.73x | 1.30x to 1.94x | 19 |
| Ar/A | cost_cached | 1.88x | 1.27x to 2.13x | 19 |
| Ar/A | cost_cache_write | 0.89x | 0.86x to 0.92x | 19 |
| Ar/A | cost_output | 1.00x | 0.89x to 1.07x | 19 |
| Br-B | pass_rate | +0.000 | +0.000 to +0.000 | - |
| Br/B | tokens | 1.14x | 1.05x to 1.36x | 15 |
| Br/B | cost | 1.05x | 0.95x to 1.11x | 15 |
| Br/B | turns | 0.53x | 0.44x to 0.62x | 15 |
| Br/B | wall_seconds | 1.35x | 1.11x to 1.76x | 15 |
| Br/B | cost_uncached | 1.24x | 1.11x to 1.36x | 15 |
| Br/B | cost_cached | 1.19x | 1.08x to 1.41x | 15 |
| Br/B | cost_cache_write | 0.88x | 0.85x to 0.94x | 15 |
| Br/B | cost_output | 0.97x | 0.95x to 1.06x | 15 |
| Cr-C | pass_rate | +0.000 | +0.000 to +0.000 | - |
| Cr/C | tokens | 1.14x | 1.08x to 1.30x | 17 |
| Cr/C | cost | 0.97x | 0.94x to 1.09x | 17 |
| Cr/C | turns | 0.58x | 0.52x to 0.61x | 17 |
| Cr/C | wall_seconds | 1.22x | 1.19x to 1.40x | 17 |
| Cr/C | cost_uncached | 1.22x | 1.12x to 1.37x | 17 |
| Cr/C | cost_cached | 1.20x | 1.12x to 1.35x | 17 |
| Cr/C | cost_cache_write | 0.87x | 0.85x to 0.93x | 17 |
| Cr/C | cost_output | 0.96x | 0.89x to 1.02x | 17 |

## adoption

fallback rate = share of file reads/searches/edits that didn't go through ax; script calls = inline python/node doing that work.

| setup | runs | runs using ax | median fallback rate | script calls | ax rejections | top ax commands |
|---|---|---|---|---|---|---|
| A | 120 | 0 (0.0%) | 100.0% | 26 | 0 | - |
| Ar | 19 | 0 (0.0%) | 100.0% | 8 | 0 | - |
| B | 120 | 120 (100.0%) | 0.1% | 2 | 0 | edit 381, read 377, find 187, diff 159 |
| Br | 15 | 15 (100.0%) | 0.8% | 0 | 0 | read 49, edit 46, find 35, diff 26 |
| C | 120 | 120 (100.0%) | 1.2% | 3 | 4 | edit 391, read 370, find 181, diff 161 |
| Cr | 17 | 17 (100.0%) | 1.3% | 0 | 0 | read 67, edit 58, find 33, diff 29 |

## wins and losses

top 3 tasks per metric, by per-task ratio (or pass-rate delta) against the baseline.

### B vs A: resolved

- no task differs from A.

### B vs A: tokens

- wins:
  - `hono-5205`: A 240,920, B 173,729 (0.72x); runs [A0](../runs/20260926T180446-hono-5205-A-r0-7ac4/events.jsonl) [A1](../runs/20260926T171658-hono-5205-A-r1-e2f1/events.jsonl) [A2](../runs/20260926T173248-hono-5205-A-r2-4782/events.jsonl) [B0](../runs/20260926T174838-hono-5205-B-r0-8924/events.jsonl) [B1](../runs/20260926T174648-hono-5205-B-r1-05a2/events.jsonl) [B2](../runs/20260926T175101-hono-5205-B-r2-1978/events.jsonl)
  - `hono-5020`: A 170,349, B 126,402 (0.74x); runs [A0](../runs/20260926T173120-hono-5020-A-r0-4a55/events.jsonl) [A1](../runs/20260926T174339-hono-5020-A-r1-598c/events.jsonl) [A2](../runs/20260926T180758-hono-5020-A-r2-572a/events.jsonl) [B0](../runs/20260926T165604-hono-5020-B-r0-eeb8/events.jsonl) [B1](../runs/20260926T163952-hono-5020-B-r1-9537/events.jsonl) [B2](../runs/20260926T172820-hono-5020-B-r2-1165/events.jsonl)
  - `hono-5264`: A 333,876, B 264,682 (0.79x); runs [A0](../runs/20260926T173858-hono-5264-A-r0-7cd8/events.jsonl) [A1](../runs/20260926T172724-hono-5264-A-r1-b57a/events.jsonl) [A2](../runs/20260926T173346-hono-5264-A-r2-5b6c/events.jsonl) [B0](../runs/20260926T170431-hono-5264-B-r0-cd63/events.jsonl) [B1](../runs/20260926T172554-hono-5264-B-r1-7856/events.jsonl) [B2](../runs/20260926T165114-hono-5264-B-r2-a50b/events.jsonl)
- losses:
  - `hono-5138`: A 114,144, B 182,152 (1.60x); runs [A0](../runs/20260926T172326-hono-5138-A-r0-b23a/events.jsonl) [A1](../runs/20260926T173532-hono-5138-A-r1-e83e/events.jsonl) [A2](../runs/20260926T174203-hono-5138-A-r2-d074/events.jsonl) [B0](../runs/20260926T180512-hono-5138-B-r0-3db2/events.jsonl) [B1](../runs/20260926T170033-hono-5138-B-r1-3c46/events.jsonl) [B2](../runs/20260926T175404-hono-5138-B-r2-24cb/events.jsonl)
  - `hono-5311`: A 197,329, B 260,105 (1.32x); runs [A0](../runs/20260926T171341-hono-5311-A-r0-3644/events.jsonl) [A1](../runs/20260926T164959-hono-5311-A-r1-f1ee/events.jsonl) [A2](../runs/20260926T175441-hono-5311-A-r2-62c9/events.jsonl) [B0](../runs/20260926T174859-hono-5311-B-r0-a30f/events.jsonl) [B1](../runs/20260926T165240-hono-5311-B-r1-44b4/events.jsonl) [B2](../runs/20260926T165556-hono-5311-B-r2-48b3/events.jsonl)
  - `hono-5357`: A 167,136, B 217,971 (1.30x); runs [A0](../runs/20260926T170347-hono-5357-A-r0-e574/events.jsonl) [A1](../runs/20260926T180411-hono-5357-A-r1-bf0b/events.jsonl) [A2](../runs/20260926T172638-hono-5357-A-r2-eb3d/events.jsonl) [B0](../runs/20260926T164135-hono-5357-B-r0-61ac/events.jsonl) [B1](../runs/20260926T175011-hono-5357-B-r1-e9a6/events.jsonl) [B2](../runs/20260926T173037-hono-5357-B-r2-8168/events.jsonl)

### B vs A: cost

- wins:
  - `hono-5020`: A $0.564, B $0.434 (0.77x); runs [A0](../runs/20260926T173120-hono-5020-A-r0-4a55/events.jsonl) [A1](../runs/20260926T174339-hono-5020-A-r1-598c/events.jsonl) [A2](../runs/20260926T180758-hono-5020-A-r2-572a/events.jsonl) [B0](../runs/20260926T165604-hono-5020-B-r0-eeb8/events.jsonl) [B1](../runs/20260926T163952-hono-5020-B-r1-9537/events.jsonl) [B2](../runs/20260926T172820-hono-5020-B-r2-1165/events.jsonl)
  - `hono-5349`: A $0.634, B $0.515 (0.81x); runs [A0](../runs/20260926T171441-hono-5349-A-r0-47c9/events.jsonl) [A1](../runs/20260926T163229-hono-5349-A-r1-d453/events.jsonl) [A2](../runs/20260926T180315-hono-5349-A-r2-7062/events.jsonl) [B0](../runs/20260926T163537-hono-5349-B-r0-3076/events.jsonl) [B1](../runs/20260926T174029-hono-5349-B-r1-b2d6/events.jsonl) [B2](../runs/20260926T165012-hono-5349-B-r2-e455/events.jsonl)
  - `hono-5205`: A $0.776, B $0.636 (0.82x); runs [A0](../runs/20260926T180446-hono-5205-A-r0-7ac4/events.jsonl) [A1](../runs/20260926T171658-hono-5205-A-r1-e2f1/events.jsonl) [A2](../runs/20260926T173248-hono-5205-A-r2-4782/events.jsonl) [B0](../runs/20260926T174838-hono-5205-B-r0-8924/events.jsonl) [B1](../runs/20260926T174648-hono-5205-B-r1-05a2/events.jsonl) [B2](../runs/20260926T175101-hono-5205-B-r2-1978/events.jsonl)
- losses:
  - `hono-5138`: A $0.436, B $0.531 (1.22x); runs [A0](../runs/20260926T172326-hono-5138-A-r0-b23a/events.jsonl) [A1](../runs/20260926T173532-hono-5138-A-r1-e83e/events.jsonl) [A2](../runs/20260926T174203-hono-5138-A-r2-d074/events.jsonl) [B0](../runs/20260926T180512-hono-5138-B-r0-3db2/events.jsonl) [B1](../runs/20260926T170033-hono-5138-B-r1-3c46/events.jsonl) [B2](../runs/20260926T175404-hono-5138-B-r2-24cb/events.jsonl)
  - `hono-5311`: A $0.700, B $0.808 (1.15x); runs [A0](../runs/20260926T171341-hono-5311-A-r0-3644/events.jsonl) [A1](../runs/20260926T164959-hono-5311-A-r1-f1ee/events.jsonl) [A2](../runs/20260926T175441-hono-5311-A-r2-62c9/events.jsonl) [B0](../runs/20260926T174859-hono-5311-B-r0-a30f/events.jsonl) [B1](../runs/20260926T165240-hono-5311-B-r1-44b4/events.jsonl) [B2](../runs/20260926T165556-hono-5311-B-r2-48b3/events.jsonl)
  - `hono-5215`: A $0.694, B $0.776 (1.12x); runs [A0](../runs/20260926T174719-hono-5215-A-r0-3be4/events.jsonl) [A1](../runs/20260926T175212-hono-5215-A-r1-e966/events.jsonl) [A2](../runs/20260926T171100-hono-5215-A-r2-09b6/events.jsonl) [B0](../runs/20260926T172145-hono-5215-B-r0-1560/events.jsonl) [B1](../runs/20260926T175534-hono-5215-B-r1-080a/events.jsonl) [B2](../runs/20260926T165238-hono-5215-B-r2-e014/events.jsonl)

### B vs A: turns

- wins:
  - `hono-5110`: A 12, B 9 (0.75x); runs [A0](../runs/20260926T170700-hono-5110-A-r0-de02/events.jsonl) [A1](../runs/20260926T171743-hono-5110-A-r1-637e/events.jsonl) [A2](../runs/20260926T164232-hono-5110-A-r2-611a/events.jsonl) [B0](../runs/20260926T163319-hono-5110-B-r0-11ea/events.jsonl) [B1](../runs/20260926T174643-hono-5110-B-r1-9a56/events.jsonl) [B2](../runs/20260926T174609-hono-5110-B-r2-5ed4/events.jsonl)
  - `hono-5264`: A 16, B 12 (0.77x); runs [A0](../runs/20260926T173858-hono-5264-A-r0-7cd8/events.jsonl) [A1](../runs/20260926T172724-hono-5264-A-r1-b57a/events.jsonl) [A2](../runs/20260926T173346-hono-5264-A-r2-5b6c/events.jsonl) [B0](../runs/20260926T170431-hono-5264-B-r0-cd63/events.jsonl) [B1](../runs/20260926T172554-hono-5264-B-r1-7856/events.jsonl) [B2](../runs/20260926T165114-hono-5264-B-r2-a50b/events.jsonl)
  - `hono-5062`: A 12, B 10 (0.78x); runs [A0](../runs/20260926T174458-hono-5062-A-r0-7102/events.jsonl) [A1](../runs/20260926T175247-hono-5062-A-r1-cf5f/events.jsonl) [A2](../runs/20260926T175746-hono-5062-A-r2-728d/events.jsonl) [B0](../runs/20260926T180413-hono-5062-B-r0-d286/events.jsonl) [B1](../runs/20260926T172701-hono-5062-B-r1-57fa/events.jsonl) [B2](../runs/20260926T180238-hono-5062-B-r2-6be8/events.jsonl)
- losses:
  - `hono-5272`: A 13, B 18 (1.45x); runs [A0](../runs/20260926T165743-hono-5272-A-r0-b17e/events.jsonl) [A1](../runs/20260926T172321-hono-5272-A-r1-2256/events.jsonl) [A2](../runs/20260926T172448-hono-5272-A-r2-8478/events.jsonl) [B0](../runs/20260926T165255-hono-5272-B-r0-62e9/events.jsonl) [B1](../runs/20260926T164740-hono-5272-B-r1-4848/events.jsonl) [B2](../runs/20260926T170851-hono-5272-B-r2-ed7b/events.jsonl)
  - `hono-5215`: A 16, B 23 (1.45x); runs [A0](../runs/20260926T174719-hono-5215-A-r0-3be4/events.jsonl) [A1](../runs/20260926T175212-hono-5215-A-r1-e966/events.jsonl) [A2](../runs/20260926T171100-hono-5215-A-r2-09b6/events.jsonl) [B0](../runs/20260926T172145-hono-5215-B-r0-1560/events.jsonl) [B1](../runs/20260926T175534-hono-5215-B-r1-080a/events.jsonl) [B2](../runs/20260926T165238-hono-5215-B-r2-e014/events.jsonl)
  - `hono-5291`: A 18, B 25 (1.41x); runs [A0](../runs/20260926T163546-hono-5291-A-r0-470f/events.jsonl) [A1](../runs/20260926T172320-hono-5291-A-r1-f327/events.jsonl) [A2](../runs/20260926T180328-hono-5291-A-r2-a617/events.jsonl) [B0](../runs/20260926T164623-hono-5291-B-r0-9a72/events.jsonl) [B1](../runs/20260926T173328-hono-5291-B-r1-9f47/events.jsonl) [B2](../runs/20260926T162638-hono-5291-B-r2-b360/events.jsonl)

### B vs A: wall_seconds

- wins:
  - `hono-5205`: A 71.3, B 60.0 (0.84x); runs [A0](../runs/20260926T180446-hono-5205-A-r0-7ac4/events.jsonl) [A1](../runs/20260926T171658-hono-5205-A-r1-e2f1/events.jsonl) [A2](../runs/20260926T173248-hono-5205-A-r2-4782/events.jsonl) [B0](../runs/20260926T174838-hono-5205-B-r0-8924/events.jsonl) [B1](../runs/20260926T174648-hono-5205-B-r1-05a2/events.jsonl) [B2](../runs/20260926T175101-hono-5205-B-r2-1978/events.jsonl)
  - `hono-5033`: A 72.0, B 60.7 (0.84x); runs [A0](../runs/20260926T164823-hono-5033-A-r0-5865/events.jsonl) [A1](../runs/20260926T170204-hono-5033-A-r1-e635/events.jsonl) [A2](../runs/20260926T173714-hono-5033-A-r2-e047/events.jsonl) [B0](../runs/20260926T172856-hono-5033-B-r0-e876/events.jsonl) [B1](../runs/20260926T175830-hono-5033-B-r1-5af1/events.jsonl) [B2](../runs/20260926T175458-hono-5033-B-r2-6a18/events.jsonl)
  - `hono-5020`: A 46.7, B 39.7 (0.85x); runs [A0](../runs/20260926T173120-hono-5020-A-r0-4a55/events.jsonl) [A1](../runs/20260926T174339-hono-5020-A-r1-598c/events.jsonl) [A2](../runs/20260926T180758-hono-5020-A-r2-572a/events.jsonl) [B0](../runs/20260926T165604-hono-5020-B-r0-eeb8/events.jsonl) [B1](../runs/20260926T163952-hono-5020-B-r1-9537/events.jsonl) [B2](../runs/20260926T172820-hono-5020-B-r2-1165/events.jsonl)
- losses:
  - `hono-5138`: A 37.7, B 52.0 (1.38x); runs [A0](../runs/20260926T172326-hono-5138-A-r0-b23a/events.jsonl) [A1](../runs/20260926T173532-hono-5138-A-r1-e83e/events.jsonl) [A2](../runs/20260926T174203-hono-5138-A-r2-d074/events.jsonl) [B0](../runs/20260926T180512-hono-5138-B-r0-3db2/events.jsonl) [B1](../runs/20260926T170033-hono-5138-B-r1-3c46/events.jsonl) [B2](../runs/20260926T175404-hono-5138-B-r2-24cb/events.jsonl)
  - `hono-5197`: A 40.0, B 52.0 (1.30x); runs [A0](../runs/20260926T162638-hono-5197-A-r0-cbcd/events.jsonl) [A1](../runs/20260926T164844-hono-5197-A-r1-996a/events.jsonl) [A2](../runs/20260926T180330-hono-5197-A-r2-4057/events.jsonl) [B0](../runs/20260926T164002-hono-5197-B-r0-f859/events.jsonl) [B1](../runs/20260926T171211-hono-5197-B-r1-a52d/events.jsonl) [B2](../runs/20260926T165452-hono-5197-B-r2-31fd/events.jsonl)
  - `hono-5292`: A 50.0, B 59.7 (1.19x); runs [A0](../runs/20260926T172819-hono-5292-A-r0-b158/events.jsonl) [A1](../runs/20260926T175816-hono-5292-A-r1-1fec/events.jsonl) [A2](../runs/20260926T170702-hono-5292-A-r2-052d/events.jsonl) [B0](../runs/20260926T175939-hono-5292-B-r0-2451/events.jsonl) [B1](../runs/20260926T165604-hono-5292-B-r1-7d1a/events.jsonl) [B2](../runs/20260926T172018-hono-5292-B-r2-402e/events.jsonl)

### Br vs Ar: resolved

- no task differs from A.

### Br vs Ar: tokens

- wins:
  - `hono-5110`: A 358,752, Br 194,039 (0.54x); runs [Ar0](../runs/20260927T143721-hono-5110-Ar-r0-8cb4/events.jsonl) [Br0](../runs/20260927T144004-hono-5110-Br-r0-f56c/events.jsonl)
  - `hono-5099`: A 706,339, Br 421,382 (0.60x); runs [Ar0](../runs/20260927T143238-hono-5099-Ar-r0-63ce/events.jsonl) [Br0](../runs/20260927T143923-hono-5099-Br-r0-cf0f/events.jsonl)
  - `hono-5209`: A 255,591, Br 165,966 (0.65x); runs [Ar0](../runs/20260927T143943-hono-5209-Ar-r0-e57f/events.jsonl) [Br0](../runs/20260927T142800-hono-5209-Br-r0-4380/events.jsonl)
- losses:
  - `hono-5272`: A 201,952, Br 281,971 (1.40x); runs [Ar0](../runs/20260927T142626-hono-5272-Ar-r0-0f7d/events.jsonl) [Br0](../runs/20260927T142420-hono-5272-Br-r0-b5ce/events.jsonl)
  - `hono-5197`: A 148,830, Br 151,274 (1.02x); runs [Ar0](../runs/20260927T144138-hono-5197-Ar-r0-3731/events.jsonl) [Br0](../runs/20260927T143718-hono-5197-Br-r0-b822/events.jsonl)

### Br vs Ar: cost

- wins:
  - `hono-5197`: A $0.692, Br $0.408 (0.59x); runs [Ar0](../runs/20260927T144138-hono-5197-Ar-r0-3731/events.jsonl) [Br0](../runs/20260927T143718-hono-5197-Br-r0-b822/events.jsonl)
  - `hono-5110`: A $0.706, Br $0.492 (0.70x); runs [Ar0](../runs/20260927T143721-hono-5110-Ar-r0-8cb4/events.jsonl) [Br0](../runs/20260927T144004-hono-5110-Br-r0-f56c/events.jsonl)
  - `hono-5099`: A $1.229, Br $0.875 (0.71x); runs [Ar0](../runs/20260927T143238-hono-5099-Ar-r0-63ce/events.jsonl) [Br0](../runs/20260927T143923-hono-5099-Br-r0-cf0f/events.jsonl)
- losses:
  - `hono-5272`: A $0.558, Br $0.704 (1.26x); runs [Ar0](../runs/20260927T142626-hono-5272-Ar-r0-0f7d/events.jsonl) [Br0](../runs/20260927T142420-hono-5272-Br-r0-b5ce/events.jsonl)

### Br vs Ar: turns

- wins:
  - `hono-5110`: A 11, Br 6 (0.55x); runs [Ar0](../runs/20260927T143721-hono-5110-Ar-r0-8cb4/events.jsonl) [Br0](../runs/20260927T144004-hono-5110-Br-r0-f56c/events.jsonl)
  - `hono-5099`: A 16, Br 9 (0.56x); runs [Ar0](../runs/20260927T143238-hono-5099-Ar-r0-63ce/events.jsonl) [Br0](../runs/20260927T143923-hono-5099-Br-r0-cf0f/events.jsonl)
  - `hono-5292`: A 12, Br 7 (0.58x); runs [Ar0](../runs/20260927T142951-hono-5292-Ar-r0-89da/events.jsonl) [Br0](../runs/20260927T142828-hono-5292-Br-r0-d98c/events.jsonl)
- losses:
  - `hono-5272`: A 7, Br 8 (1.14x); runs [Ar0](../runs/20260927T142626-hono-5272-Ar-r0-0f7d/events.jsonl) [Br0](../runs/20260927T142420-hono-5272-Br-r0-b5ce/events.jsonl)

### Br vs Ar: wall_seconds

- wins:
  - `hono-5209`: A 87.0, Br 55.0 (0.63x); runs [Ar0](../runs/20260927T143943-hono-5209-Ar-r0-e57f/events.jsonl) [Br0](../runs/20260927T142800-hono-5209-Br-r0-4380/events.jsonl)
  - `hono-5110`: A 122.0, Br 79.0 (0.65x); runs [Ar0](../runs/20260927T143721-hono-5110-Ar-r0-8cb4/events.jsonl) [Br0](../runs/20260927T144004-hono-5110-Br-r0-f56c/events.jsonl)
  - `hono-5292`: A 85.0, Br 63.0 (0.74x); runs [Ar0](../runs/20260927T142951-hono-5292-Ar-r0-89da/events.jsonl) [Br0](../runs/20260927T142828-hono-5292-Br-r0-d98c/events.jsonl)
- losses:
  - `hono-5197`: A 42.0, Br 71.0 (1.69x); runs [Ar0](../runs/20260927T144138-hono-5197-Ar-r0-3731/events.jsonl) [Br0](../runs/20260927T143718-hono-5197-Br-r0-b822/events.jsonl)
  - `hono-5272`: A 58.0, Br 75.0 (1.29x); runs [Ar0](../runs/20260927T142626-hono-5272-Ar-r0-0f7d/events.jsonl) [Br0](../runs/20260927T142420-hono-5272-Br-r0-b5ce/events.jsonl)
  - `hono-5033`: A 72.0, Br 78.0 (1.08x); runs [Ar0](../runs/20260927T142839-hono-5033-Ar-r0-f10b/events.jsonl) [Br0](../runs/20260927T142438-hono-5033-Br-r0-a66f/events.jsonl)

### C vs A: resolved

- no task differs from A.

### C vs A: tokens

- wins:
  - `hono-5291`: A 345,709, C 242,747 (0.70x); runs [A0](../runs/20260926T163546-hono-5291-A-r0-470f/events.jsonl) [A1](../runs/20260926T172320-hono-5291-A-r1-f327/events.jsonl) [A2](../runs/20260926T180328-hono-5291-A-r2-a617/events.jsonl) [C0](../runs/20260926T174932-hono-5291-C-r0-e582/events.jsonl) [C1](../runs/20260926T173633-hono-5291-C-r1-6c62/events.jsonl) [C2](../runs/20260926T175328-hono-5291-C-r2-5b54/events.jsonl)
  - `hono-5340`: A 785,416, C 594,226 (0.76x); runs [A0](../runs/20260926T173011-hono-5340-A-r0-e078/events.jsonl) [A1](../runs/20260926T180602-hono-5340-A-r1-1268/events.jsonl) [A2](../runs/20260926T170220-hono-5340-A-r2-0a5e/events.jsonl) [C0](../runs/20260926T162958-hono-5340-C-r0-28be/events.jsonl) [C1](../runs/20260926T165957-hono-5340-C-r1-3ecf/events.jsonl) [C2](../runs/20260926T172533-hono-5340-C-r2-cf18/events.jsonl)
  - `hono-5059`: A 155,272, C 117,526 (0.76x); runs [A0](../runs/20260926T163541-hono-5059-A-r0-c617/events.jsonl) [A1](../runs/20260926T180226-hono-5059-A-r1-17ae/events.jsonl) [A2](../runs/20260926T164632-hono-5059-A-r2-b4e6/events.jsonl) [C0](../runs/20260926T174053-hono-5059-C-r0-5756/events.jsonl) [C1](../runs/20260926T173556-hono-5059-C-r1-8ecb/events.jsonl) [C2](../runs/20260926T171402-hono-5059-C-r2-a1a9/events.jsonl)
- losses:
  - `hono-5138`: A 114,144, C 167,464 (1.47x); runs [A0](../runs/20260926T172326-hono-5138-A-r0-b23a/events.jsonl) [A1](../runs/20260926T173532-hono-5138-A-r1-e83e/events.jsonl) [A2](../runs/20260926T174203-hono-5138-A-r2-d074/events.jsonl) [C0](../runs/20260926T164920-hono-5138-C-r0-0e87/events.jsonl) [C1](../runs/20260926T165241-hono-5138-C-r1-d939/events.jsonl) [C2](../runs/20260926T165658-hono-5138-C-r2-8111/events.jsonl)
  - `hono-5311`: A 197,329, C 280,746 (1.42x); runs [A0](../runs/20260926T171341-hono-5311-A-r0-3644/events.jsonl) [A1](../runs/20260926T164959-hono-5311-A-r1-f1ee/events.jsonl) [A2](../runs/20260926T175441-hono-5311-A-r2-62c9/events.jsonl) [C0](../runs/20260926T173231-hono-5311-C-r0-d2e8/events.jsonl) [C1](../runs/20260926T173145-hono-5311-C-r1-0002/events.jsonl) [C2](../runs/20260926T162638-hono-5311-C-r2-d24e/events.jsonl)
  - `hono-5268`: A 127,982, C 175,779 (1.37x); runs [A0](../runs/20260926T164058-hono-5268-A-r0-6c9b/events.jsonl) [A1](../runs/20260926T175905-hono-5268-A-r1-899f/events.jsonl) [A2](../runs/20260926T174819-hono-5268-A-r2-5f7d/events.jsonl) [C0](../runs/20260926T164648-hono-5268-C-r0-fc79/events.jsonl) [C1](../runs/20260926T170117-hono-5268-C-r1-8a96/events.jsonl) [C2](../runs/20260926T162743-hono-5268-C-r2-3bcf/events.jsonl)

### C vs A: cost

- wins:
  - `hono-5349`: A $0.634, C $0.508 (0.80x); runs [A0](../runs/20260926T171441-hono-5349-A-r0-47c9/events.jsonl) [A1](../runs/20260926T163229-hono-5349-A-r1-d453/events.jsonl) [A2](../runs/20260926T180315-hono-5349-A-r2-7062/events.jsonl) [C0](../runs/20260926T175945-hono-5349-C-r0-83a5/events.jsonl) [C1](../runs/20260926T175703-hono-5349-C-r1-8b24/events.jsonl) [C2](../runs/20260926T174120-hono-5349-C-r2-16f5/events.jsonl)
  - `hono-5020`: A $0.564, C $0.452 (0.80x); runs [A0](../runs/20260926T173120-hono-5020-A-r0-4a55/events.jsonl) [A1](../runs/20260926T174339-hono-5020-A-r1-598c/events.jsonl) [A2](../runs/20260926T180758-hono-5020-A-r2-572a/events.jsonl) [C0](../runs/20260926T165049-hono-5020-C-r0-c80f/events.jsonl) [C1](../runs/20260926T173444-hono-5020-C-r1-d9c2/events.jsonl) [C2](../runs/20260926T163009-hono-5020-C-r2-effe/events.jsonl)
  - `hono-5197`: A $0.504, C $0.405 (0.80x); runs [A0](../runs/20260926T162638-hono-5197-A-r0-cbcd/events.jsonl) [A1](../runs/20260926T164844-hono-5197-A-r1-996a/events.jsonl) [A2](../runs/20260926T180330-hono-5197-A-r2-4057/events.jsonl) [C0](../runs/20260926T180750-hono-5197-C-r0-00de/events.jsonl) [C1](../runs/20260926T175841-hono-5197-C-r1-19ec/events.jsonl) [C2](../runs/20260926T163740-hono-5197-C-r2-8707/events.jsonl)
- losses:
  - `hono-5311`: A $0.700, C $0.844 (1.21x); runs [A0](../runs/20260926T171341-hono-5311-A-r0-3644/events.jsonl) [A1](../runs/20260926T164959-hono-5311-A-r1-f1ee/events.jsonl) [A2](../runs/20260926T175441-hono-5311-A-r2-62c9/events.jsonl) [C0](../runs/20260926T173231-hono-5311-C-r0-d2e8/events.jsonl) [C1](../runs/20260926T173145-hono-5311-C-r1-0002/events.jsonl) [C2](../runs/20260926T162638-hono-5311-C-r2-d24e/events.jsonl)
  - `hono-5138`: A $0.436, C $0.513 (1.18x); runs [A0](../runs/20260926T172326-hono-5138-A-r0-b23a/events.jsonl) [A1](../runs/20260926T173532-hono-5138-A-r1-e83e/events.jsonl) [A2](../runs/20260926T174203-hono-5138-A-r2-d074/events.jsonl) [C0](../runs/20260926T164920-hono-5138-C-r0-0e87/events.jsonl) [C1](../runs/20260926T165241-hono-5138-C-r1-d939/events.jsonl) [C2](../runs/20260926T165658-hono-5138-C-r2-8111/events.jsonl)
  - `hono-5244`: A $0.604, C $0.694 (1.15x); runs [A0](../runs/20260926T173652-hono-5244-A-r0-a349/events.jsonl) [A1](../runs/20260926T180044-hono-5244-A-r1-05b9/events.jsonl) [A2](../runs/20260926T174055-hono-5244-A-r2-f14a/events.jsonl) [C0](../runs/20260926T172506-hono-5244-C-r0-5a41/events.jsonl) [C1](../runs/20260926T173745-hono-5244-C-r1-de7b/events.jsonl) [C2](../runs/20260926T165511-hono-5244-C-r2-ca8d/events.jsonl)

### C vs A: turns

- wins:
  - `hono-5268`: A 11, C 8 (0.72x); runs [A0](../runs/20260926T164058-hono-5268-A-r0-6c9b/events.jsonl) [A1](../runs/20260926T175905-hono-5268-A-r1-899f/events.jsonl) [A2](../runs/20260926T174819-hono-5268-A-r2-5f7d/events.jsonl) [C0](../runs/20260926T164648-hono-5268-C-r0-fc79/events.jsonl) [C1](../runs/20260926T170117-hono-5268-C-r1-8a96/events.jsonl) [C2](../runs/20260926T162743-hono-5268-C-r2-3bcf/events.jsonl)
  - `hono-5255`: A 14, C 10 (0.74x); runs [A0](../runs/20260926T171357-hono-5255-A-r0-c58d/events.jsonl) [A1](../runs/20260926T172009-hono-5255-A-r1-aae6/events.jsonl) [A2](../runs/20260926T174240-hono-5255-A-r2-7547/events.jsonl) [C0](../runs/20260926T175740-hono-5255-C-r0-ff6c/events.jsonl) [C1](../runs/20260926T163248-hono-5255-C-r1-4303/events.jsonl) [C2](../runs/20260926T170316-hono-5255-C-r2-ef31/events.jsonl)
  - `hono-4988`: A 13, C 10 (0.78x); runs [A0](../runs/20260926T175714-hono-4988-A-r0-e54b/events.jsonl) [A1](../runs/20260926T164937-hono-4988-A-r1-9ecf/events.jsonl) [A2](../runs/20260926T163836-hono-4988-A-r2-49be/events.jsonl) [C0](../runs/20260926T173048-hono-4988-C-r0-ac0b/events.jsonl) [C1](../runs/20260926T175758-hono-4988-C-r1-67bf/events.jsonl) [C2](../runs/20260926T165545-hono-4988-C-r2-a89c/events.jsonl)
- losses:
  - `hono-5424`: A 11, C 17 (1.53x); runs [A0](../runs/20260926T164658-hono-5424-A-r0-4213/events.jsonl) [A1](../runs/20260926T173844-hono-5424-A-r1-a064/events.jsonl) [A2](../runs/20260926T170749-hono-5424-A-r2-a0b3/events.jsonl) [C0](../runs/20260926T172040-hono-5424-C-r0-42ed/events.jsonl) [C1](../runs/20260926T173545-hono-5424-C-r1-0716/events.jsonl) [C2](../runs/20260926T172615-hono-5424-C-r2-c5c9/events.jsonl)
  - `hono-5062`: A 12, C 18 (1.46x); runs [A0](../runs/20260926T174458-hono-5062-A-r0-7102/events.jsonl) [A1](../runs/20260926T175247-hono-5062-A-r1-cf5f/events.jsonl) [A2](../runs/20260926T175746-hono-5062-A-r2-728d/events.jsonl) [C0](../runs/20260926T180058-hono-5062-C-r0-7c48/events.jsonl) [C1](../runs/20260926T171646-hono-5062-C-r1-5c9a/events.jsonl) [C2](../runs/20260926T172521-hono-5062-C-r2-2fcc/events.jsonl)
  - `hono-5244`: A 11, C 15 (1.36x); runs [A0](../runs/20260926T173652-hono-5244-A-r0-a349/events.jsonl) [A1](../runs/20260926T180044-hono-5244-A-r1-05b9/events.jsonl) [A2](../runs/20260926T174055-hono-5244-A-r2-f14a/events.jsonl) [C0](../runs/20260926T172506-hono-5244-C-r0-5a41/events.jsonl) [C1](../runs/20260926T173745-hono-5244-C-r1-de7b/events.jsonl) [C2](../runs/20260926T165511-hono-5244-C-r2-ca8d/events.jsonl)

### C vs A: wall_seconds

- wins:
  - `hono-5059`: A 45.7, C 37.0 (0.81x); runs [A0](../runs/20260926T163541-hono-5059-A-r0-c617/events.jsonl) [A1](../runs/20260926T180226-hono-5059-A-r1-17ae/events.jsonl) [A2](../runs/20260926T164632-hono-5059-A-r2-b4e6/events.jsonl) [C0](../runs/20260926T174053-hono-5059-C-r0-5756/events.jsonl) [C1](../runs/20260926T173556-hono-5059-C-r1-8ecb/events.jsonl) [C2](../runs/20260926T171402-hono-5059-C-r2-a1a9/events.jsonl)
  - `hono-5179`: A 179.3, C 146.7 (0.82x); runs [A0](../runs/20260926T170907-hono-5179-A-r0-ec29/events.jsonl) [A1](../runs/20260926T165740-hono-5179-A-r1-c0d5/events.jsonl) [A2](../runs/20260926T171935-hono-5179-A-r2-66d5/events.jsonl) [C0](../runs/20260926T174651-hono-5179-C-r0-a682/events.jsonl) [C1](../runs/20260926T175544-hono-5179-C-r1-de8f/events.jsonl) [C2](../runs/20260926T164310-hono-5179-C-r2-012c/events.jsonl)
  - `hono-5380`: A 70.3, C 60.3 (0.86x); runs [A0](../runs/20260926T163633-hono-5380-A-r0-1bc3/events.jsonl) [A1](../runs/20260926T162901-hono-5380-A-r1-ac69/events.jsonl) [A2](../runs/20260926T173427-hono-5380-A-r2-687f/events.jsonl) [C0](../runs/20260926T162809-hono-5380-C-r0-69d0/events.jsonl) [C1](../runs/20260926T163349-hono-5380-C-r1-a87a/events.jsonl) [C2](../runs/20260926T171938-hono-5380-C-r2-ab0f/events.jsonl)
- losses:
  - `hono-5062`: A 50.3, C 74.0 (1.47x); runs [A0](../runs/20260926T174458-hono-5062-A-r0-7102/events.jsonl) [A1](../runs/20260926T175247-hono-5062-A-r1-cf5f/events.jsonl) [A2](../runs/20260926T175746-hono-5062-A-r2-728d/events.jsonl) [C0](../runs/20260926T180058-hono-5062-C-r0-7c48/events.jsonl) [C1](../runs/20260926T171646-hono-5062-C-r1-5c9a/events.jsonl) [C2](../runs/20260926T172521-hono-5062-C-r2-2fcc/events.jsonl)
  - `hono-5268`: A 39.0, C 53.3 (1.37x); runs [A0](../runs/20260926T164058-hono-5268-A-r0-6c9b/events.jsonl) [A1](../runs/20260926T175905-hono-5268-A-r1-899f/events.jsonl) [A2](../runs/20260926T174819-hono-5268-A-r2-5f7d/events.jsonl) [C0](../runs/20260926T164648-hono-5268-C-r0-fc79/events.jsonl) [C1](../runs/20260926T170117-hono-5268-C-r1-8a96/events.jsonl) [C2](../runs/20260926T162743-hono-5268-C-r2-3bcf/events.jsonl)
  - `hono-5099`: A 69.3, C 88.0 (1.27x); runs [A0](../runs/20260926T175332-hono-5099-A-r0-59ae/events.jsonl) [A1](../runs/20260926T170637-hono-5099-A-r1-bb18/events.jsonl) [A2](../runs/20260926T163322-hono-5099-A-r2-4152/events.jsonl) [C0](../runs/20260926T164448-hono-5099-C-r0-dd41/events.jsonl) [C1](../runs/20260926T171210-hono-5099-C-r1-f097/events.jsonl) [C2](../runs/20260926T164234-hono-5099-C-r2-1e46/events.jsonl)

### Cr vs Ar: resolved

- no task differs from A.

### Cr vs Ar: tokens

- wins:
  - `hono-5426`: A 367,128, Cr 148,327 (0.40x); runs [Ar0](../runs/20260927T143843-hono-5426-Ar-r0-a3bd/events.jsonl) [Cr0](../runs/20260927T142223-hono-5426-Cr-r0-0e43/events.jsonl)
  - `hono-5255`: A 322,084, Cr 180,646 (0.56x); runs [Ar0](../runs/20260927T143829-hono-5255-Ar-r0-91ae/events.jsonl) [Cr0](../runs/20260927T142321-hono-5255-Cr-r0-e1b4/events.jsonl)
  - `hono-5292`: A 385,899, Cr 233,308 (0.60x); runs [Ar0](../runs/20260927T142951-hono-5292-Ar-r0-89da/events.jsonl) [Cr0](../runs/20260927T142547-hono-5292-Cr-r0-95b3/events.jsonl)
- losses:
  - `hono-5137`: A 858,072, Cr 1,096,965 (1.28x); runs [Ar0](../runs/20260927T143222-hono-5137-Ar-r0-91ef/events.jsonl) [Cr0](../runs/20260927T143502-hono-5137-Cr-r0-23f3/events.jsonl)
  - `hono-5424`: A 235,900, Cr 288,219 (1.22x); runs [Ar0](../runs/20260927T142646-hono-5424-Ar-r0-653a/events.jsonl) [Cr0](../runs/20260927T142909-hono-5424-Cr-r0-748c/events.jsonl)
  - `hono-5138`: A 190,743, Cr 221,325 (1.16x); runs [Ar0](../runs/20260927T143028-hono-5138-Ar-r0-7786/events.jsonl) [Cr0](../runs/20260927T142437-hono-5138-Cr-r0-ccc3/events.jsonl)

### Cr vs Ar: cost

- wins:
  - `hono-5426`: A $0.770, Cr $0.455 (0.59x); runs [Ar0](../runs/20260927T143843-hono-5426-Ar-r0-a3bd/events.jsonl) [Cr0](../runs/20260927T142223-hono-5426-Cr-r0-0e43/events.jsonl)
  - `hono-5292`: A $0.825, Cr $0.604 (0.73x); runs [Ar0](../runs/20260927T142951-hono-5292-Ar-r0-89da/events.jsonl) [Cr0](../runs/20260927T142547-hono-5292-Cr-r0-95b3/events.jsonl)
  - `hono-5179`: A $2.825, Cr $2.133 (0.76x); runs [Ar0](../runs/20260927T142952-hono-5179-Ar-r0-bc71/events.jsonl) [Cr0](../runs/20260927T142325-hono-5179-Cr-r0-6e50/events.jsonl)
- losses:
  - `hono-5424`: A $0.640, Cr $0.785 (1.23x); runs [Ar0](../runs/20260927T142646-hono-5424-Ar-r0-653a/events.jsonl) [Cr0](../runs/20260927T142909-hono-5424-Cr-r0-748c/events.jsonl)
  - `hono-5137`: A $1.626, Cr $1.862 (1.14x); runs [Ar0](../runs/20260927T143222-hono-5137-Ar-r0-91ef/events.jsonl) [Cr0](../runs/20260927T143502-hono-5137-Cr-r0-23f3/events.jsonl)
  - `hono-5138`: A $0.490, Cr $0.525 (1.07x); runs [Ar0](../runs/20260927T143028-hono-5138-Ar-r0-7786/events.jsonl) [Cr0](../runs/20260927T142437-hono-5138-Cr-r0-ccc3/events.jsonl)

### Cr vs Ar: turns

- wins:
  - `hono-5292`: A 12, Cr 7 (0.58x); runs [Ar0](../runs/20260927T142951-hono-5292-Ar-r0-89da/events.jsonl) [Cr0](../runs/20260927T142547-hono-5292-Cr-r0-95b3/events.jsonl)
  - `hono-5426`: A 10, Cr 6 (0.60x); runs [Ar0](../runs/20260927T143843-hono-5426-Ar-r0-a3bd/events.jsonl) [Cr0](../runs/20260927T142223-hono-5426-Cr-r0-0e43/events.jsonl)
  - `hono-5255`: A 8, Cr 6 (0.75x); runs [Ar0](../runs/20260927T143829-hono-5255-Ar-r0-91ae/events.jsonl) [Cr0](../runs/20260927T142321-hono-5255-Cr-r0-e1b4/events.jsonl)
- losses:
  - `hono-5137`: A 17, Cr 20 (1.18x); runs [Ar0](../runs/20260927T143222-hono-5137-Ar-r0-91ef/events.jsonl) [Cr0](../runs/20260927T143502-hono-5137-Cr-r0-23f3/events.jsonl)

### Cr vs Ar: wall_seconds

- wins:
  - `hono-5426`: A 91.0, Cr 58.0 (0.64x); runs [Ar0](../runs/20260927T143843-hono-5426-Ar-r0-a3bd/events.jsonl) [Cr0](../runs/20260927T142223-hono-5426-Cr-r0-0e43/events.jsonl)
  - `hono-5292`: A 85.0, Cr 59.0 (0.69x); runs [Ar0](../runs/20260927T142951-hono-5292-Ar-r0-89da/events.jsonl) [Cr0](../runs/20260927T142547-hono-5292-Cr-r0-95b3/events.jsonl)
  - `hono-5179`: A 292.0, Cr 214.0 (0.73x); runs [Ar0](../runs/20260927T142952-hono-5179-Ar-r0-bc71/events.jsonl) [Cr0](../runs/20260927T142325-hono-5179-Cr-r0-6e50/events.jsonl)
- losses:
  - `hono-5033`: A 72.0, Cr 91.0 (1.26x); runs [Ar0](../runs/20260927T142839-hono-5033-Ar-r0-f10b/events.jsonl) [Cr0](../runs/20260927T143547-hono-5033-Cr-r0-c9ec/events.jsonl)
  - `hono-5138`: A 59.0, Cr 70.0 (1.19x); runs [Ar0](../runs/20260927T143028-hono-5138-Ar-r0-7786/events.jsonl) [Cr0](../runs/20260927T142437-hono-5138-Cr-r0-ccc3/events.jsonl)
  - `hono-5424`: A 74.0, Cr 79.0 (1.07x); runs [Ar0](../runs/20260927T142646-hono-5424-Ar-r0-653a/events.jsonl) [Cr0](../runs/20260927T142909-hono-5424-Cr-r0-748c/events.jsonl)

## verdict

rule: a metric counts as helped or hurt only when its 95% CI excludes no change (ratio 1.0, or 0 pp for pass rate). otherwise: no measurable difference.

- pass rate is at the ceiling (95%+ in every setup), so it can't separate the setups here; the comparison rests on tokens, cost, turns and wall time.

- **B vs A**
  - pass rate: no measurable difference. +0.0 pp vs A, 95% CI +0.0 to +0.0 pp
  - tokens: no measurable difference. median 0.94x of A, 95% CI 0.90x to 1.03x
  - cost: helped. median 0.95x of A, 95% CI 0.90x to 0.97x
  - turns: no measurable difference. median 1.04x of A, 95% CI 1.00x to 1.14x
  - wall_seconds: no measurable difference. median 1.02x of A, 95% CI 0.98x to 1.08x
- **Br vs Ar**
  - pass rate: no measurable difference. +0.0 pp vs A, 95% CI +0.0 to +0.0 pp
  - tokens: no measurable difference. median 0.77x of A, 95% CI 0.60x to 1.02x
  - cost: helped. median 0.79x of A, 95% CI 0.70x to 0.89x
  - turns: helped. median 0.82x of A, 95% CI 0.56x to 0.88x
  - wall_seconds: no measurable difference. median 0.89x of A, 95% CI 0.65x to 1.29x
- **C vs A**
  - pass rate: no measurable difference. +0.0 pp vs A, 95% CI +0.0 to +0.0 pp
  - tokens: no measurable difference. median 0.98x of A, 95% CI 0.89x to 1.03x
  - cost: helped. median 0.94x of A, 95% CI 0.90x to 0.96x
  - turns: no measurable difference. median 1.03x of A, 95% CI 0.99x to 1.12x
  - wall_seconds: no measurable difference. median 1.04x of A, 95% CI 0.97x to 1.08x
- **Cr vs Ar**
  - pass rate: no measurable difference. +0.0 pp vs A, 95% CI +0.0 to +0.0 pp
  - tokens: no measurable difference. median 0.77x of A, 95% CI 0.56x to 1.22x
  - cost: no measurable difference. median 0.86x of A, 95% CI 0.73x to 1.14x
  - turns: no measurable difference. median 0.80x of A, 95% CI 0.60x to 1.00x
  - wall_seconds: no measurable difference. median 0.88x of A, 95% CI 0.69x to 1.19x

## limitations

- tool-surface confound: B and C reach ax through the shell tool, while A edits with codex's native apply_patch. differences mix ax itself with the cost of going through the shell (quoting, heredocs, output formatting).
- single repo: every task comes from hono (typescript). other languages, repo sizes and layouts aren't covered.
- single agent and model: codex on one model at one reasoning effort. other agents may use tools very differently.
- tasks are mined from merged PRs with hidden tests; rewritten instructions can still leak or under-specify the fix.
- CIs are over tasks with a handful of reps each; small task counts give wide intervals, so "no measurable difference" is not the same as "no difference".

stats: ax_eval.stats.summary.
