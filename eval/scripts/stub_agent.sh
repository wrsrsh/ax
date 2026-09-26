#!/usr/bin/env bash
# $0 stand-in for codex: read, search and make one trivial edit to $STUB_FILE,
# with ax in setups B/C and cat/sed in A. prints codex-shaped --json events.
set -u
cd /w
f="$STUB_FILE"
n=0
ev() { printf '%s\n' "$1"; }
run() {
  n=$((n + 1))
  out=$(bash -c "$1" 2>&1); code=$?
  ev "{\"type\":\"item.completed\",\"item\":{\"id\":\"item_$n\",\"type\":\"command_execution\",\"command\":$(printf '%s' "$1" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))'),\"exit_code\":$code,\"status\":\"completed\"}}"
  echo "$out" >&2
}
ev '{"type":"thread.started","thread_id":"stub"}'
ev '{"type":"turn.started"}'
case "$STUB_SETUP" in
  B|C)
    run "ax read $f:1-20"
    run "ax grep -F export $f"
    lines=$(ax read "$f:1-1" | grep -oE '\(([0-9]+) lines' | grep -oE '[0-9]+')
    anchor=$(ax read "$f:$lines-$lines" | grep -oE "^ *$lines:[0-9a-f]+" | tr -d ' ')
    run "printf '@@ insert after $anchor\n// ax-eval stub\n' | ax edit $f"
    ;;
  *)
    run "cat $f | head -20"
    run "grep -n export $f | head -5"
    run "sed -i -e '\$a // ax-eval stub' $f"
    ;;
esac
ev '{"type":"item.completed","item":{"id":"msg","type":"agent_message","text":"stub done"}}'
ev '{"type":"turn.completed","usage":{"input_tokens":0,"cached_input_tokens":0,"output_tokens":0,"reasoning_output_tokens":0}}'
