# m7: external harnesses, what they look like on 2026-09-26

three harnesses we might use later: harbor (terminal-bench 2.0), mini-swe-agent (swe-rebench), edit-bench (+ tau). everything below was installed into a scratch venv under `eval/.cache/m7/` and checked with `--help` / by reading the installed source. no model calls, no paid runs. things marked **unverified** are from reading code or docs only.

| tool | pin | where |
|---|---|---|
| harbor | `harbor==0.23.0` (pypi, stable; nightly `0.23.1.devYYYYMMDD` builds land daily) | github.com/harbor-framework/harbor (laude-institute/harbor redirects there) |
| terminal-bench 2.0 | dataset `terminal-bench@2.0`, 89 tasks | harbor registry (legacy registry.json) |
| mini-swe-agent | `mini-swe-agent==2.4.6` (2026-07-23, still the latest tag) | github.com/SWE-agent/mini-swe-agent |
| swe-rebench | hf `nebius/SWE-rebench-leaderboard`, latest split `2026_03` | eval via github.com/SWE-rebench/SWE-bench-fork @ `e4907b7a90ea` |
| edit-bench | no release, no pypi; commit `a652e164da60` (2026-03-23, last push) | github.com/nwyin/edit-bench |
| tau | no release; main `5010f88050c4` (2026-04-24). hashline-era pin `1cd9c9712392` | github.com/nwyin/tau |

scratch venv, for reference (python 3.12, uv):

```
uv venv eval/.cache/m7/venv --python 3.12
uv pip install --python eval/.cache/m7/venv/bin/python harbor==0.23.0 mini-swe-agent==2.4.6 swebench==5.0.2 ./eval/.cache/m7/edit-bench
```

that pulled litellm 1.102.1 and datasets 5.0.1.

---

## 1. harbor (terminal-bench 2.0)

`pip install harbor==0.23.0`, python >= 3.12, needs docker (default env) or a cloud sandbox (`-e daytona|modal|e2b|...`). cli is `harbor` (aliases `hb`, `hr`). `harbor run` = `harbor job start`.

the old `terminal-bench` pypi package (0.2.18, `tb` cli) hasn't moved since 2025-09 and is superseded; tb 2.0 runs through harbor.

### running a tb2 subset

```
harbor download terminal-bench@2.0 -o eval/.cache/m7/tb2      # optional: task dirs to look at (verified, 89 tasks)

harbor run -d terminal-bench@2.0 \
  -a codex -m openai/gpt-6-astra --ak version=0.156.0 --ak reasoning_effort=medium \
  -i 'fix-git' -i 'large-scale-text-editing' -i 'kv-store-grpc' \
  -n 2 -k 1 -o eval/runs/harbor --job-name tb2-noax-smoke -y
```

relevant flags (all from `harbor run --help`, 0.23.0):
- dataset: `-d name@version`, `-p ./local/task-or-dataset`, `-i/--include-task-name <glob>` (repeatable), `-x/--exclude-task-name <glob>`, `-l/--n-tasks N` (applied after filters), `-t org/name` for one registry task.
- agent: `-a <builtin>` or `-a module.path:ClassName`, `-m model` (repeatable), `--ak key=value` agent kwargs (`harbor agent schema codex` lists them), `--ae KEY=VALUE` agent env, `--mcp-config`, `--skill`, `--allow-agent-host`.
- instructions: `--extra-instruction-path FILE` / `--extra-instruction TEXT` append to every task instruction.
- run: `-n` concurrent trials (default 4), `-k` attempts per task, `-r` max retries, `--timeout-multiplier`, `--agent-timeout-multiplier`, `--install-only`, `--disable-verification`, `--no-delete`, `--mounts '[...]'` (docker-compose volume syntax), `--override-cpus/--override-memory-mb`.
- `-c config.yaml` takes a JobConfig (schema: `harbor job schema`); `harbor job init` writes one from flags.
- `harbor job resume -p jobs/<name>` resumes, `harbor job regrade <job>` re-runs verifiers, `harbor view jobs` opens a web viewer.

