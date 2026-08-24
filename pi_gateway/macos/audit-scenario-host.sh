#!/bin/sh
set -eu

health_url="${RECLAIM_SCENARIO_HEALTH_URL:-http://127.0.0.1:9080/health}"
file_watch_path="${RECLAIM_SCENARIO_FILE_WATCH_PATH:-$HOME/Library/Application Support/RECLAIM/scenarios/convene_file_watch.txt}"

health="$(curl -fsS "$health_url")"
printf '%s\n' "$health" | python3 -c '
import json, sys
h = json.load(sys.stdin)
errors = []
if h.get("src") != "reclaim-macbook-scenario-01": errors.append("unexpected source identity")
if h.get("mode") not in {"harness", "replay"}: errors.append("mode is not scenario-labeled")
if h.get("transport") != "console": errors.append("direct cloud transport is enabled")
if h.get("convene", {}).get("enabled"): errors.append("direct Convene API publisher is enabled")
fw = h.get("file_watch", {})
if not fw.get("enabled"): errors.append("File Watch writer is disabled")
if fw.get("failed", 0): errors.append("File Watch writer has failures")
if errors:
    raise SystemExit("; ".join(errors))
print(json.dumps(h, indent=2))
'

test -f "$file_watch_path"
permissions="$(stat -f '%Lp' "$file_watch_path")"
test "$permissions" = "600"

listeners="$(lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null || true)"
for required_port in 9070 9080; do
    printf '%s\n' "$listeners" | grep -E "127\\.0\\.0\\.1:${required_port}[[:space:]]" >/dev/null
done
if printf '%s\n' "$listeners" | grep -E '(^|[[:space:]])(\*|0\.0\.0\.0|\[::\]):(9070|9080)[[:space:]]' >/dev/null; then
    echo 'Scenario listener is exposed beyond loopback.' >&2
    exit 1
fi
if printf '%s\n' "$listeners" | grep -E ':(8078|8177|8178|8179|8180|8181)[[:space:]]' >/dev/null; then
    echo 'Deprecated local engine/scenario listener is active.' >&2
    exit 1
fi

field_count="$(awk -F ', ' 'NR==1 { print NF }' "$file_watch_path")"
test "$field_count" = "35"
line_count="$(wc -l < "$file_watch_path" | tr -d ' ')"
test "$line_count" = "1"

echo "MacBook scenario host audit passed: one loopback service, one 35-field live-shaped text frame, no competing engine ports."
