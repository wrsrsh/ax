# instruction audit (final.jsonl, 50 tasks)

manual pass over every task in `eval/tasks/final.jsonl`: read the instruction, the gold patch, the test patch, fail_to_pass and the new tests that land in pass_to_pass. for the 26 flagged tasks `instruction` is still identical to `original_instruction`, so i judged the original text and noted what a rewrite has to avoid or add.

how to read the columns:

- **leak**: `major` means the instruction names the src file or line, or spells out the code-level fix (exact regex, exact one-liner, internal function plus what to change in it). `minor` means an internal symbol name, a file path that only shows up in a lint/test command, or a loose hint at the approach. `none` means behaviour only. public api names (`hc`, `etag()`, `accepts()`, `cloneRawRequest`, `parseBody`, ...) don't count.
- **sufficient**: could a competent engineer get the hidden tests to pass (f2p, plus the new tests that sit in p2p) from the instruction and the repo at base? `partial` means the tests check something the instruction doesn't imply, or the instruction's own suggested fix fails them. `no` means following the instruction produces something the tests reject.

## per task

| id | set | leak | sufficient | note |
|---|---|---|---|---|
| hono-4988 | heldout | major | partial | names `src/utils/stream.ts` lines 78-82 and gives a try/finally fix. the suggested fix **fails** the tests: gold also adds `preventAbort: true`, because otherwise `pipeTo` aborts the writable and later writes die. the test does `api.write('after pipe')` then `expect((await reader.read()).value).toEqual(encode('after pipe'))`. a rewrite has to say writes after a failed pipe must still reach the response |
| hono-4998 | heldout | major | yes | not flagged by the auto check: names `convertIPv6BinaryToString` and gives the exact `if (ipV6 === 0n) return '::'` fix |
| hono-5020 | heldout | none | yes | behaviour only (skip 206). the test also expects Content-Length and Content-Range preserved, which the instruction implies |
| hono-5033 | heldout | none | yes | issue text only. the test just needs a V1 event carrying `rawPath` to route by `path` |
| hono-5059 | heldout | minor | yes | quotes the offending line `protocol: c.req.url` and says "first value of Sec-WebSocket-Protocol". second f2p wants `''` with no header (`expect(ws.protocol).toBe('')`), implied by "mirror WebSocket.protocol" but not stated. bun adapter test is mocked, runs under node |
| hono-5062 | heldout | major | yes | file:line anchors plus the `content !== null` fix |
| hono-5067 | heldout | major | yes | file:line anchors for body.ts and validator.ts plus the fix idea. 3 src files. the mixed-case multipart bufferToFormData test already passes at base (in p2p), so the platform accepts mixed case and only the guards need changing |
| hono-5084 | heldout | major | partial | quotes `etagMatches` with file:line. a hidden p2p test (new, passes at base) pins scope: PUT with `If-None-Match: *` must give `expect(res.status).toBe(201)`, and a 404 with `*` must stay 404. "when a representation exists" covers the 404 case, but nothing mentions methods. a naive "`*` always matches" fix regresses p2p |
| hono-5092 | dev | major | yes | github links to `client.ts#L219` and `utils.ts` deepMerge. hidden p2p: per-request header wins on conflict, which is natural |
| hono-5094 | dev | none | partial | issue only says "return the request to origin". tests also require the first callback call to win (`callback(null, req); callback(null, {status:'500'})` gives `expect(result).toBe(cf.request)`) and `callback(error)` to reject (`rejects.toThrow('edge failure')`). several valid designs. the test patch also edits `runtime-tests/lambda-edge/index.test.ts` (outside src/, not run) |
| hono-5096 | dev | major | yes | not flagged: names `replaceUrlParam`, shows the regex and gives the exact `(?=/\|$)` fix. f2p calls the internal `replaceUrlParam` directly, so a rewrite must keep the fix inside that helper (sorting keys in client.ts wouldn't pass) |
| hono-5099 | heldout | major | yes | github url to lambda-edge `handler.ts#L140-L141` plus "look at Content-Encoding". zstd must be base64 and `identity` must not (hidden p2p), both fit the text |
| hono-5102 | heldout | major | yes | names `node.ts` `search()`, the RegExp branch, and the exact condition `m[0].length === restPathString.length`. f2p calls internal `Node.search` |
| hono-5133 | heldout | minor | **no** | the issue describes parseBody-after-formData, but at base (`80959d4`) `parseFormData` already early-returns from `bodyCache.formData`, so the repro passes. gold only changes `cloneRawRequest`, and the f2p is a cloneRawRequest test the text never mentions: `await req.formData(); const cloned = await cloneRawRequest(req)` then `expect(bodyText.startsWith(`--${boundary}`)).toBe(true)`. the issue's suggested fix points at the wrong function |
| hono-5135 | heldout | none | yes | thin (title only: "emit retry field when retry is 0"). the test just wants `retry: 0\n\n` in the output. a rewrite should give one sentence of behaviour |
| hono-5138 | heldout | major | yes | not flagged: gives the exact `message.id !== undefined` replacement. exact output `'data: reset\nid: \n\n'` follows from the existing template |
| hono-5141 | heldout | minor | yes | feature, but option name (`realm`), header format and escaping are all specified, so one design passes |
| hono-5171 | heldout | minor | partial | +176/-202 restructure of RegExpRouter over 3 files, 14 f2p. the pr says routing behaviour is unchanged, yet f2p includes new matching behaviour: `add('/w/*/x'); add('/w/:id/y')` then match `/w/123/y` captures `id`, and `add('GET','/:x{.}')` must throw. which paths are "unsupported" is decided by the gold algorithm |
| hono-5179 | heldout | minor | partial | feature, 3 files, 34 f2p (most are existing streaming tests that cascade through a shared `suspenseCounter`). names internal `JSXFunctionNode.toStringToBuffer()`, `childrenToStringToBuffer()`. tests also cover two things not described: a shared promise result under two context providers (`Promise.resolve(<Consumer/>)` must render `'<span>dark</span>'` and `'<span>black</span>'`) and escaped-string callbacks inside a returned array (`raw('a',[cb])` gives `'ab'`) |
| hono-5196 | heldout | none | **no** | the issue asks for an opt-in `cacheableStatusCode` option with a backward-compatible default ("the default would be all status codes"). gold changes the default instead and the test uses plain `etag()`: `c.text('not found', 404, { ETag: '"etag-123"' })` with `If-None-Match: "etag-123"` gives `expect(res.status).toBe(404)`, and PUT gives 201. unsafe methods (and a `QUERY` method in gold) are never mentioned |
| hono-5197 | heldout | minor | yes | names `getPermissionsPolicyDirectives`. behaviour (`false`/`['none']` becomes `()`) is clear |
| hono-5199 | heldout | major | yes | github url to `digest.ts#L26-L34`. expects standard sha-1 `"d104fafd..."` for a 2-chunk stream. the issue floats fixed-size buffering, which also passes here because the body is tiny. **duplicate of hono-5205** (same bug #4401) |
| hono-5202 | heldout | minor | yes | path only in lint commands. before/after cookie strings make the behaviour clear |
| hono-5205 | heldout | none | yes | thin (title only). the test only checks that two chunkings of a 1 MB body give equal ETags. duplicate of 5199 |
| hono-5209 | heldout | major | yes | names `checkOptionalParameter` in `src/utils/url.ts` plus the exact regex fix. f2p unit-tests that internal helper, so a rewrite must still point at optional-param expansion, not just at "routes misbehave" |
| hono-5215 | heldout | minor | yes | path in lint commands, "truthiness condition". behaviour well specified |
| hono-5226 | dev | major | partial | file, regex and exact diff given. the text also describes a `replacer` option that gold doesn't implement (harmless). the given regex `/^application\/(?:[a-z0-9._-]+\+)?json/i` has no end anchor, so it prettifies `application/json-seq` and **fails** f2p: `'Content-Type': 'application/json-seq'` gives `expect(await jsonSeqRes.text()).toBe('{"message":"Hono!"}')` |
| hono-5234 | dev | major | yes | file, code snippet and fix spelled out |
| hono-5239 | heldout | major | yes | not flagged: names `generateDigest()` and the `subarray()` to `slice()` fix. f2p imports `generateDigest` from `./digest` directly. follow-up to 5205 in the same function |
| hono-5244 | heldout | minor | yes | path in lint commands. behaviour clear, including "no empty Cookie header" |
| hono-5255 | dev | major | **no** | not flagged: names `defaultMatch`, `matchType`, `getSpecificity`. the text says global wildcards (`*/*`) should match supported types, but gold's `matchType` returns false for `*/*` and `*`, and hidden p2p tests (new, pass at base) require that. `'text/plain, */*;q=0.5'` with supports `['application/json']` gives `expect(result).toBe('text/html')`. `'*'` for Accept-Encoding gives `'identity'`. following the instruction regresses both |
| hono-5256 | heldout | major | yes | not flagged: names `proxyCallback`, `method === 'ws'`, `buildSearchParamsOption` and the exact rerouting |
| hono-5264 | dev | major | yes | file, `refCleanupMap`, root cause and a near-copy of the test |
| hono-5268 | heldout | none | yes | short but exact: `param('id')` is undefined, `param()` is `{}` |
| hono-5272 | heldout | major | yes | not flagged: names `buildSearchParams`, "the array branch", `=== undefined`, and `src/client/client.ts:70-73` (for the sibling form bug). f2p unit-tests `buildSearchParams` directly |
| hono-5280 | heldout | none | yes | thin (title only). hidden p2p keeps `''` entries. twin of 5272 on the form side |
| hono-5283 | heldout | minor | yes | path in verify commands. before/after table is behaviour |
| hono-5288 | dev | minor | yes | thin title but specific ("serialize cached JSON body in cloneRawRequest"). same function as 5133 |
| hono-5291 | heldout | minor | yes | behaviour table. 9 of the 10 f2p are existing ws tests with updated expected urls (`ws://localhost/`) |
| hono-5292 | dev | minor | yes | "truthiness check / undefined boundary" is a small hint. before/after table is clear |
| hono-5311 | heldout | major | yes | file paths plus `defaultMatch` and `detectFromHeader`. builds directly on 5255's code |
| hono-5329 | heldout | major | partial | file plus exact `oldVChildren[0]`/`shift()` fix. the test monkeypatches `Array.prototype.findIndex` and asserts `expect(findIndexCalls).toBe(0)` on an in-order rerender, which pins the implementation. a rewrite without the fix hint must say "no linear searches for in-order children" or the task becomes unfair. same issue (#5306) and loop as dev task 5340 |
| hono-5340 | dev | minor | partial | perf feature, and the issue explicitly says the approach is open. tests are white-box: import internal `build`/`buildNode`/`NodeObject` and inspect `vC`/`vR`/`pC`, count `key` getter reads (`large.old < small.old * 3`, `matchingReads < ids.length * 8`), and pin removal order (`removed.forEach((c,i) => expect(parent.vR[i]).toBe(c))`) |
| hono-5349 | heldout | major | yes | not flagged: gives the exact one-liner `parseQuality(accept.params.q ?? accept.params.Q)` |
| hono-5357 | heldout | major | yes | names `parseQuality` and the test file. before/after table is exact |
| hono-5366 | heldout | minor | yes | names private `#cachedBody()`. behaviour table is clear |
| hono-5379 | heldout | major | yes | not flagged: `verify()`, `decodeBase64Url()`, try/catch placement, test file path |
| hono-5380 | heldout | major | yes | both files plus the `[\s\S]*?` fix |
| hono-5424 | heldout | major | partial | file:line, function and full replacement code. f2p also needs case-insensitive matching of the general rule (`['APPLICATION/JSON', false]`, `['TEXT/PLAIN', false]`), which the text never mentions. its suggested code only puts `/i` on the new archive regex, so pasting it **fails** those two cases |
| hono-5426 | heldout | minor | yes | names `createResult()` and says "apply the same check as aws-lambda". at base the aws-lambda version (from 5424) is sitting in the repo, so this is a copy job. near-duplicate of 5424 |

### totals

- leak: **major 26**, **minor 16**, **none 8**
- sufficient: **yes 38**, **partial 9** (4988, 5084, 5094, 5171, 5179, 5226, 5329, 5340, 5424), **no 3** (5133, 5196, 5255)
- the auto check missed 9 tasks with a major leak: 4998, 5096, 5138, 5239, 5255, 5256, 5272, 5349, 5379. they need rewrites too. most leak through a function name plus a code snippet, not a file path.

## recommend drop

- **hono-5133**: the described bug is already fixed at base. the f2p targets a different function (`cloneRawRequest`) the text never mentions: `await req.formData(); const clonedReq = await cloneRawRequest(req)` then `expect(bodyText.startsWith(`--${boundary}`)).toBe(true)`.
- **hono-5196**: the instruction contradicts the test. it asks for a backward-compatible opt-in, but the test needs plain `etag()` to skip 404 and PUT: `c.text('not found', 404, { ETag: '"etag-123"' })` with `If-None-Match: '"etag-123"'` gives `expect(res.status).toBe(404)`.
- **hono-5171**: 378-line router restructure, 14 f2p, and behaviour changes the text says don't happen: `add('GET','/w/*/x'); add('GET','/w/:id/y')` then `match('/w/123/y')` must give `id === '123'`, and `add('GET','/:x{.}')` must throw `UnsupportedPathError`. too design-bound to be a fair task.
- **hono-5199**: same bug (#4401) and same function as hono-5205. keep 5205 (with a rewritten body) and drop 5199. 5199's test expects `'"d104fafdb380655dab607c9bddc4d4982037afa1"'`, which 5205's gold also satisfies.
- **hono-5329**: pins the implementation (`expect(findIndexCalls).toBe(0)` via a monkeypatched `Array.prototype.findIndex`). it is also the same issue and loop as dev task hono-5340, so heldout would overlap dev.

## recommend rewrite (keep the task)

- **hono-5255** (dev): say that `*/*` and `*` must **not** match (they fall through to the default) and that only `type/*` wildcards match. hidden p2p: `'text/plain, */*;q=0.5'` gives `'text/html'`, `'*'` gives `'identity'`. without that fix, drop it.
- **hono-4988**: drop the try/finally-only suggestion. state that after a failed `pipe()`, later `write()`/`pipe()` calls must still reach the client. test: `api.write('after pipe')` then `expect((await reader.read()).value).toEqual(encode('after pipe'))`.
- **hono-5424**: add that content-type matching must be case-insensitive. f2p: `['APPLICATION/JSON', false]`, `['TEXT/PLAIN', false]`. remove the pasted code.
- **hono-5226** (dev): say non-json subtypes like `application/json-seq` must be left alone, and drop the unimplemented `replacer` part. f2p: `application/json-seq` gives `'{"message":"Hono!"}'` unchanged.
- **hono-5094** (dev): specify first-callback-wins and reject on `callback(err)`. f2p: `rejects.toThrow('edge failure')`, and `expect(result).toBe(cf.request)` after two callback calls.
- **hono-5084**: say `*` only applies to GET/HEAD with a successful response. hidden p2p: PUT with `If-None-Match: *` gives `expect(res.status).toBe(201)`.
- **hono-5179**: mention the shared-promise context isolation and callback preservation, or drop those f2p. `expect(black.toString()).toBe('<span>black</span>')` and `expect((<Items />).toString()).toBe('ab')`.
- **hono-5340** (dev): white-box on internal render state. fine as a dev-only stress task, but don't read much into pass rates.
- **thin tasks** (5135, 5205, 5280, 5288): give each one sentence of observable behaviour. they are solvable from the title, but barely.
- **rewrites of tasks whose f2p calls an internal helper directly** (5096 `replaceUrlParam`, 5209 `checkOptionalParameter`, 5239 `generateDigest`, 5272 `buildSearchParams`, 5349/5357 `parseAccept`, 5102 `Node.search`): when removing the leak, keep enough to steer the fix into that helper. a fix one layer up (in the caller) is valid but fails the unit test.

## duplicates and near-duplicates

- **5199 = 5205**: same bug, same function (`generateDigest`). **5239** is a follow-up to 5205 in the same function, so it's 3 tasks on one 40-line function.
- **5424 ~ 5426**: the same content-type fix, ported from aws-lambda to lambda-edge. 5426's base already contains 5424's code to copy.
- **5272 ~ 5280**: `undefined` entry in a query array vs a form array, the same one-line guard. **5244** (undefined header/cookie) has the same theme.
- **5135 ~ 5138**: writeSSE drops a falsy field (`retry: 0` vs `id: ''`), the same line.
- **5329 (heldout) ~ 5340 (dev)**: both from issue #5306, same reconciliation loop in `jsx/dom/render.ts`.
- **5133 (heldout) ~ 5288 (dev)**: both `cloneRawRequest` re-serialising a cached body. **5366** is the same `#cachedBody` path.
- **5255 (dev) → 5311 (heldout)**: 5311 edits the code 5255 introduced (`defaultMatch`). **5349 ~ 5357**: both q-value parsing in `parseAccept`.
- **5084 / 5196 / 5234**: all 304 handling in `etag/index.ts`. etag is 6 of 50 tasks (12%).
- **5256 ~ 5291**: both `$ws` url construction in `hc`.

## dev vs heldout balance

- split is **10 dev / 40 heldout**. median changed lines is 7 in both. heldout mean is 21.7 vs 13.4, pulled up by 5171 (378 lines) and 5179 (71). dev max is 43.
- **all 6 multi-file tasks are heldout** (5067, 5141, 5171, 5179, 5311, 5380). dev has none. dropping 5171 helps; consider moving one small multi-file task (5141 or 5380) to dev.
- issue-sourced share is similar (dev 4/10, heldout 13/40). flagged share is similar (5/10 vs 21/40). both sets mix fixes with a feature or perf task (dev: 5226, 5340; heldout: 5141, 5171, 5179, 5329).
- every dev area also appears in heldout, and three dev tasks touch the exact function of a heldout task (5340/5329, 5288/5133, 5255/5311). if dev is used to tune the AGENTS.md setups, that's mild contamination. dropping 5329 and 5133 (already recommended for other reasons) removes two of the three.
- client (`src/client`) is the largest cluster: 10 tasks (2 dev, 8 heldout). etag is 6.

## other scope notes

- only 5094 touches tests outside `src/` (`runtime-tests/lambda-edge/index.test.ts`, edited but not in test_run_files).
- 5179's f2p list is inflated: 20 of its 22 `streaming.test.tsx` f2p are existing tests that fail at base only because a new test throws and breaks the shared `suspenseCounter`. pass/fail still works, but it's brittle.
- 5329 swaps `Array.prototype.findIndex` globally during the test, so any other `findIndex` in the render path counts against the agent.
- 5099 relies on `CompressionStream`/`DecompressionStream` (fine on node ≥18). 5059 is a bun adapter but fully mocked, so no bun runtime is needed.