tb2 shape (from the downloaded task.toml files): 89 tasks, 4 easy / 55 medium / 30 hard. 26 software-engineering, 5 debugging, 5 file-operations, the rest science/security/sysadmin/ml. agent timeouts 600s to 12000s, median 900s. no task sets a network policy (so full egress by default) and none need a gpu. each task pins a prebuilt image like `alexgshaw/large-scale-text-editing:20251031` (python:3.13-slim-bookworm base for that one).

### codex, and what the built-in agent does

`-a codex` (harbor/agents/installed/codex.py), read from source:
- install: apt-get installs curl/bash/nodejs/npm/ripgrep into the task image, then nvm + node 22 + `npm install -g @openai/codex@<version>` (latest if `--ak version` is unset). symlinks node/codex into /usr/local/bin.
- run: `CODEX_HOME=/tmp/codex-home`, writes `auth.json` from `OPENAI_API_KEY` (or uploads your real one with `CODEX_AUTH_JSON_PATH=...` / `CODEX_FORCE_AUTH_JSON=1`), uploads `--ak config=<config.toml or inline json>` as `$CODEX_HOME/config.toml`, then
  `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --model <m> --json --enable unified_exec [-c model_reasoning_effort=...] -- '<instruction>' | tee /logs/agent/codex.txt`
- afterwards copies `$CODEX_HOME/sessions` to `/logs/agent/sessions` and converts the rollout jsonl into `trajectory.json` (ATIF), then `rm -rf $CODEX_HOME`.

so our current codex flags (`--disable goals multi_agent ...`, `agents.max_concurrent_threads_per_session = 1`, the azure foundry provider, `model_catalog_json`) all have to go in through `--ak config=path/to/config.toml`. the catalog path inside that toml has to point at a file inside the container, so the custom agent below should upload it too. `--disable` flags have toml equivalents under `[features]`; **unverified** which exact keys 0.156.0 wants.

### custom agent: codex + ax on PATH + AGENTS.md note

tested with `--install-only` on `large-scale-text-editing` (no model call, 1m41s): codex 0.156.0 installed, `ax --version` ran inside the task container, AGENTS.md uploaded, no errors.

```python
# ax_codex.py  ->  harbor run -a ax_codex:AxCodex ...  (dir on PYTHONPATH)
import os, shlex
from pathlib import Path
from harbor.agents.installed.codex import Codex
from harbor.environments.base import BaseEnvironment

AX_BIN = Path(os.environ.get("AX_BIN", "ax"))          # static musl build, so any image works
AX_NOTE = Path(os.environ.get("AX_NOTE", "AGENTS.ax.md"))

class AxCodex(Codex):
    async def install(self, environment: BaseEnvironment) -> None:
        await super().install(environment)             # node + @openai/codex
        await environment.upload_file(AX_BIN, "/usr/local/bin/ax")
        await self.exec_as_root(environment, "chmod 755 /usr/local/bin/ax && ax --version")
        # codex reads $CODEX_HOME/AGENTS.md as global instructions. harbor's Codex.run()
        # sets CODEX_HOME=/tmp/codex-home and only mkdir -p's it, so this survives.
        home = self._REMOTE_CODEX_HOME.as_posix()
        await self.exec_as_agent(environment, f"mkdir -p {shlex.quote(home)}")
        await environment.upload_file(AX_NOTE, f"{home}/AGENTS.md")
        if environment.default_user is not None:
            await self.exec_as_root(environment, f"chown -R {environment.default_user} {shlex.quote(home)}")
```

```
cargo build --release --target x86_64-unknown-linux-musl     # static-pie, 10.8MB. the glibc build needs GLIBC_2.39, tb2 images ship 2.36
PYTHONPATH=path/to/dir AX_BIN=.../x86_64-unknown-linux-musl/release/ax AX_NOTE=eval/setups/AGENTS.ax.md \
harbor run -d terminal-bench@2.0 -i fix-git -a ax_codex:AxCodex -m openai/gpt-6-astra \
  --ak version=0.156.0 --ak config=eval/.cache/m7/codex-config.toml --ae <PROVIDER_KEY_VAR>=... \
  -o eval/runs/harbor --job-name tb2-ax-smoke -y
```

