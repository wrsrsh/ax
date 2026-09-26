#!/usr/bin/env bash
# isolation probe, run inside an agent container right before the agent starts.
# env: PROBE_SETUP (A|B|C|Ar|Br|Cr), PROBE_BASE (commit), PROBE_AGENTS_SHA (sha256 of the
# expected AGENTS.md), PROBE_HIDDEN (newline-separated test_patch paths),
# PROBE_ENV_KEY (name of the api key var, must not be in the container env).
set -u
fail=0
ok() { echo "ok   $*"; }
bad() { echo "FAIL $*"; fail=1; }

for f in $(printf '%s\n' /root/.codex/config.toml "$HOME/.codex/config.toml" | sort -u); do
  [ -e "$f" ] && bad "host codex config present: $f" || ok "no $f"
done

cfg="${CODEX_HOME:-}/config.toml"
if [ -z "${CODEX_HOME:-}" ] || [ ! -f "$cfg" ]; then
  bad "no generated codex config at \$CODEX_HOME"
else
  grep -Eq '^\s*\[+\s*mcp_servers|^\s*mcp_servers\s*=' "$cfg" && bad "mcp servers in $cfg" || ok "no mcp servers in generated config"
fi
[ -d "${CODEX_HOME:-/nonexistent}/plugins" ] && bad "plugins dir in CODEX_HOME" || true

cd /w || { bad "no /w"; exit 1; }
while IFS= read -r p; do
  [ -z "$p" ] && continue
  if git cat-file -e "$PROBE_BASE:$p" 2>/dev/null; then
    git diff --quiet "$PROBE_BASE" -- "$p" && ok "at base: $p" || bad "hidden test changed from base: $p"
  else
    [ -e "$p" ] && bad "hidden test present: $p" || ok "absent: $p"
  fi
done <<< "${PROBE_HIDDEN:-}"
[ -z "$(git status --porcelain --untracked-files=all -- . ':(exclude)AGENTS.md')" ] && ok "clean tree at base" || bad "tree not clean"
[ "$(git rev-parse HEAD)" = "$(git rev-parse "$PROBE_BASE^{commit}")" ] && ok "HEAD is base" || bad "HEAD is not base"

case "$PROBE_SETUP" in
  B*|C*) command -v ax >/dev/null && ok "ax on PATH" || bad "ax missing in $PROBE_SETUP" ;;
  *) command -v ax >/dev/null && bad "ax present in $PROBE_SETUP" || ok "no ax in $PROBE_SETUP" ;;
esac

got=$(sha256sum AGENTS.md 2>/dev/null | cut -d' ' -f1)
[ "$got" = "$PROBE_AGENTS_SHA" ] && ok "AGENTS.md matches setup $PROBE_SETUP" || bad "AGENTS.md mismatch ($got)"

if [ -n "${PROBE_ENV_KEY:-}" ] && [ -n "$(printenv "$PROBE_ENV_KEY")" ]; then bad "$PROBE_ENV_KEY is in the container env"; else ok "no api key in container env"; fi
[ "${AX_LOG:-}" = /out/ax_log.jsonl ] && ok "AX_LOG=/out/ax_log.jsonl" || bad "AX_LOG is '${AX_LOG:-}'"
mounts=$(awk '$4 != "/" && $5 !~ "^/(proc|sys|dev|etc/(hosts|hostname|resolv.conf))" && $9 !~ "^(proc|sysfs|tmpfs|devpts|mqueue|cgroup2?|overlay)$" {print $5}' /proc/self/mountinfo | sort -u | tr '\n' ' ')
[ "$mounts" = "/out " ] && ok "only /out is mounted" || bad "unexpected mounts: $mounts"

exit $fail
