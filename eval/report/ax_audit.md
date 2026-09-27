# ax exit audit

from `runs/runs.jsonl`: 360 non-dry held-out runs (A 120, B 120, C 120), 4,851 shell commands, 2,405 of them invoke ax.

a non-zero exit counts against ax only when the ax segment is the last one in the shell line, or the output starts with an ax-style error (`error:`, `ax:`, `<path>: stale anchor`, `... isn't`, `no such path`, `unexpected argument`, `nothing written (...)`), or an unambiguous ax refusal line shows up later in the output (the `&&` chain stopped there). two tweaks: an ax that's last but printed no ax error didn't fail (an earlier `&&` link did), and the subcommand is the ax segment the error line names. everything else is the other command's exit (tests, tsc, prettier). heredoc bodies aren't commands; what runs after the terminator is.

## non-zero exits

- 143 commands that invoke ax exited non-zero.
- 28 are ax's: 27 ax is the last segment, 1 output starts with an ax error.
- by setup: B 10, C 18.
- 115 belong to another command (114 after ax, 1 before ax): `bun run test` 55, `bunx vitest` 28, `bun run vitest` 7, `bun x vitest` 5, `bunx tsc` 5, `npx vitest` 5, `node` 4, `bunx prettier` 3, `git` 2, `vitest` 1.

## ax failures by subcommand and kind

| subcommand | usage error | stale anchor | no match | parse-rejected | missing path | other | total |
|---|---|---|---|---|---|---|---|
| `ax grep` | 7 |  |  |  | 2 |  | 9 |
| `ax read` |  |  |  |  | 6 |  | 6 |
| `ax find` | 5 |  |  |  |  |  | 5 |
| `ax edit` |  | 3 | 1 |  |  |  | 4 |
| `ax write` | 2 |  |  |  |  |  | 2 |
| `ax map` | 1 |  |  |  |  |  | 1 |
| `ax outline` |  |  |  |  | 1 |  | 1 |
| **total** | 15 | 3 | 1 |  | 9 |  | 28 |

## examples

### usage error

- `ax map src/adapter/lambda-edge runtime-tests/lambda-edge`  
  -> `error: unexpected argument 'runtime-tests/lambda-edge' found` (20260926T163102-hono-5094-B-r2-236d)
- `ax find '*test*' src/jsx && ax diff --stat`  
  -> `error: unexpected argument 'src/jsx' found` (20260926T164509-hono-5380-B-r0-8648)
- `ax read src/request.test.ts:1-220; ax grep 'notFound|param\(' src/hono.test.ts -m 15`  
  -> `error: unexpected argument '-m' found` (20260926T164648-hono-5268-C-r0-fc79)

### stale anchor

- `ax edit src/request.ts <<'EOF' ⏎ @@ replace 485:ff79..487:3a48 ⏎ EOF`  
  -> `src/request.ts: stale anchor 487:3a48: that line changed since you read it. current lines:` (20260926T163149-hono-5288-C-r2-dd5e)
- `ax edit src/adapter/lambda-edge/handler.test.ts <<'EOF' ⏎ @@ insert before 1:4c30 ⏎ EOF`  
  -> `src/adapter/lambda-edge/handler.test.ts: stale anchor 1:4c30: that line changed since you read it. current lines:` (20260926T164234-hono-5099-C-r2-1e46)
- `ax edit src/adapter/lambda-edge/handler.ts <<'EOF' ⏎ @@ replace 150:1b9e ⏎ EOF`  
  -> `src/adapter/lambda-edge/handler.ts: stale anchor 150:1b9e: that line changed since you read it. current lines:` (20260926T164234-hono-5099-C-r2-1e46)

### no match

- `ax edit src/utils/jwt/jwt.test.ts <<'EOF' ⏎ @@ find ⏎ describe('verifyWithJwks security', () => { ⏎ @@ with ⏎ describe(…`  
  -> `src/utils/jwt/jwt.test.ts: find text " describe('verifyWithJwks security', () => {" isn't in the file exactly. closest: ` (20260926T164714-hono-5379-C-r0-6d94)

### missing path

- `ax read src/middleware/etag/digest.ts src/middleware/etag/digest.test.ts vitest.config.ts src/middleware/etag/index.tes…`  
  -> `src/middleware/etag/digest.test.ts: no such file or directory (os error 2)` (20260926T163844-hono-5205-C-r1-70c8)
- `ax grep 'spyOn|restoreAllMocks|SignatureMismatched' src/utils/jwt/jwt.test.ts src/middleware/jwt/jwt.test.ts`  
  -> `ax: no such path: src/middleware/jwt/jwt.test.ts` (20260926T164714-hono-5379-C-r0-6d94)
- `ax read src/jsx/intrinsic-element/components.ts src/jsx/intrinsic-element/index.ts && ax find '*intrinsic*' && ax grep …`  
  -> `src/jsx/intrinsic-element/index.ts: no such file or directory (os error 2)` (20260926T165341-hono-5204-C-r1-f744)

## cross-check with ax's own log

`ax_log.jsonl` records every ax call that got past argument parsing (clap usage errors exit before it), including ones hidden inside a shell line that still exited 0 (`ax read missing; ax grep x`).

- 20 ax calls exited non-zero: read 10, edit 4, write 3, grep 2, outline 1; outcomes none 10, error 6, stale 3, no-match 1.
- 12 of 2,903 log lines don't parse (parallel ax calls interleaving their appends).

## habits

- first command of the run is `ax map`: A 0/120, B 120/120, C 120/120.
- first ax command of the run is `ax map`: A 0/120, B 120/120, C 120/120.
- runs that call `ax find AGENTS.md`: A 0/120, B 120/120, C 115/120.

## output size of successful calls

lines of output for exit-0 calls where ax is the only command on the line.

| subcommand | calls | median lines | mean lines |
|---|---|---|---|
| `ax edit` | 487 | 14 | 24.4 |
| `ax read` | 478 | 286.5 | 328.1 |
| `ax diff` | 193 | 73 | 70.5 |
| `ax map` | 253 | 50 | 48.0 |