- that `$CODEX_HOME/AGENTS.md` is really picked up was checked separately with our fake responses api (`ax_eval.capture`, codex 0.156.0): the marker text shows up in the first request. writing AGENTS.md into the task workdir (`/app`) instead would pollute whatever the verifier diffs, so don't.
- the noax arm is the same class without the upload (or plain `-a codex`), but give both the same config.toml and the placebo note (`eval/setups/AGENTS.placebo.md`) so the arms only differ in ax.
- the agent keeps reporting `name() == "codex"`, so results show up as `codex__gpt-6-astra__terminal-bench`. tell the arms apart by `--job-name`. overriding `name()` looks possible, but `utils/traces_utils.py` does `AgentName(agent_name)`, which would throw on a custom name (**unverified** whether that path runs during normal jobs).
- alternative to uploading: `--mounts '["/abs/ax:/usr/local/bin/ax:ro"]'` (**unverified**).
- claude code: same pattern, subclass `harbor.agents.installed.claude_code.ClaudeCode`. the built-in agent already has `--ak append_system_prompt=...`, `--ak max_budget_usd=...`, `--ak max_turns=...`, `--ak allowed_tools/disallowed_tools`. it installs with `npm install -g @anthropic-ai/claude-code` and runs `--output-format=stream-json`.

### cost controls

- no job-level dollar cap in harbor. what there is: `-l/--n-tasks`, `-i/-x` filters, `-k`, `-n`, the task timeouts (`--agent-timeout-multiplier` scales them down), and per-agent kwargs. codex has no budget or turn flag, but claude-code (`max_budget_usd`, `max_turns`), mini-swe-agent (`cost_limit`), swe-agent (`per_instance_cost_limit`) and openhands (`max_budget_per_task`) do.
- cost is added up after the fact: `Codex._compute_cost_from_pricing` uses litellm's price table. litellm 1.102.1 has `gpt-6-astra` (openai, $10/M in) and `azure/gpt-6-astra`, so `cost_usd` should fill in (**unverified** end to end).
- a hard stop would have to be a job hook via the python api (`Job.on_trial_ended(cb)`, `--plugin module:Class` with `BaseJobPlugin.on_job_start/on_job_end`). **unverified** that a plugin can cancel pending trials.
- `--dry-run` validates config, preflight and task metadata without downloading or running anything. `--install-only` goes one step further (builds the env, installs the agent, no model call) and is the free local smoke test.

### output layout (verified from the install-only run + source)

```
jobs/<job-name>/
  config.json  result.json  job.log  lock.json
  <task>__<rand>/
    config.json  result.json  trial.log  exception.txt?
    agent/        codex.txt (codex --json stream), sessions/ (rollout jsonl), trajectory.json (ATIF), setup/
    verifier/     reward.txt or reward.json, test-stdout.txt, test-stderr.txt
    artifacts/
```

- trial `result.json`: `agent_info{name,version,model_info}`, `agent_result{n_input_tokens,n_cache_tokens,n_output_tokens,cost_usd,model_usage,metadata}`, `verifier_result{rewards:{...}}`, `exception_info`, timings (`environment_setup`, `agent_setup`, `agent_execution`, `verifier`).
- job `result.json`: `stats.evals["<agent>__<model>__<dataset>"]` has `n_trials, n_errors, metrics[{mean}], pass_at_k, reward_stats, exception_stats`, plus job-wide token and cost totals.
- `codex.txt` is the same `codex exec --json` event stream that `ax_eval.parse` already handles.

### risks / unknowns

