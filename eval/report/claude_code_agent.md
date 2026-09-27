# claude code as a second agent

claude code runs the same tasks under the same A/B/C setups as codex. everything below was checked on 2026-09-27 against claude code **2.1.283** (the version installed on this host, `claude --version`) talking to a fake messages api (`ax_eval.fakeapi_anthropic`). no model calls, $0.

## what it looks like

- image: `ax-agent:<hash>-claude-noax` / `-claude-ax`, built from the task image with `npm i -g @anthropic-ai/claude-code@2.1.283` (label `org.ax.claude`). the ax variant copies in the same static musl ax. `uv run python -m ax_eval.images --all --agent claude` builds them all, otherwise the runner builds on first use.
- note: the same text as codex's AGENTS.md (placebo in A, the ax note in B/C), written to `/w/CLAUDE.md`, added to `.git/info/exclude` and left out of `final.diff`. the probe checks its sha and that there's no AGENTS.md next to it (claude code has a builtin `agents-md` plugin that would read one).
- home: `CLAUDE_CONFIG_DIR=/claude-home`, an empty dir made fresh per container. HOME stays /root like it is for codex, and the probe fails if `/root/.claude` or `/root/.claude.json` exist.
- key: never in the container env. the runner reads it from its own env (`$ANTHROPIC_API_KEY`, or whatever `--env-key` names) and hands it to `docker exec -e ANTHROPIC_API_KEY` for the claude process only (`ANTHROPIC_AUTH_TOKEN` if you pass `--env-key ANTHROPIC_AUTH_TOKEN`, for a gateway). `ANTHROPIC_BASE_URL` goes in the same way, default `https://api.anthropic.com`.
- container env: `CLAUDE_CONFIG_DIR`, `DISABLE_AUTOUPDATER=1`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, `IS_SANDBOX=1`. the last one is needed because the task images run as root and claude code otherwise refuses with "--dangerously-skip-permissions cannot be used with root/sudo privileges" (seen on the first dry run).

the command, prompt on stdin (`setups.claude_args`):

```
claude -p --output-format stream-json --verbose \
  --model claude-opus-5 --effort medium --max-turns 100 \
  --permission-mode bypassPermissions \
  --strict-mcp-config --setting-sources project --settings '{"autoMemoryEnabled": false}' \
  --disable-slash-commands --no-session-persistence \
  --tools Bash,Read,Edit,Write,Glob,Grep            # C: --tools Bash,Read,Glob,Grep --disallowedTools Edit,Write,MultiEdit,NotebookEdit
```

why each one:

- `--output-format stream-json --verbose`: one json event per line, which is what `parse.py` reads. without `--verbose` stream-json only prints the result.
- `--max-turns`: not in `--help` any more, but it works. it counts model requests, not tool calls: `--max-turns 2` made 2 requests and ended with `subtype: error_max_turns`, `terminal_reason: max_turns`, exit 1. the runner maps that to `turn_capped`. `--turn-cap N` sets it, default 100. codex's turn cap counts tool calls instead (and a claude turn can hold parallel tool calls), so the two caps aren't the same thing.
- `--effort medium`: matches codex's medium. it shows up as `output_config: {effort: "medium"}`, with `thinking: {type: "adaptive"}` next to it. opus 5 defaults to high, so this is a choice, see open questions.
- `--permission-mode bypassPermissions`: no prompts, like codex's `--dangerously-bypass-approvals-and-sandbox`.
- `--strict-mcp-config` with no `--mcp-config`: no mcp servers. init event says `mcp_servers: []`.
- `--setting-sources project`: user and local settings don't load. it has to include `project`, because that's also what loads `/w/CLAUDE.md`: with `--setting-sources ""` the note silently disappeared from the request. the probe fails if `/w/.claude` or `/w/.mcp.json` exist, so project settings can't bring anything else in.
- `--settings '{"autoMemoryEnabled": false}'`: without it the system prompt has a "# Memory" section pointing the model at a persistent memory dir under the config dir. gone with it (captured).
- `--disable-slash-commands`: no skills. without it the init event lists ~40 slash commands/skills (claude-api, code-review, dataviz, ...) and a Skill tool.
- `--tools ...`: an allowlist rather than a denylist. the default `-p` tool list in 2.1.283 is Agent, Bash, CronCreate/Delete/List, Edit, EnterWorktree, ExitWorktree, ListAgents, NotebookEdit, Read, ReportFindings, ScheduleWakeup, SendMessage, Skill, TaskStop, WebFetch, WebSearch, Workflow, Write. subagents, web, cron and worktrees go, the same way codex loses multi_agent, browser_use and friends (a worktree tool would even move the agent out of /w). Glob and Grep are *not* in the default list any more but still exist, so they're named. MultiEdit and TodoWrite don't exist in this version; naming them is silently ignored.
- `--no-session-persistence`: nothing written to disk for resuming.

