#!/bin/bash
set -euo pipefail

usage() {
  echo "Usage: $0 nominal|power-outage|lunar|loss-of-data" >&2
  exit 2
}

[[ $# -eq 1 ]] || usage

profile=$1
script_dir=$(cd "$(dirname "$0")" && pwd)
repository_root=$(cd "$script_dir/../.." && pwd)
python_exe="$repository_root/.venv-macbook/bin/python"
gateway_host=${RECLAIM_GATEWAY_HOST:-127.0.0.1}
gateway_port=${RECLAIM_GATEWAY_PORT:-9070}
status_base=${RECLAIM_STATUS_BASE:-http://127.0.0.1:9080}
speed=${RECLAIM_SCENARIO_SPEED:-1}
max_frames=${RECLAIM_SCENARIO_MAX_FRAMES:-0}
cycles=${RECLAIM_SCENARIO_CYCLES:-0}

[[ -x "$python_exe" ]] || {
  echo "Missing MacBook runtime: $python_exe" >&2
  exit 1
}

health=$(curl --fail --silent --max-time 5 "$status_base/health") || {
  echo "Gateway health unavailable at $status_base/health" >&2
  exit 1
}

printf '%s' "$health" | "$python_exe" -c '
import json, sys
h = json.load(sys.stdin)
mode = h.get("mode")
if mode not in {"harness", "replay"}:
    raise SystemExit(f"MacBook must be scenario-only (harness/replay), got {mode!r}")
'

if /usr/sbin/lsof -nP -iTCP:"$gateway_port" -sTCP:ESTABLISHED 2>/dev/null | tail -n +2 | grep -q .; then
  echo "Refusing synthetic telemetry: a device is already connected to TCP $gateway_port." >&2
  exit 1
fi

scenario=nominal
environment=earth_lab
case "$profile" in
  nominal)
    ;;
  power-outage)
    scenario=power_outage
    ;;
  lunar)
    environment=lunar_surface
    ;;
  loss-of-data)
    if [[ "$cycles" -eq 0 ]]; then
      cycles=1
    fi
    ;;
  *)
    usage
    ;;
esac

args=(
  "$repository_root/tools/synthetic_crio.py"
  --scenario "$scenario"
  --env "$environment"
  --host "$gateway_host"
  --port "$gateway_port"
  --speed "$speed"
)

if [[ "$cycles" -gt 0 ]]; then
  args+=(--cycles "$cycles")
fi
if [[ "$max_frames" -gt 0 ]]; then
  args+=(--max-frames "$max_frames")
fi

echo "RECLAIM MacBook scenario host: $profile"
echo "Path: synthetic source -> $gateway_host:$gateway_port -> Convene scenario publisher"
echo "Source is synthetic and advisory-only. Stop with Ctrl+C."

exec "$python_exe" "${args[@]}"
