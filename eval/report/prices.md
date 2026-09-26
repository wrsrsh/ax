# gpt-6-astra prices

checked 2026-09-26. provider is azure ai foundry, global standard (pay-as-you-go). numbers in usd per 1m tokens.

| | input | cached input | cache write | output |
|---|---|---|---|---|
| global standard, short context | 10.00 | 1.00 | 12.50 | 50.00 |
| global standard, long context | 20.00 | 2.00 | 25.00 | 75.00 |
| us data zone, short | 11.00 | 1.10 | 13.75 | 55.00 |
| eu data zone, short | 12.00 | 1.20 | 15.00 | 60.00 |
| openai api direct, standard short | 10.00 | 1.00 | 12.50 | 50.00 |

`eval/prices.json` uses the first row.

## sources

- azure blog, 2026-09-22, gpt-6 astra/sol/luna in foundry:
  https://azure.microsoft.com/en-us/blog/gpt-6-astra-sol-and-luna-for-production-agents-in-microsoft-foundry/
  table row: "Global Standard | Short | $10.00 | $1.00 | $12.50 | $50.00". also has the us and eu data zone rows above.
- azure blog, 2026-09-03, astra ga announcement (same global numbers):
  https://azure.microsoft.com/en-us/blog/gpt-6-astra-frontier-intelligence-for-work-now-generally-available-in-microsoft-foundry/
- azure openai pricing page: https://azure.microsoft.com/en-us/pricing/details/azure-openai/
  the gpt-6 astra rows exist but show "$-" everywhere, with a notice that gpt-6 prices are "currently in processing for publishing on this page" and to see the blog. so the blog is the only official azure number right now.
- learn, models sold by azure: https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure
  `gpt-6-astra` (2026-09-03), context "1,050,000 Input: 922,000 Output: 128,000". standard deployments "use separate pricing categories for short-context and long-context requests", decided by input tokens only. some quota tiers need a quota request; tier 5/6 have quota by default.
- learn, reasoning models: https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning
  "Reasoning tokens are billed as output tokens". effort is described as changing how much the model thinks, not the rate.
- openai pricing (fallback): https://developers.openai.com/api/docs/pricing
  gpt-6-astra standard short: $10 / $1 cached / $12.50 cache write / $50. long: $20 / $2 / $25 / $75. batch and flex are half, fast mode is 2x. "Regional processing (data residency) endpoints are charged a 10% uplift" for newer models.
- openai model page: https://developers.openai.com/api/docs/models/gpt-6-astra
  "1,050,000 context window", "128,000 max output tokens", effort supports low, medium, high, xhigh, max.

## caveats

- the long-context threshold isn't written down on any official page i could read. third-party writeups (truefoundry, storagereview, others) say >272k input tokens and that the higher rate covers the whole request. our tasks should stay well under that, so the short-context row is the one that matters, but if a run ever crosses it the cost of that request roughly doubles on input and goes 1.5x on output.
- cache writes are a separate line ($12.50/1m, above uncached input). prices.json doesn't carry it because the schema only has three fields. if codex's prompt caching reports cache-write tokens we should price them separately, otherwise we'll undercount.
- medium reasoning effort doesn't change the per-token price on either azure or openai. it changes how many reasoning tokens get generated, and those are billed at the output rate.
- no per-request minimum found on any of the pages.
- region: global standard is region-independent. if the deployment is actually data zone (us/eu), use the +10% / +20% rows.
- azure's pricing page could still change when the real numbers get published there. worth re-checking before the paid runs.

confidence: high for $10 / $1 / $50 on global standard (two official azure blog posts and openai's own page agree). medium on the long-context threshold (only third-party sources).
