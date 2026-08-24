#!/bin/bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  start-rehearsal-scenario.sh start <profile> <PL|MT>
  start-rehearsal-scenario.sh stop
  start-rehearsal-scenario.sh status
  start-rehearsal-scenario.sh run <profile> <PL|MT>

Profiles: nominal | power-outage | lunar | loss-of-data
EOF
  exit 2
}

[[ $# -ge 1 ]] || usage

action=$1
script_dir=$(cd "$(dirname "$0")" && pwd)
repository_root=$(cd "$script_dir/../.." && pwd)
python_exe="$repository_root/.venv-macbook/bin/python"
gateway_host=${RECLAIM_GATEWAY_HOST:-127.0.0.1}
gateway_port=${RECLAIM_GATEWAY_PORT:-9070}
status_base=${RECLAIM_STATUS_BASE:-http://127.0.0.1:9080}
speed=${RECLAIM_SCENARIO_SPEED:-1}
max_frames=${RECLAIM_SCENARIO_MAX_FRAMES:-0}
cycles=${RECLAIM_SCENARIO_CYCLES:-0}
state_dir=${RECLAIM_SCENARIO_STATE_DIR:-"$HOME/Library/Application Support/RECLAIM/scenarios"}
pid_file="$state_dir/scenario.pid"
log_file="$state_dir/scenario.log"

is_running() {
  [[ -f "$pid_file" ]] || return 1
  local pid command
  pid=$(<"$pid_file")
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  command=$(ps -p "$pid" -o command= 2>/dev/null || true)
  [[ "$command" == *"tools/synthetic_crio.py"* ]]
}

stop_scenario() {
  if [[ ! -f "$pid_file" ]]; then
    echo "No MacBook scenario is running."
    return 0
  fi
  local pid command
  pid=$(<"$pid_file")
  if [[ ! "$pid" =~ ^[0-9]+$ ]] || ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$pid_file"
    echo "Removed a stale scenario PID file; no scenario was running."
    return 0
  fi
  command=$(ps -p "$pid" -o command= 2>/dev/null || true)
  if [[ "$command" != *"tools/synthetic_crio.py"* ]]; then
    echo "Refusing to stop PID $pid because it is not a RECLAIM scenario process." >&2
    return 1
  fi
  kill -TERM "$pid"
  for _ in {1..100}; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "Scenario PID $pid did not stop within 10 seconds." >&2
    return 1
  fi
  rm -f "$pid_file"
  echo "Stopped MacBook scenario PID $pid."
}

if [[ "$action" == "stop" ]]; then
  [[ $# -eq 1 ]] || usage
  stop_scenario
  exit 0
fi

if [[ "$action" == "status" ]]; then
  [[ $# -eq 1 ]] || usage
  if is_running; then
    echo "MacBook scenario is running (PID $(<"$pid_file"))."
    curl --fail --silent --max-time 5 "$status_base/latest" || true
    echo
    exit 0
  fi
  echo "No MacBook scenario is running."
  exit 1
fi

[[ "$action" == "start" || "$action" == "run" ]] || usage
[[ $# -eq 3 ]] || usage
profile=$2
active_chamber=$3
[[ "$active_chamber" == "PL" || "$active_chamber" == "MT" ]] || usage

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

if is_running; then
  echo "A MacBook scenario is already running (PID $(<"$pid_file")). Stop it first." >&2
  exit 1
fi
if /usr/sbin/lsof -nP -iTCP:"$gateway_port" -sTCP:ESTABLISHED 2>/dev/null | tail -n +2 | grep -q .; then
  echo "Refusing scenario start: a source is already connected to TCP $gateway_port." >&2
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
  --active-chamber "$active_chamber"
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

echo "RECLAIM MacBook scenario: $profile, active chamber $active_chamber"
echo "Path: synthetic source -> $gateway_host:$gateway_port -> Convene scenario publisher"

if [[ "$action" == "run" ]]; then
  echo "Foreground run; stop with Ctrl+C."
  exec "$python_exe" "${args[@]}"
fi

mkdir -p "$state_dir"
nohup "$python_exe" "${args[@]}" >>"$log_file" 2>&1 &
scenario_pid=$!
printf '%s\n' "$scenario_pid" >"$pid_file"
sleep 0.5
if ! is_running; then
  rm -f "$pid_file"
  echo "Scenario failed to stay running. Recent log output:" >&2
  tail -n 20 "$log_file" >&2 || true
  exit 1
fi
echo "Started MacBook scenario PID $scenario_pid."
echo "Log: $log_file"
echo "Stop: $0 stop"
