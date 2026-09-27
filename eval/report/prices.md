# model prices

checked 2026-09-27. provider is azure ai foundry, global standard (pay-as-you-go), deployments in eastus. usd per 1m tokens, short context (under 272k input tokens per request). `eval/prices.json` has exactly these rows, and `load_prices(model=...)` picks one (default gpt-6-astra, unknown model = warning + zeros).

| model | version | input | cached input | cache write | output | context | effort levels |
|---|---|---|---|---|---|---|---|
| gpt-6-astra | 2026-09-03 | 10.00 | 1.00 | 12.50 | 50.00 | 1.05m (922k in / 128k out) | none, low, medium, high, xhigh, max |
| gpt-6-sol | 2026-09-22 | 2.00 | 0.20 | 2.50 | 10.00 | 1.05m (922k / 128k) | none, low, medium, high, xhigh, max |
| gpt-6-luna | 2026-09-22 | 0.10 | 0.01 | 0.125 | 0.50 | 1.05m (922k / 128k) | none, low, medium, high, xhigh, max |
| gpt-5.6-sol | 2026-07-09 | 4.00 | 0.40 | 5.00 | 20.00 | 1.05m (922k / 128k) | none, low, medium, high, xhigh, max |
| gpt-5.6-terra | 2026-07-09 | 2.00 | 0.20 | 2.50 | 12.00 | 1.05m (922k / 128k) | none, low, medium, high, xhigh, max |
| gpt-5.6-luna | 2026-07-09 | 0.20 | 0.02 | 0.25 | 1.20 | 1.05m (922k / 128k) | none, low, medium, high, xhigh, max |

gpt-5.6-sol is a promo price (see caveats). list is 5.00 / 0.50 / 6.25 / 30.00.

every model supports reasoning effort, medium is the default everywhere, and none of them charge a different per-token rate by effort. effort just changes how many reasoning tokens get made, and those bill as output. so the medium runs are comparable to astra's on setup, just not on token counts.

openai direct (standard tier) matches every row above to the cent.

long context (over 272k input tokens, and then the whole request is billed at the higher rate) in case a run ever gets there:

| model | input | cached input | cache write | output |
|---|---|---|---|---|
| gpt-6-astra | 20.00 | 2.00 | 25.00 | 75.00 |
| gpt-6-sol | 4.00 | 0.40 | 5.00 | 15.00 |
| gpt-6-luna | 0.20 | 0.02 | 0.25 | 0.75 |
| gpt-5.6-sol (promo) | 8.00 | 0.80 | 10.00 | 30.00 |
| gpt-5.6-terra | 4.00 | 0.40 | 5.00 | 18.00 |
| gpt-5.6-luna | 0.40 | 0.04 | 0.50 | 1.80 |

## where the numbers came from

- azure blog, 2026-09-22, gpt-6 astra/sol/luna in foundry. has the full gpt-6 table: global, us data zone, eu data zone, short and long:
  https://azure.microsoft.com/en-us/blog/gpt-6-astra-sol-and-luna-for-production-agents-in-microsoft-foundry/
- azure blog, 2026-07-09 (updated after openai's 7/30 cut), gpt-5.6 in foundry. short-context standard global rows for sol/terra/luna, plus the sol promo footnote ("$4.00 per 1M input tokens and $20.00 per 1M output tokens", 2026-09-01 through at least 2026-11-30):
  https://azure.microsoft.com/en-us/blog/gpt-5-6-now-available-in-microsoft-foundry/
- azure retail prices api, filtered to `serviceName eq 'Foundry Models' and armRegionName eq 'eastus'`. this is the official machine-readable price list and it has every meter we need: `6-sol ShortCo Inp Std Gl`, `5.6 terra ShortCo Cd Wr Std Gl`, etc (Inp = input, Cd Inp = cached input, Cd Wr = cache write, Opt = output, Gl = global, DZ = data zone, PP = priority). every short and long number in both tables above matches it. it's also the only official azure source for the 5.6-sol promo cached/cache-write rates and for all 5.6 long-context rates.
  https://prices.azure.com/api/retail/prices
- azure openai pricing page: rows exist for all six models but the static page shows `$-`, with a notice that gpt-6 sol and luna prices "are currently in processing for publishing on this page" and to see the blog:
  https://azure.microsoft.com/en-us/pricing/details/azure-openai/
- learn, models sold by azure: versions, context windows (all six are "1,050,000 Input: 922,000 Output: 128,000"), and that short vs long is decided by input tokens only:
  https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure
- learn, reasoning models: effort support per model (gpt-6: "including none"), `max` only on gpt-6/5.6 via the responses api, "Reasoning tokens are billed as output tokens", and the gpt-5.6 chat-completions tools gotcha:
  https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning
- openai pricing (cross-check): standard table has all six, same numbers. the "all models" table is what lists the 5.6 rows:
  https://developers.openai.com/api/docs/pricing
- openai model pages, for effort levels ("none, low, medium (default), high, xhigh, and max"), context, cache write = 1.25x input, and the long-context rule ("Prompts with more than 272K input tokens are priced at 2x input and cache rates and 1.5x output for the full request"):
  https://developers.openai.com/api/docs/models/gpt-6-sol (and gpt-6-luna, gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna)

## caveats

- gpt-5.6-sol is on promo. azure says 2026-09-01 to at least 2026-11-30, openai says at least 2026-11-21. if we run after that, use list (5.00 / 0.50 / 6.25 / 30.00). the azure blog only states promo input and output; the 0.40 cached and 5.00 cache write come from the retail api and openai's page, not the blog.
- gpt-5.6-terra and luna were cut on 2026-07-30 (luna by a lot). older third-party writeups and q&a threads quote the pre-cut prices, ignore those.
- the gpt-5.6 generation isn't cheaper than gpt-6 at the same tier: 5.6-luna is 2x gpt-6-luna on input and 2.4x on output, and 5.6-sol (even on promo) is 2x gpt-6-sol.
- the 272k long-context threshold is now written on openai's model pages (for astra too), so the astra note in prices.json saying it's third-party only is out of date. azure's learn page still just says "see azure openai pricing" and the pricing page is blank, so for azure it's still inferred from openai + the retail meters. our tasks stay way under it anyway.
- version mismatch: learn's models page says gpt-5.6 is `2026-07-09`, the reasoning page's feature table says `2026-06-25`. the ask was 2026-07-09 and prices don't depend on it.
- gpt-5.6 on chat completions refuses function tools unless effort is `none`. codex talks responses api so it should be fine, but if a run errors with "Function tools with reasoning_effort are not supported", that's why.
- cache writes are billed on all six at 1.25x input. `cost()` already prices `cache_write_input_tokens`.
- data zone deployments cost +10% (us) or +20% (eu, gpt-6 per the blog) instead. global standard is what we deploy.
- no per-request minimum on any page. recheck the azure pricing page before paid runs, it'll probably fill in eventually.

confidence: high on every short-context number. each one is on an azure blog or the azure retail api, and openai's own page agrees.