- the installer apt-gets node/npm/ripgrep into the task image and runs nvm from raw.githubusercontent.com. that changes the environment the task author tested, and it's slow (about 80s per trial for setup). both arms pay it equally.
- azure foundry auth: harbor writes an OPENAI_API_KEY auth.json. our provider needs its own key env plus headers from config.toml. should be doable with `--ak config` + `--ae`, but **unverified**.
- `model_catalog_json` has to be uploaded into the container (the agent can do it in `install`), otherwise codex doesn't know gpt-6-astra's tool shape.
- tb2 is mostly not edit-heavy (sysadmin, crypto, ml). maybe 30 to 36 tasks are plausibly file-editing work. ax effects will be diluted.
- harbor moves fast (daily dev builds, lots of agents). pin `harbor==0.23.0` and codex `--ak version=0.156.0`.
- rewards are all-or-nothing per task. 89 tasks x k attempts at 900s+ each is expensive, so start with a small `-i` subset.

---

## 2. mini-swe-agent

`pip install mini-swe-agent==2.4.6`. clis: `mini` (local interactive), `mini-extra swebench | swebench-single | programbench | config | inspect`. v2 changed the config format (migration guide at klieret.short.gy/mini-v2-migration).

gotcha: every cli call creates `~/.config/mini-swe-agent/` and loads `.env` from there. set `MSWEA_GLOBAL_CONFIG_DIR=<scratch>` to keep it out of home.

### config format

yaml, merged recursively left to right with `-c`. passing any `-c` drops the default, so always list the base first:

```
mini-extra swebench -c swebench.yaml -c ax_overlay.yaml -c agent.step_limit=50 ...
```

sections are `agent` (`system_template`, `instance_template` as jinja, `step_limit`, `cost_limit`, `wall_time_limit_seconds`), `environment` (`environment_class`, `cwd`, `timeout`, `env`, `forward_env`, `run_args`, `interpreter`), `model` (`model_name`, `model_class`, `model_kwargs`, `cost_tracking`, `litellm_model_registry`, templates), and `run.env_startup_command` (a jinja template over the instance dict, run once after the container starts). the builtin `swebench.yaml` is tool-call based (one `bash` tool), step_limit 250, cost_limit 3, cwd `/testbed`, `BASH_ENV=/root/.bashrc` so conda's `testbed` env activates.

### adding ax + a system prompt note

verified: the merge below gives the new system_template, and the docker env with that `run_args` runs `ax --version` / `ax read` inside a debian container.

```yaml
# ax_overlay.yaml
agent:
  system_template: |
    You are a helpful assistant that can interact with a computer shell to solve programming tasks.

    <contents of eval/setups/AGENTS.ax.md>
  step_limit: 100
  cost_limit: 1.0
environment:
  run_args: ["--rm", "-v", "/abs/path/ax-musl:/usr/local/bin/ax:ro"]
```

- strings are replaced whole, not appended, so the overlay has to repeat the base system prompt line. the noax arm uses the same overlay with the placebo note and no mount.
- the ax binary must be the static musl build (swe images are ubuntu/conda, glibc version varies).
- other ways in: `run.env_startup_command` (e.g. to copy the binary or write a file into the repo) or a custom `environment_class`.

### swe-rebench

dataset ids on hf (checked via the datasets-server api):
- `nebius/SWE-rebench-leaderboard`: the monthly, decontaminated eval set. splits `test` (860) plus monthly `2025_01` .. `2026_03` (the newest has 110). fields include `image_name` = `swerebench/sweb.eval.x86_64.<id>:latest` and harbor resource hints (`harbor_cpus`, ...). last modified 2026-07-28.
- `nebius/SWE-rebench`: the big set (`test` 21,336, `filtered` 6,542), mini's built-in `--subset rebench` alias.
- `nebius/SWE-rebench-V2` (32k, multi-language, `train` only) and `-V2-PRs` are training sets, not for eval.

