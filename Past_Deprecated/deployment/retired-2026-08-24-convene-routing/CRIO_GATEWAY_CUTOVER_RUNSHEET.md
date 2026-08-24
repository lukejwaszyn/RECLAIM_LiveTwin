# MacBook scenario host cutover runsheet

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

**Date:** 2026-08-23
**Target:** this MacBook
**Scope:** gateway-side handover only; no cRIO edit, deployment, or re-addressing

Stop at any failed check. This cutover does not authorize an unreviewed cRIO VI
or convert diagnostic payloads into telemetry.

## 0. Required values

Record `APPROVED_SHA`, `MACBOOK_OT_INTERFACE`, `MACBOOK_OT_IP`,
`CRIO_SOURCE_IP`, and `CLOUD_INGEST_URL` before starting. The bench values
`192.168.12.33` is the observed active-en0 bench address and is not the default
OT bind; `192.168.12.114` was an emulated peer. Assign/confirm production values.

## 1. Read-only prechecks

```bash
git status --short
git rev-parse HEAD
networksetup -listallhardwareports
route -n get default
ifconfig
lsof -nP -iTCP:9070 -sTCP:LISTEN
lsof -nP -iTCP:9080 -sTCP:LISTEN
```

Pass requires the approved SHA, intended OT interface/address, no unexpected
port owner, and no default route on the isolated OT interface. Preserve the
existing queue, configuration, logs, and captures.

## 2. Configuration check

Production configuration is
`/Users/lukewaszyn/Library/Application Support/RECLAIM/edge-gateway/config.yaml`.
Required values:

- `listen_host: <WINDOWS10_GATEWAY_IP>`, `listen_port: 9070`;
- `status_port: 9080`;
- `conn_idle_timeout_s: 15.0`, `max_line_bytes: 8192`;
- `strict_fields: false` until the signed source manifest exists;
- absolute persistent `buffer_path`;
- `mode: live`, `transport: https`, current `/ingest` URL and ingest token;
- `verify_tls: true`; configuration and credential mode `0600`.

Do not print the token. Do not provide the VM read token to the MacBook.

## 3. Software preflight

```bash
PYTHONPATH=pi_gateway .venv-macbook/bin/python -m pytest pi_gateway -q
PYTHONPATH=cloud_engine .venv-macbook/bin/python -m pytest cloud_engine -q
PYTHONPATH=crio_source_record .venv-macbook/bin/python -m pytest crio_source_record -q
PYTHONPATH="pi_gateway:cloud_engine:$PWD" \
  .venv-macbook/bin/python -m crio_source_record.bench_replay
```

All tests and bench replay must pass at the selected SHA.

## 4. Foreground handover

With the cRIO producer and every synthetic sender stopped:

```bash
export RECLAIM_EDGE_CONFIG="$HOME/Library/Application Support/RECLAIM/edge-gateway/config.yaml"
PYTHONPATH=pi_gateway .venv-macbook/bin/python -m reclaim_edge.main
```

In a second terminal:

```bash
lsof -nP -iTCP:9070 -sTCP:LISTEN
lsof -nP -iTCP:9080 -sTCP:LISTEN
curl --fail http://127.0.0.1:9080/health
curl --fail http://127.0.0.1:9080/latest
```

Pass requires `9070` on `<WINDOWS10_GATEWAY_IP>` and `9080` on `127.0.0.1` only.

## 5. Commissioning stream

Before the real source, send one bounded, explicitly synthetic stream. Pass
requires receive and delivery counters to advance, the queue to drain, no new
dead letters, correlated engine run/source/sequence, advancing raw gateway and `sim_`,
and DATA NOT LIVE after source expiry.

If the cloud final-rejects frames as `timestamp_stale`, stop and complete
`CLOUD_ENGINE_LIVE_SCENARIO_HANDOFF_PROMPT.md`. Do not widen freshness limits in
place of repairing run adoption or persistence.

## 6. Real-source cutover

Stop every synthetic sender and confirm no established synthetic connection.
Start exactly one controls-approved cRIO producer. Capture the first raw frame,
compare it with same-time LabVIEW/USB evidence, and run at least five minutes as
an engineering shadow. No command or actuation path is authorized.

## 7. launchd and rollback

Install the LaunchAgent only after foreground shutdown/restart and queue recovery
pass. Follow `../pi_gateway/macos/README.md`. Reboot once before the competition
and confirm the service after login.

Rollback by stopping the LaunchAgent or foreground gateway and stopping the cRIO
telemetry addition. Preserve queue, logs, captures, credentials, and evidence.
