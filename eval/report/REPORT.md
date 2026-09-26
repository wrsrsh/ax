# ax eval report

generated 2026-09-26 from `runs/runs.jsonl`.

- agent: codex, codex codex-cli 0.156.0
- model: gpt-6-astra, effort medium
- ax commit: 687338073221047ba63e22c2aea3a05148a423d1
- tasks: 50 in final.jsonl (10 dev, 40 held-out); 40 with usable runs here
- runs: 369 real (28 dry runs ignored), 369 usable, 360 in this report (heldout split), 0 infra failures, 0 incomplete, 0 timed out (counted as unresolved)
- setups: A, B, C. A is the baseline (Ar for the raw-tools family); ratios and deltas are paired by task against it.

## summary

| setup | runs | tasks | pass rate | 95% CI | median tokens | median cost | median turns | median wall s |
|---|---|---|---|---|---|---|---|---|
| A | 120 | 40 | 98.3% | 95.0% to 100.0% | 194,480 | $0.982 | 12.0 | 58.0 |
| B | 120 | 40 | 98.3% | 95.0% to 100.0% | 202,588 | $0.968 | 13.0 | 60.0 |
| C | 120 | 40 | 98.3% | 95.0% to 100.0% | 201,326 | $0.975 | 14.0 | 61.0 |

pass rate by split:

| setup | dev | held-out |
|---|---|---|
| A | 100.0% (3/3) | 98.3% (118/120) |
| B | 100.0% (3/3) | 98.3% (118/120) |
| C | 100.0% (3/3) | 98.3% (118/120) |

## guardrail

- B: ok. pass rate +0.0 pp vs A, 95% CI +0.0 to +0.0 pp; allowed loss 5 pp.
- C: ok. pass rate +0.0 pp vs A, 95% CI +0.0 to +0.0 pp; allowed loss 5 pp.

## ratios vs baseline

median over tasks of (setup mean / baseline mean); below 1 means the ax setup used less.

| comparison | metric | median ratio | 95% CI | tasks |
|---|---|---|---|---|
| B/A | tokens | 0.94x | 0.90x to 1.03x | 40 |
| B/A | cost | 0.95x | 0.90x to 0.98x | 40 |
| B/A | turns | 1.04x | 1.00x to 1.14x | 40 |
| B/A | wall_seconds | 1.02x | 0.98x to 1.08x | 40 |
| C/A | tokens | 0.98x | 0.89x to 1.03x | 40 |
| C/A | cost | 0.93x | 0.90x to 0.96x | 40 |
| C/A | turns | 1.03x | 0.99x to 1.12x | 40 |
| C/A | wall_seconds | 1.04x | 0.97x to 1.08x | 40 |

## adoption

fallback rate = share of file reads/searches/edits that didn't go through ax; script calls = inline python/node doing that work.

| setup | runs | runs using ax | median fallback rate | script calls | ax rejections | top ax commands |
|---|---|---|---|---|---|---|
| A | 120 | 0 (0.0%) | 100.0% | 26 | 0 | - |
| B | 120 | 120 (100.0%) | 0.1% | 2 | 0 | edit 381, read 377, find 187, diff 159 |
| C | 120 | 120 (100.0%) | 1.2% | 3 | 4 | edit 391, read 370, find 181, diff 161 |

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
  - `hono-5020`: A $0.855, B $0.665 (0.78x); runs [A0](../runs/20260926T173120-hono-5020-A-r0-4a55/events.jsonl) [A1](../runs/20260926T174339-hono-5020-A-r1-598c/events.jsonl) [A2](../runs/20260926T180758-hono-5020-A-r2-572a/events.jsonl) [B0](../runs/20260926T165604-hono-5020-B-r0-eeb8/events.jsonl) [B1](../runs/20260926T163952-hono-5020-B-r1-9537/events.jsonl) [B2](../runs/20260926T172820-hono-5020-B-r2-1165/events.jsonl)
  - `hono-5349`: A $0.956, B $0.774 (0.81x); runs [A0](../runs/20260926T171441-hono-5349-A-r0-47c9/events.jsonl) [A1](../runs/20260926T163229-hono-5349-A-r1-d453/events.jsonl) [A2](../runs/20260926T180315-hono-5349-A-r2-7062/events.jsonl) [B0](../runs/20260926T163537-hono-5349-B-r0-3076/events.jsonl) [B1](../runs/20260926T174029-hono-5349-B-r1-b2d6/events.jsonl) [B2](../runs/20260926T165012-hono-5349-B-r2-e455/events.jsonl)
  - `hono-5099`: A $1.205, B $1.000 (0.83x); runs [A0](../runs/20260926T175332-hono-5099-A-r0-59ae/events.jsonl) [A1](../runs/20260926T170637-hono-5099-A-r1-bb18/events.jsonl) [A2](../runs/20260926T163322-hono-5099-A-r2-4152/events.jsonl) [B0](../runs/20260926T180307-hono-5099-B-r0-a9d7/events.jsonl) [B1](../runs/20260926T174345-hono-5099-B-r1-3a78/events.jsonl) [B2](../runs/20260926T172118-hono-5099-B-r2-cfd8/events.jsonl)
