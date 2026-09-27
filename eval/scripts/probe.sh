#!/usr/bin/env bash
# isolation probe, run inside an agent container right before the agent starts.
# env: PROBE_SETUP (A|B|C|Ar|Br|Cr), PROBE_BASE (commit), PROBE_AGENTS_SHA (sha256 of the
# expected AGENTS.md), PROBE_HIDDEN (newline-separated test_patch paths),
# PROBE_ENV_KEY (name of the api key var, must not be in the container env),
# PROBE_AGENT (codex|claude, default codex), PROBE_NOTE (the note file, default AGENTS.md).
set -u
fail=0
ok() { echo "ok   $*"; }
bad() { echo "FAIL $*"; fail=1; }
note="${PROBE_NOTE:-AGENTS.md}"

for f in $(printf '%s\n' /root/.codex/config.toml "$HOME/.codex/config.toml" | sort -u); do
  [ -e "$f" ] && bad "host codex config present: $f" || ok "no $f"
done

if [ "${PROBE_AGENT:-codex}" = claude ]; then
  for f in $(printf '%s\n' /root/.claude /root/.claude.json "$HOME/.claude" "$HOME/.claude.json" | sort -u); do
    [ -e "$f" ] && bad "host claude state present: $f" || ok "no $f"
  done
  if [ "${CLAUDE_CONFIG_DIR:-}" != /claude-home ] || [ ! -d /claude-home ]; then
    bad "CLAUDE_CONFIG_DIR is '${CLAUDE_CONFIG_DIR:-}', want an empty /claude-home"
  else
    [ -z "$(ls -A /claude-home)" ] && ok "CLAUDE_CONFIG_DIR=/claude-home is empty" || bad "/claude-home not empty: $(ls -A /claude-home | tr '\n' ' ')"
  fi
  [ -e /etc/claude-code ] && bad "managed settings dir /etc/claude-code present" || ok "no managed settings"
  [ -e /w/.mcp.json ] && bad "project mcp config /w/.mcp.json" || ok "no /w/.mcp.json"
  [ -e /w/.claude ] && bad "project claude settings /w/.claude" || ok "no /w/.claude"
  [ -e /w/AGENTS.md ] && bad "AGENTS.md present for claude (its agents-md plugin reads it)" || ok "no AGENTS.md"
  leaked=$(env | cut -d= -f1 | grep -E '^ANTHROPIC_|^CLAUDE_CODE_(OAUTH|API_KEY)' | tr '\n' ' ')
  [ -z "$leaked" ] && ok "no anthropic vars in container env" || bad "anthropic vars in container env: $leaked"
  command -v claude >/dev/null && ok "claude on PATH" || bad "claude missing"
else
  cfg="${CODEX_HOME:-}/config.toml"
  if [ -z "${CODEX_HOME:-}" ] || [ ! -f "$cfg" ]; then
    bad "no generated codex config at \$CODEX_HOME"
  else
    grep -Eq '^\s*\[+\s*mcp_servers|^\s*mcp_servers\s*=' "$cfg" && bad "mcp servers in $cfg" || ok "no mcp servers in generated config"
  fi
  [ -d "${CODEX_HOME:-/nonexistent}/plugins" ] && bad "plugins dir in CODEX_HOME" || true
fi

cd /w || { bad "no /w"; exit 1; }
while IFS= read -r p; do
  [ -z "$p" ] && continue
  if git cat-file -e "$PROBE_BASE:$p" 2>/dev/null; then
    git diff --quiet "$PROBE_BASE" -- "$p" && ok "at base: $p" || bad "hidden test changed from base: $p"
  else
    [ -e "$p" ] && bad "hidden test present: $p" || ok "absent: $p"
  fi
done <<< "${PROBE_HIDDEN:-}"
[ -z "$(git status --porcelain --untracked-files=all -- . ":(exclude)$note")" ] && ok "clean tree at base" || bad "tree not clean"
[ "$(git rev-parse HEAD)" = "$(git rev-parse "$PROBE_BASE^{commit}")" ] && ok "HEAD is base" || bad "HEAD is not base"

case "$PROBE_SETUP" in
  B*|C*) command -v ax >/dev/null && ok "ax on PATH" || bad "ax missing in $PROBE_SETUP" ;;
  *) command -v ax >/dev/null && bad "ax present in $PROBE_SETUP" || ok "no ax in $PROBE_SETUP" ;;
esac

got=$(sha256sum "$note" 2>/dev/null | cut -d' ' -f1)
[ "$got" = "$PROBE_AGENTS_SHA" ] && ok "$note matches setup $PROBE_SETUP" || bad "$note mismatch ($got)"

if [ -n "${PROBE_ENV_KEY:-}" ] && [ -n "$(printenv "$PROBE_ENV_KEY")" ]; then bad "$PROBE_ENV_KEY is in the container env"; else ok "no api key in container env"; fi
[ "${AX_LOG:-}" = /out/ax_log.jsonl ] && ok "AX_LOG=/out/ax_log.jsonl" || bad "AX_LOG is '${AX_LOG:-}'"
mounts=$(awk '$4 != "/" && $5 !~ "^/(proc|sys|dev|etc/(hosts|hostname|resolv.conf))" && $9 !~ "^(proc|sysfs|tmpfs|devpts|mqueue|cgroup2?|overlay)$" {print $5}' /proc/self/mountinfo | sort -u | tr '\n' ' ')
[ "$mounts" = "/out " ] && ok "only /out is mounted" || bad "unexpected mounts: $mounts"

exit $fail