```
export MSWEA_GLOBAL_CONFIG_DIR=eval/.cache/m7/mswea-home MSWEA_GLOBAL_COST_LIMIT=5
mini-extra swebench \
  --subset nebius/SWE-rebench-leaderboard --split 2026_03 --slice 0:10 \
  -m <model> -c swebench.yaml -c ax_overlay.yaml \
  -w 4 -o eval/runs/mini/rebench-2026_03-ax
```

(`--split` defaults to `dev`, which rebench doesn't have. `--filter <regex>` / `--shuffle` / `--redo-existing` also exist.) mini picks the image from the instance's `image_name`/`docker_image` field, so rebench images get pulled as-is (**unverified** that every rebench image has the conda `testbed` env that `BASH_ENV` expects).

grading isn't in mini. use the swe-rebench fork of the swe-bench harness (upstream `swebench` 5.0.2 dropped `--namespace` and doesn't know rebench repos):

```
pip install git+https://github.com/SWE-rebench/SWE-bench-fork@e4907b7a90eafaa1f0a6428fd04fe31cdd8b4284
python -m swebench.harness.run_evaluation --dataset_name nebius/SWE-rebench-leaderboard --split 2026_03 \
  --predictions_path eval/runs/mini/rebench-2026_03-ax/preds.json --cache_level instance \
  --namespace swerebench --run_id ax-2026_03 --max_workers 4
```

