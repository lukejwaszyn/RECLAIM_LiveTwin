# Windows 10 cRIO live-gateway deployment session prompt

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

> Paste this file into a Codex session running on the authoritative MacBook
> gateway from `/Users/lukewaszyn/RECLAIM_LiveTwin`. Do not paste secrets.

You are deploying the RECLAIM cRIO-to-gateway telemetry seam on macOS. Use
terminal commands only. Read completely before changing the machine:

- `deployment/DEPLOYMENT_TOPOLOGY.md`
- `deployment/MACBOOK_GATEWAY_AND_CRIO_VI_HANDOFF.md`
- `deployment/CRIO_GATEWAY_CUTOVER_RUNSHEET.md`
- `deployment/GATEWAY_GO_LIVE.md`
- `pi_gateway/macos/README.md`
- `deployment/CLOUD_ENGINE_LIVE_SCENARIO_HANDOFF_PROMPT.md`

## Objective

Deploy exactly one MacBook scenario host process that listens on
`<WINDOWS10_GATEWAY_IP>:9070`, keeps status on `127.0.0.1:9080`, durably sends accepted
frames to the production VM `/ingest`, and independently publishes exact-name gateway variables.

The VM remains Windows Server 2025 and is the sole `sim_*` writer. No command,
setpoint, shared-variable write, cRIO deploy, or actuation path is authorized.

## Guardrails

- Preserve every untracked capture, probe, config, queue, log, and credential.
- Record `git status --short` and the exact SHA before editing or deploying.
- Do not assume the bench addresses are production values. Confirm/reserve the
  Windows 10 gateway address and confirm the real cRIO source address.
- Do not bind `9070` to `0.0.0.0`.
- Do not expose `9080` beyond loopback.
- Do not print tokens or place them in command arguments.
- Run in foreground with console transport before enabling HTTPS or `launchd`.
- Stop if any software test, bind check, queue check, cloud correlation, or stale
  expiry gate fails.

## Required workflow

1. Perform the read-only host, network, route, port-owner, and repository audit.
2. Create `.venv-macbook`, install `pi_gateway/requirements.txt`, and run all
   gateway/source/engine tests plus bench replay.
3. Stage the protected configuration under
   `~/Library/Application Support/RECLAIM/edge-gateway/config.yaml` with mode
   `0600`; keep queue/logs outside Git.
4. Start the gateway in the foreground with `transport: console`. Verify
   listener/status bindings, Ctrl+C shutdown, restart, and queue persistence.
5. Obtain the current VM `/ingest` URL and ingest token privately. Enable
   `transport: https`, `mode: live`, and `verify_tls: true`.
6. Coordinate a bounded synthetic stream. Require gateway receive/delivery,
   drained queue, no new dead letters, engine run/source/sequence adoption,
   healthy state bridge, advancing raw gateway and `sim_`, and DATA NOT LIVE on stop.
7. If frames become `timestamp_stale`, stop and repair the VM using
   `CLOUD_ENGINE_LIVE_SCENARIO_HANDOFF_PROMPT.md`; do not widen freshness.
8. Install the LaunchAgent only after foreground acceptance. Reboot, log in, and
   verify it returns.
9. Connect exactly one controls-approved cRIO producer, retain the first frame,
   correlate it with LabVIEW/USB, and run the required engineering-shadow soak.

## Return

Report the selected SHA; macOS/Python versions; OT interface, gateway address,
and source address; files changed; config/credential permission state without
secret values; test results; listener bindings; queue/counter deltas; engine and
Convene correlation; stale-expiry evidence; `launchd` status; unresolved gates;
and exact rollback commands.