## tool surface per setup (captured)

from the init event and the first request body, host claude and inside the agent images (dry runs below):

| setup | tools offered | note |
|---|---|---|
| A | Bash, Edit, Glob, Grep, Read, Write | placebo CLAUDE.md, no ax on PATH |
| B | Bash, Edit, Glob, Grep, Read, Write | ax CLAUDE.md, ax on PATH |
| C | Bash, Glob, Grep, Read | ax CLAUDE.md, ax on PATH, edits have to go through the shell |

- same system prompt in all three (6,915 chars in the fake capture), tool definitions 10,347 chars of json in A/B, 8,674 in C. the note arrives inside the first user message as a `Contents of /w/CLAUDE.md (project instructions, ...)` system-reminder, next to a git status block.
- in C, a model that asks for Edit anyway gets `No such tool available: Edit. Edit is disabled for this session` back as an error tool_result, and the file is untouched (fixture `setup_c_edit.jsonl`, and `test_capture_claude.py`). that counts as a failed patch.
- Read and Grep stay in C on purpose: the issue only takes away the edit tools, the way codex's C only loses apply_patch. that means claude's C still has a non-shell read and search path that codex's C doesn't.
- request shape: `POST /v1/messages?beta=true`, streamed, `max_tokens: 64000`, `thinking: adaptive`, `context_management: clear_thinking_20251015 keep all`. no side requests (titles, quota checks) showed up with nonessential traffic off. when all retries fail it also does `GET /v1/models` and `GET /health`.

## parsing

`parse.py` tells the two streams apart by shape (claude events carry `session_id` on system/assistant/result).