(the command is from the fork's readme. not run here.) their readme reports mini-swe-agent 1.14.4 + minimax m2.5 at about 42% on 105 instances from 2026_01+02.

### model

`-m` is a litellm name. for gpt-6-astra through azure: `azure/gpt-6-astra` with `AZURE_API_KEY`/`AZURE_API_BASE`, and probably `--model-class litellm_response` (responses api; classes are `litellm`, `litellm_response`, `litellm_textbased`, `openrouter*`, `portkey*`, `requesty`, `deterministic`). **unverified**. litellm 1.102.1 prices `azure/gpt-6-astra`, so cost tracking works. unknown models need `model.cost_tracking: ignore_errors` or a `litellm_model_registry` json.

### cost controls and tracking

- per instance: `agent.cost_limit` (default 3.0, stops after going over), `agent.step_limit`, `agent.wall_time_limit_seconds`.
- global across the batch: env `MSWEA_GLOBAL_COST_LIMIT` / `MSWEA_GLOBAL_CALL_LIMIT` raise on the next model call once exceeded. that's a real hard-ish stop at the process level.
- cost per call comes from `litellm.completion_cost`. with `cost_tracking: default` a missing price is an error, not a silent zero.
- `models/test_models.py` has a scripted `deterministic` model class. could give a zero-cost plumbing run (not tried).

### outputs

```
<out>/preds.json                     {instance_id: {model_name_or_path, instance_id, model_patch}}  (swe-bench predictions format)
<out>/<instance_id>/<instance_id>.traj.json
<out>/exit_statuses_<ts>.yaml
<out>/minisweagent.log
```

`traj.json` (`trajectory_format: mini-swe-agent-1.1`) has `info.model_stats{instance_cost, api_calls}`, `info.exit_status`, `info.submission`, `info.config`, `info.mini_version`, and `messages[]`. each assistant message has `extra.response` (the full litellm response incl. `usage`), `extra.cost`, `extra.actions`, `extra.timestamp`. token counts are per message in `extra.response.usage`, not summed anywhere. `mini-extra inspect` browses them. harbor's mini-swe-agent adapter already has a traj -> ATIF converter if we want one format.

### risks / unknowns

- the agent under test would be mini's bash-only loop, not codex. ax results there say "ax helps a minimal agent", not "ax helps codex". that's a different claim.
- submission is `git diff > patch.txt; echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt`. ax edits are fine with that, but the instance prompt's "use sed/cat" style guidance competes with the ax note, and we'd have to edit `instance_template` too.
- rebench images are big (GBs each), pulled per instance. disk plus pull time is real.
- the exact grading command for monthly splits (`--split 2026_03` vs the `test` split) is **unverified**.

---

## 3. edit-bench (+ tau)

no package on pypi. install from source: `uv pip install ./edit-bench` (python >= 3.12, no deps). two entry points.

### generating tasks

```
edit-bench-generate --source-dir <dir> [<dir> ...] --lang {python,rust,go,typescript,javascript} \
  --max-tasks 20 --seed 42 [--hard] [--min-lines 30] [--exclude-mutations delete-statement ...] --output-dir fixtures
```

verified on our hono checkout (`--lang typescript --max-tasks 8`): it makes 8 fixtures across swap-adjacent-lines, rename-partial, flip-boolean, remove-optional-chain, unicode-hyphen, delete-statement, duplicate-line-flip, swap-args. how it works: collects files of that language (30 to 800 lines; `--hard` means >= 100 lines and sorts by an "ambiguity" score), finds mutation candidates (generic plus per-language: 4 go, 4 rust, 4 ts), picks them round-robin across mutation types, applies one mutation per task, and writes

```
fixtures/<mutation>-<nnn>/input/<file>  expected/<file>  prompt.md  metadata.json
```

difficulty (easy = gets the line number, medium, hard, nightmare = "there is a subtle bug") is scored from the file and match. single file per task, and the file is copied alone into a temp dir. gotchas: it `rm -rf`s `--output-dir` first, and it happily picks test files (`index.test.ts`).

### running

```
edit-bench-run --fixtures fixtures --model <tau model id> --edit-mode {replace,hashline} \
  [--runs 1] [--timeout 120] [--max-turns 10] [--max-attempts 1] [--no-op-retry-limit 2] [-j 4] \
  [--oneshot] [--tau /path/to/tau] [--lang ts] [--output runs]
```

- default is rpc mode. it spawns `tau serve --cwd <tmp> --model M --tools file_read,file_edit,file_write`, sends the templated prompt, waits for `session.status: idle`, then diffs the file against `expected/`. on failure it retries with the diff (`--max-attempts`), and a prompt with no edit gets up to 2 free "you must edit" retries.
- scoring: normalize line endings and trailing whitespace, restore whitespace-only line diffs, collapse blank lines, then format both sides (`uvx ruff format`, `rustfmt`, `gofmt`, `npx prettier`) and compare exactly. a missing formatter only warns and falls back to the raw text.
- `--edit-mode` does not change the tool list (always `file_read,file_edit,file_write`). it only writes `edit_mode = "<mode>"` into `~/.tau/config.toml`, and tau was supposed to swap the tool implementation behind the same names.
- outputs: `runs/<model>_<mode>_<ts>.md` (tables by mutation, language, difficulty, plus failure diffs) and `.json` (`config`, `summary{total_runs,passed,failed,success_rate,total_tokens,total_time_ms}`, `results[{task_id,run_index,success,exit_code,wall_clock_ms,input_tokens,output_tokens,tool_calls,error_message}]`). no cost in usd. in rpc mode tokens come from tau's `session.status` usage. oneshot adds `--trace-output`, and tau's `run.json` there also has `total_cost`.

### tau, and the state of hashline

`tau` is nwyin's rust harness (`cargo install --path coding-agent`). built main here (1m36s). `tau --help`: `-p/--prompt (- = stdin)`, `-m`, `--system-prompt`, `--tools a,b,c`, `--yolo`, `--thinking`, `--no-session`, `--skill PATH`, `--no-skills`, `--trace-output DIR`, `--stats-json`, `--task-id`. subcommands `serve` (json-rpc on stdio: `--cwd --model --tools --trace-output --task-id`, always yolo) and `models`.

- **hashline is gone from tau main.** it was added 2026-03-19 and removed in `1dfcab778fb6` ("remove hashline editing, default to replace-only", 2026-04-02). tau's config struct is `serde(default)` without `deny_unknown_fields`, so edit-bench's `edit_mode = "hashline"` is silently ignored: **`--edit-mode hashline` against tau main just runs replace.** to reproduce the hashline arm, pin tau to `1cd9c9712392` (parent of the removal).
- custom tools: **no plugin, mcp or external-tool mechanism.** tools are a static rust table (`coding-agent/src/tools/registry.rs`, `DIRECT_TOOL_SPECS`: bash, file_read, file_edit, file_write, glob, grep, web_fetch, web_search, subagent, todo, py_repl, thread, ...). adding one means implementing `agent::types::AgentTool` (`name/label/description/parameters/execute`) and registering it. skills exist (`.tau/skills/`, `~/.tau/skills/`, `--skill`), but they're progressive disclosure, invoked with `/skill:name`. not a system prompt note. tau doesn't read AGENTS.md.
- models: hardcoded catalog (`ai/src/catalog.rs`, gpt-5.4 family, claude, openrouter, groq, ...). keys come from `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/..., with **no base-url override and no gpt-6-astra.** running our model means patching the catalog (model entry + azure base url + auth header).

### what an `ax edit` mode would take

two options, cheapest first:

1. **bash + note (edit-bench-only patch, about 20 lines).** add `ax` to `--edit-mode` choices, make `_tools_for_mode("ax")` return `bash` (maybe `bash,file_read`), and for that mode prepend `eval/setups/AGENTS.ax.md` to `PROMPT_TEMPLATE` (the template says "use the edit tool", which needs rewording per mode). put the musl ax on PATH. this compares "ax through a shell" against "native replace tool", which is closest to how codex actually sees ax.
2. **native `ax_edit` tool in tau (rust, about 100 to 150 lines).** an `AgentTool` whose `execute` runs `ax edit <path>` with the body on stdin (and maybe `ax_read` wrapping `ax read`), registered next to `file_edit`, plus a mode in edit-bench that selects `file_read→ax_read, file_edit→ax_edit` or a tau config switch like the old hashline one. cleaner tool-vs-tool comparison, but it tests ax's edit format more than the cli.

either way we'd also have to fix these edit-bench things:
- rpc mode ignores `--tau` (`TauRpcClient` hardcodes `"tau"` from PATH), so put the right binary first on PATH.
- it writes `~/.tau/config.toml`, so run with `HOME=<scratch>`.
- tau needs the gpt-6-astra/azure catalog patch above.
- oneshot mode doesn't pass `--yolo`. tools with an `ask` policy may stall there (**unverified**). rpc mode is yolo.

### cost controls

`--max-turns` (sets `TAU_MAX_TURNS`), env `TAU_MAX_API_REQUESTS`, `--max-attempts`, `--no-op-retry-limit`, `--timeout`, `--runs`, and the fixture count. no dollar cap. tokens per run are in the json report. single-file tasks with short prompts are cheap per run (the bulk is the file read), so this is the cheapest of the three by far.

### risks / unknowns

- the repo is small and was last touched 2026-03-23. `docs/*-spec.md` describe a "v2" (verifier tiers, manifests) that isn't implemented. treat it as a script to fork, not a dependency.
- the hashline result that motivated it can't be reproduced on tau main (see above).
- scoring is exact text after formatting. ax's own formatting-neutral edits should be fine, but a mode that rewrites whole files (`ax write`) could trip on formatter differences for languages without a formatter installed.
- mutations are single-token or single-line, one file. that's narrower than our hono tasks.
- tau catalog/auth for gpt-6-astra is a patch we'd own.

---

## bottom line

- harbor + tb2 is ready: a 15-line subclass puts ax and the AGENTS.md note into stock codex, verified up to install. the open work is our azure codex config inside the container and picking an edit-heavy subset.
- mini-swe-agent + swe-rebench-leaderboard is ready: yaml overlay + docker `run_args` mount (verified), `MSWEA_GLOBAL_COST_LIMIT` as a hard stop, grading through the swe-rebench swe-bench fork. but it measures mini's agent, not codex.
- edit-bench needs work: tau has no custom tools, no longer has hashline, and doesn't know our model. forking edit-bench with a bash+ax mode is small. a native tau tool is a rust patch.