- losses:
  - `hono-5138`: A $0.675, B $0.790 (1.17x); runs [A0](../runs/20260926T172326-hono-5138-A-r0-b23a/events.jsonl) [A1](../runs/20260926T173532-hono-5138-A-r1-e83e/events.jsonl) [A2](../runs/20260926T174203-hono-5138-A-r2-d074/events.jsonl) [B0](../runs/20260926T180512-hono-5138-B-r0-3db2/events.jsonl) [B1](../runs/20260926T170033-hono-5138-B-r1-3c46/events.jsonl) [B2](../runs/20260926T175404-hono-5138-B-r2-24cb/events.jsonl)
  - `hono-5311`: A $1.049, B $1.204 (1.15x); runs [A0](../runs/20260926T171341-hono-5311-A-r0-3644/events.jsonl) [A1](../runs/20260926T164959-hono-5311-A-r1-f1ee/events.jsonl) [A2](../runs/20260926T175441-hono-5311-A-r2-62c9/events.jsonl) [B0](../runs/20260926T174859-hono-5311-B-r0-a30f/events.jsonl) [B1](../runs/20260926T165240-hono-5311-B-r1-44b4/events.jsonl) [B2](../runs/20260926T165556-hono-5311-B-r2-48b3/events.jsonl)
  - `hono-5215`: A $0.994, B $1.097 (1.10x); runs [A0](../runs/20260926T174719-hono-5215-A-r0-3be4/events.jsonl) [A1](../runs/20260926T175212-hono-5215-A-r1-e966/events.jsonl) [A2](../runs/20260926T171100-hono-5215-A-r2-09b6/events.jsonl) [B0](../runs/20260926T172145-hono-5215-B-r0-1560/events.jsonl) [B1](../runs/20260926T175534-hono-5215-B-r1-080a/events.jsonl) [B2](../runs/20260926T165238-hono-5215-B-r2-e014/events.jsonl)

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
  - `hono-5020`: A $0.855, C $0.681 (0.80x); runs [A0](../runs/20260926T173120-hono-5020-A-r0-4a55/events.jsonl) [A1](../runs/20260926T174339-hono-5020-A-r1-598c/events.jsonl) [A2](../runs/20260926T180758-hono-5020-A-r2-572a/events.jsonl) [C0](../runs/20260926T165049-hono-5020-C-r0-c80f/events.jsonl) [C1](../runs/20260926T173444-hono-5020-C-r1-d9c2/events.jsonl) [C2](../runs/20260926T163009-hono-5020-C-r2-effe/events.jsonl)
  - `hono-5349`: A $0.956, C $0.765 (0.80x); runs [A0](../runs/20260926T171441-hono-5349-A-r0-47c9/events.jsonl) [A1](../runs/20260926T163229-hono-5349-A-r1-d453/events.jsonl) [A2](../runs/20260926T180315-hono-5349-A-r2-7062/events.jsonl) [C0](../runs/20260926T175945-hono-5349-C-r0-83a5/events.jsonl) [C1](../runs/20260926T175703-hono-5349-C-r1-8b24/events.jsonl) [C2](../runs/20260926T174120-hono-5349-C-r2-16f5/events.jsonl)
  - `hono-5197`: A $0.773, C $0.625 (0.81x); runs [A0](../runs/20260926T162638-hono-5197-A-r0-cbcd/events.jsonl) [A1](../runs/20260926T164844-hono-5197-A-r1-996a/events.jsonl) [A2](../runs/20260926T180330-hono-5197-A-r2-4057/events.jsonl) [C0](../runs/20260926T180750-hono-5197-C-r0-00de/events.jsonl) [C1](../runs/20260926T175841-hono-5197-C-r1-19ec/events.jsonl) [C2](../runs/20260926T163740-hono-5197-C-r2-8707/events.jsonl)
