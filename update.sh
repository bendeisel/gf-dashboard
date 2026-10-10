#!/usr/bin/env bash
# Pull the latest dashboard and redeploy. Safe to run repeatedly (and from cron).
# Usage: ./update.sh            (pull + rebuild if there are changes)
#        ./update.sh --force    (rebuild even with no new commits)
set -euo pipefail
cd "$(dirname "$0")"

# Keep the dashboard's Claude login fresh from the server's own (actively-used) login,
# so panes never fall back to "Please run /login". Runs every tick, even on no-op pulls.
# SRC_CLAUDE_CREDS defaults to the root login; override in the environment if needed.
SRC_CLAUDE_CREDS="${SRC_CLAUDE_CREDS:-/root/.claude/.credentials.json}"
if [ -f "$SRC_CLAUDE_CREDS" ] && [ -d claude-gf ]; then
  SRC="$SRC_CLAUDE_CREDS" python3 - <<'PY' 2>/dev/null && { chown 1001:1001 claude-gf/.credentials.json 2>/dev/null || true; chmod 600 claude-gf/.credentials.json 2>/dev/null || true; } || true
import json, os
src = os.environ["SRC"]; dst = "claude-gf/.credentials.json"
root = json.load(open(src))
gf = json.load(open(dst)) if os.path.exists(dst) else {}
if "claudeAiOauth" in root:
    gf["claudeAiOauth"] = root["claudeAiOauth"]   # fresh account token; keeps mcpOAuth intact
    json.dump(gf, open(dst, "w"))
PY
fi

branch="$(git rev-parse --abbrev-ref HEAD)"
before="$(git rev-parse HEAD)"
git fetch --quiet origin "$branch"
after="$(git rev-parse "origin/$branch")"

if [ "$before" = "$after" ] && [ "${1:-}" != "--force" ]; then
  echo "[update] already up to date ($before)"; exit 0
fi

echo "[update] $before -> $after"
git merge --ff-only "origin/$branch"

echo "[update] rebuilding container"
# the container runs as UID 1001 (user gf); bind-mounted writable dirs must be
# owned by it or uploads / the Claude login / GHL profiles fail to read-write.
if [ "$(id -u)" = "0" ]; then
  mkdir -p claude-gf ghl-profiles workspace uploads
  # ghl-cli is tracked repo content but the container (UID 1001) must write its .venv there
  chown -R 1001:1001 claude-gf ghl-profiles workspace uploads ghl-cli 2>/dev/null || true
fi
docker compose up -d --build

# health check: wait up to 60s for the login page
echo -n "[update] waiting for health "
for i in $(seq 1 30); do
  code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3100/login || true)"
  if [ "$code" = "200" ]; then echo "ok (HTTP 200)"; exit 0; fi
  echo -n "."; sleep 2
done
echo
echo "[update] WARNING: dashboard did not return 200 on /login — check: docker compose logs --tail=50" >&2
exit 1
