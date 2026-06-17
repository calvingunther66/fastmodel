#!/usr/bin/env bash
# Run the web server and (if a tunnel token is provided) the cloudflared daemon
# together in one container. If either process exits, shut the other down so the
# container stops and the restart policy can recover it.
set -euo pipefail

pids=()

cleanup() {
  for pid in "${pids[@]:-}"; do
    kill -TERM "$pid" 2>/dev/null || true
  done
}
trap cleanup TERM INT

# 1) Web server (uvicorn via `python -m server`)
python -m server &
pids+=("$!")
echo "[entrypoint] web server started (pid ${pids[-1]}) on ${HOST:-0.0.0.0}:${PORT:-8000}"

# 2) Cloudflare tunnel — only if a token is configured
if [[ -n "${TUNNEL_TOKEN:-}" ]]; then
  cloudflared tunnel --no-autoupdate run --token "$TUNNEL_TOKEN" &
  pids+=("$!")
  echo "[entrypoint] cloudflared started (pid ${pids[-1]})"
else
  echo "[entrypoint] TUNNEL_TOKEN not set — running web server only (no tunnel)."
fi

# Exit as soon as any child exits, then clean up the rest.
wait -n
status=$?
echo "[entrypoint] a process exited (status ${status}); shutting down."
cleanup
wait || true
exit "$status"
