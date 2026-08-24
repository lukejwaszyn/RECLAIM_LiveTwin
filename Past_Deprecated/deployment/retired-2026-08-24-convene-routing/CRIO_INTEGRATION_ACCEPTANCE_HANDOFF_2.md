# RECLAIM cRIO telemetry — Windows 10 gateway cutover and acceptance handoff

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

**Date:** 2026-08-23
**Gateway:** this MacBook
**Competition:** 2026-08-24
**Supersedes:** gateway-platform and gateway-command details in the earlier acceptance handoff

## Boundary

This handoff authorizes MacBook-side staging, configuration, synthetic testing,
and read-only inspection. It does not authorize a cRIO edit, VI execution,
redeployment, network re-addressing, or unsupervised real run. Those require the
named controls and onsite owners.

Bytes arriving are not authoritative telemetry. Until source/build identity,
signed maps, timing, quality, safety, rollback, and correlated acceptance pass,
the stream remains an engineering shadow.

## Endpoints

- cRIO: `<CRIO_SOURCE_IP>`, exactly one telemetry producer when approved.
- Windows 10 live gateway: `<WINDOWS10_GATEWAY_IP>:9070`; status is local-only.
- VM: Windows Server 2025, production engine on loopback `8078` behind Cloudflare.
- Convene: MacBook exact-name gateway variables and VM-only `sim_*` visualization.

Bench observations were `192.168.12.33` on active `en0` and emulated peer
`192.168.12.114`; neither is accepted as the dedicated production OT assignment.

## Proven and open

| Gate | Evidence | Status |
|---|---|---|
| MacBook TCP proof | Raw request/response against emulated endpoint | done, diagnostic only |
| Offline parser/framer | Tests and bench replay existed on the integration branch | rerun required at selected SHA |
| MacBook runtime | Protected config, queue, foreground lifecycle, `launchd` | open |
| VM live ingest | Run adoption and no `timestamp_stale` dead letters | open; repair handoff issued |
| Source identity/maps | Deployed build, coherent snapshot, signed metadata/channel maps | open |
| Producer safety | Lower priority, bounded latest-wins, no command/output path | open |
| Live correlation | First frame, five-minute shadow, restart/fault and stale expiry | open |

## Execution order

1. Read `DEPLOYMENT_TOPOLOGY.md`, `GATEWAY_GO_LIVE.md`,
   `MACBOOK_GATEWAY_AND_CRIO_VI_HANDOFF.md`, and `../pi_gateway/macos/README.md`.
2. Reserve/confirm the Windows 10 gateway OT address, interface, route isolation, real cRIO
   source IP, and packet-filter policy.
3. Build `.venv-macbook`, stage protected config/state, and rerun all tests plus
   bench replay at the selected SHA.
4. Execute `CRIO_GATEWAY_CUTOVER_RUNSHEET.md` in the foreground.
5. Repair and accept the cloud path using
   `CLOUD_ENGINE_LIVE_SCENARIO_HANDOFF_PROMPT.md`.
6. Run one bounded labeled synthetic stream through the real MacBook and
   production VM; correlate gateway, engine, bridge, raw gateway, `sim_`, and expiry.
7. Install and reboot-test the LaunchAgent.
8. Collect and countersign the cRIO source/build, map, coherence, RT-safety, and
   rollback evidence.
9. During an approved idle window, accept one real frame, sustain at least five
   minutes, and run disconnect/restart acceptance.

## Source contract

One complete UTF-8 JSON object plus one LF, maximum 8192 bytes, carrying
`source_id`, per-frame `ts`, stable physical `cycle_id`, authoritative
`source_op_state`, explicit `active_chamber`, and typed finite raw `vars`.
Incomplete bed banks must be entirely omitted rather than partially published.

## Stop conditions

Stop if an address is assumed rather than confirmed, an unknown process owns a
port, `9070` is exposed on WAN, `9080` is exposed beyond loopback, tests fail,
secrets appear in output, queue/dead letters grow, the engine does not adopt the
MacBook run, source metadata is fabricated, or any advisory result reaches
hardware control.

## Competition fallback

If real-source gates remain open, use only an explicitly labeled bounded
synthetic scenario through the MacBook and production VM. Do not claim physical
telemetry and do not reactivate the former Windows gateway.
