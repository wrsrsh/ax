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

what codex prints with `--json`: `thread.started`, `turn.started`, `item.started` / `item.completed` with item types `command_execution` (command, aggregated_output, exit_code), `file_change` (apply_patch: changes[path, kind], status) and `agent_message`, then `turn.completed` with usage `{input_tokens, cached_input_tokens, cache_write_input_tokens, output_tokens, reasoning_output_tokens}`, or `error` / `turn.failed`.