- every `tool_use` block counts once (stream-json repeats the message per content block, so they're deduped by tool_use id). Bash goes through the same `kinds()` as codex's shell commands, so `ax read`, `sed`, `python3 -c` etc. land in the same buckets. the other tools are their own kinds: `Read`, `Edit`, `Write`, `Glob`, `Grep`. they count as file ops for `fallback_rate`, since they're the non-ax way to do the same thing.
- an error tool_result on Edit/Write/MultiEdit/NotebookEdit is a failed patch, on anything else a failed command.
- usage comes from the final `result` event. anthropic's `input_tokens` is only the uncached part, so: `uncached_input_tokens = input_tokens`, `cache_write_input_tokens = cache_creation_input_tokens`, `cached_input_tokens = cache_read_input_tokens`, `input_tokens` (row) = all three added up, `output_tokens` as is, `reasoning_tokens` = `output_tokens_details.thinking_tokens`. with the `claude-opus-5` entry in prices.json ($5 / $0.50 read / $6.25 write / $25 out) our cost matches claude code's own `total_cost_usd` to the cent on every dry run.
- also kept: `turns` (num_turns), `stop` (terminal_reason), `reported_cost` (total_cost_usd), `api_retries` (count of `system/api_retry` events), `agent`.
- if the run gets killed before `result`, usage falls back to the assistant events. output tokens there are from the stream start, so they undercount.
- `completed` means `subtype: success` and not `is_error`. an api failure ends as `is_error: true, api_error_status: 529, terminal_reason: api_error`; that becomes `error: "529: API Error: ..."`, which `infra_reason` treats as infra (retried under a new run id). hitting max turns is a result, not infra.

## dry runs

all at $0 against the fake api, reached from the container as host.docker.internal:

- `uv run python -m ax_eval.runner --tasks dev --setups A B C --agent claude --dry-run --parallel 3`: 30 runs (10 dev tasks x A/B/C), 0 infra failures, 0 probe FAILs, every diff has the fake edit and nothing else (no CLAUDE.md, no `.claude/`), `ax read` counted in B/C, cost 0.02925 per run both by our formula and by claude code's. about 2 minutes including building the claude images.
- the `--paid` code path, pointed at the same fake with a bogus key (`--api-base-url http://host.docker.internal:<port> --est 0.05 --max-run-usd 1`): ran clean, ledger row `dry: false` (in a scratch ledger). `table.py` still marks it dry because of the local base url.
- pytest: `test_runner.py::test_claude_against_fake_api[A|B|C]` does one of these per setup, `test_probe_catches_claude_leaks` checks the probe fails on a host ~/.claude, a key in the env, `/w/.claude`, a stray AGENTS.md and a wrong note. `test_capture_claude.py` runs the host claude (skips unless it's 2.1.283) for the tool surface, the C edit refusal and max-turns. `test_parse_claude.py` covers the fixtures in `tests/fixtures/claude/` (made from real 2.1.283 output against the fake api).

## still unknown

- **nothing has touched a real model.** the tool surface is what 2.1.283 sends; how opus 5 actually behaves with it (parallel tool calls, how often it reaches for Read/Grep vs the shell, whether it follows the ax note) is the point of a pilot.
- `--max-turns` is undocumented in 2.1.283's `--help`. it works today, it could go away in an update. the version is pinned in the image, so that only matters when bumping it.
- whether `result.usage.output_tokens` already includes thinking tokens (it should, the api bills them as output), and whether claude code sums usage exactly the way it bills when a request is retried mid-stream. the fake never produces thinking tokens or mid-stream failures.
- claude code retries api errors itself (up to 10 times, exponential backoff, `CLAUDE_CODE_MAX_RETRIES`). codex is set to 0 retries so errors become harness retries. with claude, transient errors stay inside the run and show up as wall time plus `api_retries`. a run that burns all 10 is an infra failure like with codex.
- the placebo note was matched to the ax note with o200k (openai's tokenizer). with claude's tokenizer they're probably not as close: the placebo prompt was 3,216 chars vs 2,720 for B in the capture. `count_tokens` needs a key; check it before comparing A vs B for claude.
- effort: medium to match codex, but opus 5's api default is high and claude code may default higher still. if the question is "does ax help claude code as people run it", high might be the fairer setting.
- claude's A/B/C aren't the same as codex's A/B/C: claude keeps native Read/Grep/Glob in every setup (codex has only the shell plus apply_patch). compare setups within an agent, not across agents.
- `report.py` / `stats.py` group by setup, not by agent. claude runs belong in their own runs dir (see below) until the report learns about agents, otherwise codex and claude rows would get averaged together.
- network: the container has normal egress, same as codex. with nonessential traffic off nothing but the messages api showed up at the fake, but a real run wasn't sniffed.

## launching a paid pilot

only once the gate for it is approved. $384.73 is spent so far out of the $2,000 cap (ledger as of this commit). a dev pilot is 10 tasks x 3 setups = 30 runs; codex averaged $1.04 a run, opus 5 is half gpt-6-astra's price per token but claude code sends a bigger prompt, so `--est 1.5` for the budget check and a hard `--max-run-usd 5` per run (claude code's own `--max-budget-usd`).

```
cd eval
uv run python -m ax_eval.images --all --agent claude            # optional, the runner builds on first use
export ANTHROPIC_API_KEY=...                                    # stays in this shell, only reaches `docker exec -e`
uv run python -m ax_eval.runner --tasks dev --setups A B C --repeats 1 --seed 0 \
  --agent claude --paid --model claude-opus-5 --effort medium \
  --est 1.5 --max-run-usd 5 --parallel 3 \
  --runs-dir runs-claude --ledger runs/ledger.jsonl
uv run python -m ax_eval.table --runs runs-claude --report report/claude
```

- `--ledger runs/ledger.jsonl` keeps one ledger, so the $2,000 cap covers codex and claude together. `--runs-dir runs-claude` keeps the run dirs out of `runs/`, so the codex table and report don't pick them up. `runs-claude/*/` is gitignored like `runs/*/`.
- for a gateway instead of anthropic directly: add `--api-base-url https://...` and, if it wants a bearer token, `--env-key ANTHROPIC_AUTH_TOKEN`.
- `--turn-cap` changes `--max-turns` (default 100). `--time-cap` (default 1200s) works the same as for codex.
