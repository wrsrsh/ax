# what codex 0.156.0 actually offers the model

measured with `ax_eval.fakeapi` (a fake responses api) recording codex's first request. no model calls.

codex runs in "code mode": the model gets one javascript tool, `exec`, and calls nested tools through it (`await tools.exec_command({cmd})`). the nested tools are listed as `### \`name\`` sections inside `exec`'s description, not in a top-level `tools` field.

| setup | nested tools |
|---|---|
| default catalog (A, B) | apply_patch, exec_command, view_image, write_stdin, clock__curr_time (+ create_goal/get_goal/update_goal unless `--disable goals`) |
| catalog with `apply_patch_tool_type` removed (C) | exec_command, view_image, write_stdin, clock__curr_time |

so setup c = setup b minus apply_patch, and nothing else changes. `tests/test_capture.py` checks this whenever codex is installed.

other things every setup gets, equally:
- `--disable goals multi_agent apps browser_use computer_use image_generation in_app_browser plugins hooks`
- the `collaboration` namespace (spawn_agent etc.) can't be switched off with any feature flag in 0.156.0. `agents.max_concurrent_threads_per_session = 1` (0 is rejected) keeps it to the root thread, so no sub-agents.
- `request_user_input` stays; in `exec` mode nobody answers it.
- config lives in a fresh `CODEX_HOME` written by `ax_eval.setups`. `--ignore-user-config` is not used: it skips `$CODEX_HOME/config.toml` too, and codex then goes to api.openai.com instead of the configured provider.

what codex prints with `--json`: `thread.started`, `turn.started`, `item.started` / `item.completed` with item types `command_execution` (command, aggregated_output, exit_code), `file_change` (apply_patch: changes[path, kind], status) and `agent_message`, then `turn.completed` with usage `{input_tokens, cached_input_tokens, cache_write_input_tokens, output_tokens, reasoning_output_tokens}`, or `error` / `turn.failed`.

## turning code mode off (setups Ar / Br / Cr)

the `exec` tool comes from the catalog, not a feature flag: gpt-6-astra's entry has `"tool_mode": "code_mode_only"`. `--disable code_mode_host`, `--disable unified_exec`, `--disable shell_tool` and `shell_type = "shell_command"` all leave the model in code mode (shell_tool just removes exec_command from inside `exec`). deleting `tool_mode` from the entry gives plain function tools:

| catalog | what the model sees |
|---|---|
| stock | `exec` (js) with nested apply_patch, exec_command, view_image, write_stdin, clock__curr_time |
| `tool_mode` removed | top-level `exec_command`, `write_stdin`, `apply_patch`, `view_image`, `curr_time` |
| both `tool_mode` and `apply_patch_tool_type` removed | the same minus `apply_patch` |

`ax_eval.setups.catalog_for` does this; `Ar`/`Br`/`Cr` are `A`/`B`/`C` on the second and third rows. same AGENTS notes, same flags, same images. the collaboration tools (sleep, wait, spawn_agent...) are there in both modes.

why it matters: in code mode the model is already writing javascript to call tools, and can do file work inline instead of calling anything. `parse.py` counts `python -c` / `node -e` / heredoc scripts as `script` file ops (they count against ax in the fallback rate), and the raw setups ask whether ax helps more or less when tool calls are plain function calls.