- losses:
  - `hono-5311`: A $1.049, C $1.251 (1.19x); runs [A0](../runs/20260926T171341-hono-5311-A-r0-3644/events.jsonl) [A1](../runs/20260926T164959-hono-5311-A-r1-f1ee/events.jsonl) [A2](../runs/20260926T175441-hono-5311-A-r2-62c9/events.jsonl) [C0](../runs/20260926T173231-hono-5311-C-r0-d2e8/events.jsonl) [C1](../runs/20260926T173145-hono-5311-C-r1-0002/events.jsonl) [C2](../runs/20260926T162638-hono-5311-C-r2-d24e/events.jsonl)
  - `hono-5138`: A $0.675, C $0.770 (1.14x); runs [A0](../runs/20260926T172326-hono-5138-A-r0-b23a/events.jsonl) [A1](../runs/20260926T173532-hono-5138-A-r1-e83e/events.jsonl) [A2](../runs/20260926T174203-hono-5138-A-r2-d074/events.jsonl) [C0](../runs/20260926T164920-hono-5138-C-r0-0e87/events.jsonl) [C1](../runs/20260926T165241-hono-5138-C-r1-d939/events.jsonl) [C2](../runs/20260926T165658-hono-5138-C-r2-8111/events.jsonl)
  - `hono-5244`: A $0.904, C $1.026 (1.13x); runs [A0](../runs/20260926T173652-hono-5244-A-r0-a349/events.jsonl) [A1](../runs/20260926T180044-hono-5244-A-r1-05b9/events.jsonl) [A2](../runs/20260926T174055-hono-5244-A-r2-f14a/events.jsonl) [C0](../runs/20260926T172506-hono-5244-C-r0-5a41/events.jsonl) [C1](../runs/20260926T173745-hono-5244-C-r1-de7b/events.jsonl) [C2](../runs/20260926T165511-hono-5244-C-r2-ca8d/events.jsonl)

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

## verdict

rule: a metric counts as helped or hurt only when its 95% CI excludes no change (ratio 1.0, or 0 pp for pass rate). otherwise: no measurable difference.

- pass rate is at the ceiling (95%+ in every setup), so it can't separate the setups here; the comparison rests on tokens, cost, turns and wall time.

- **B vs A**
  - pass rate: no measurable difference. +0.0 pp vs A, 95% CI +0.0 to +0.0 pp
  - tokens: no measurable difference. median 0.94x of A, 95% CI 0.90x to 1.03x
  - cost: helped. median 0.95x of A, 95% CI 0.90x to 0.98x
  - turns: no measurable difference. median 1.04x of A, 95% CI 1.00x to 1.14x
  - wall_seconds: no measurable difference. median 1.02x of A, 95% CI 0.98x to 1.08x
- **C vs A**
  - pass rate: no measurable difference. +0.0 pp vs A, 95% CI +0.0 to +0.0 pp
  - tokens: no measurable difference. median 0.98x of A, 95% CI 0.89x to 1.03x
  - cost: helped. median 0.93x of A, 95% CI 0.90x to 0.96x
  - turns: no measurable difference. median 1.03x of A, 95% CI 0.99x to 1.12x
  - wall_seconds: no measurable difference. median 1.04x of A, 95% CI 0.97x to 1.08x

## limitations

- tool-surface confound: B and C reach ax through the shell tool, while A edits with codex's native apply_patch. differences mix ax itself with the cost of going through the shell (quoting, heredocs, output formatting).
- single repo: every task comes from hono (typescript). other languages, repo sizes and layouts aren't covered.
- single agent and model: codex on one model at one reasoning effort. other agents may use tools very differently.
- tasks are mined from merged PRs with hidden tests; rewritten instructions can still leak or under-specify the fix.
- CIs are over tasks with a handful of reps each; small task counts give wide intervals, so "no measurable difference" is not the same as "no difference".

stats: ax_eval.stats.summary.
