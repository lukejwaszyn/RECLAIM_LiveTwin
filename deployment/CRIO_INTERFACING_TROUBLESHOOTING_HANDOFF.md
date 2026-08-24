# cRIO-to-Windows-10-live-gateway interfacing troubleshooting

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

Use this when frames are not arriving, validating, or reaching the VM/Convene.
The path is advisory-only; troubleshooting does not authorize cRIO changes or an
actuation path.

## 1. First checks

```bash
networksetup -listallhardwareports
ifconfig
route -n get default
lsof -nP -iTCP:9070 -sTCP:LISTEN
lsof -nP -iTCP:9080 -sTCP:LISTEN
curl --fail http://127.0.0.1:9080/health
curl --fail http://127.0.0.1:9080/latest
```

Expected: one gateway listener on `<WINDOWS10_GATEWAY_IP>:9070`, status only on
`127.0.0.1:9080`, OT interface up with no default route, and WAN/Wi-Fi holding
the default Internet route.

## 2. Fault ladder

### No listener

- Confirm the populated config path in `RECLAIM_EDGE_CONFIG`.
- Confirm `listen_host` is assigned to the Windows 10 gateway and is not the cRIO address.
- Check the foreground log or `launchctl print gui/$(id -u)/com.reclaim.edge-gateway`.
- Identify any competing owner with `lsof`; do not kill an unknown process until
  its role is understood.

### Listener exists, no connection

- Confirm the real cRIO source IP and physical link.
- Confirm the producer targets `<WINDOWS10_GATEWAY_IP>:9070`.
- Confirm the macOS packet-filter rule admits only that source/interface.
- The MacBook's 2026-08-23 `GET` probe was the opposite connection direction and
  does not prove a cRIO producer will connect to the gateway listener.

### Connected, `received` does not advance

- Require one JSON object followed by LF. Missing LF looks like silence.
- Check the 8192-byte maximum and UTF-8/finite-number requirements.
- Wait beyond the configured 15-second idle timeout to distinguish a half-open peer.
- Capture raw bytes without inserting a transformation into the live path.

### `received` advances, validation fails

This is a source-contract problem. Compare `/latest` and retained raw evidence
with `CRIO_TELEMETRY_SOCKET_SETUP.md`. Do not invent missing metadata or map
unverified channel names in the gateway.

### Gateway accepts, cloud rejects

- Inspect final disposition and new dead-letter records without exposing tokens.
- `telemetry_invalid` with a partial PL bed bank means the producer must send the
  complete bank or omit it entirely.
- Repeated delayed `timestamp_stale` after retries points to the VM run-adoption/
  persistence problem. Follow `CLOUD_ENGINE_LIVE_SCENARIO_HANDOFF_PROMPT.md`;
  do not increase freshness to mask it.

### Cloud accepts, Convene does not advance

- Check the MacBook `/health` `convene` counters for exact-name gateway variables.
- Check engine run/source/sequence and authenticated `/state` for `sim_*`.
- Verify state-bridge health, lease renewal, and the VM Convene binding.
- Machine presence alone is not telemetry. The known Firestore heartbeat index
  issue is separate from direct `/machine/publish`.

## 3. Local reproduction

With the real cRIO disconnected, send only an explicitly labeled bounded
synthetic stream using the repository scenario/fixture tooling. It must target
the same MacBook listener and production VM path, stop automatically, and refuse
to run when a real source is connected.

Pass requires received/delivered counters to advance, queue drain, no new dead
letters, matching engine identity, advancing raw gateway and `sim_`, and DATA NOT LIVE
after stop.

## 4. MacBook-specific non-bugs

- TCP may split one application response into multiple chunks; chunk boundaries
  are not framing.
- A healthy `/health` with `received: 0` proves only that the gateway is alive.
- `convene.machine_id` may remain null until the first attempted audit delivery.
- A LaunchAgent is login-scoped; after reboot it starts only after the gateway
  user logs in.
- The old Windows task/PowerShell procedures under `pi_gateway/windows/` are
  historical and must not be used on this gateway.

## 5. Preserve and stop

Do not delete or overwrite the config, queue, logs, captures, credentials, or
untracked probe tools. Stop if troubleshooting would require a cRIO edit,
re-addressing, weakened TLS/auth/freshness, exposed `9080`, fabricated fields, or
hardware command authority.
