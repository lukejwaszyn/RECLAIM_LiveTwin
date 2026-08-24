# MacBook three-path HTTPS acceptance

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

**Captured:** 2026-08-24
**Historical component under test:** temporary MacBook gateway configuration; not deployed
**Result:** local production-component rehearsal passed; real VM/Convene cutover pending

## Proven topology

The acceptance runner exercised the production gateway, production
`DualPushEngine`, and production state bridge. Two short-lived Cloudflare Quick
Tunnels supplied real public HTTPS/TLS transport. A narrow authenticated sink
emulated only Convene's documented direct `machine/publish` and agent-heartbeat
write surfaces; it did not claim to be the production Convene tenant.

```text
isolated synthetic source -> temporary gateway component
  |-> HTTPS/Cloudflare -> exact-name gateway variables acceptance machine
  `-> HTTPS/Cloudflare -> production engine -> state bridge
                                      -> sim_* heartbeat acceptance machine
```

Evidence: `captures/three-path-cloudflare-acceptance.json`.

## Scenario result

| Profile | Frames | Final correlated sequence | Result |
|---|---:|---:|---|
| nominal Earth lab | 401 | 401 | pass |
| power-outage Earth lab | 901 | 1302 | pass |
| nominal lunar surface | 401 | 1703 | pass |

Across the combined 1,703-frame stream:

- gateway received and cloud-delivered counts matched;
- the durable queue returned to zero;
- drops and dead letters remained zero;
- `run_id/source_id/cycle_id/seq/source_op_state` matched `sim_*`;
- the raw four-temperature mean in degrees Celsius matched the engine's computed
  Kelvin metric after normalization;
- the gateway publisher added no blanket prefix and preserved canonical source
  names, while the engine payload remained `sim_`-prefixed;
- gateway Convene publication and the VM heartbeat agent both recorded zero
  failures; and
- after source stop, the bridge published `sim_data_live=false` with
  `STATE_STALE`.

The runner now requires ten consecutive successful health responses from each
Quick Tunnel before releasing telemetry. The accepted rerun recorded zero HTTP
publication failures across all three scenarios. A named Cloudflare Tunnel is
still preferred for a stable production hostname.

The run also found and repaired a shutdown race that mislabeled an orderly
publisher exit as a crash. The final harness shutdown and a subsequent installed
LaunchAgent restart both exited cleanly.

## What this does not prove

- The real Windows Server 2025 VM was not reached from this session.
- The production Convene tenant and its visible bindings were not mutated or observed.
- The real Convene tenant was not used by this isolated three-path harness. The
  MacBook is separately paired to production Convene as machine
  `iODneus5UalYhT15Y8Gm`, and a bounded 20-frame raw-variable publish completed
  with zero Convene failures.
- Tailscale is installed but logged out; joining the private network requires
  explicit authorization for the intended account/network.
- Quick-tunnel hostnames are ephemeral and must not be copied into production config.

Production acceptance still requires the real VM `/ingest`, engine `/state`, VM
state bridge/agent, visible exact-name gateway variables and `sim_*` values in Convene, stale expiry,
and the same three profiles. Use
`pi_gateway/macos/configure_production_interfaces.py` only after receiving the
approved endpoint and separate MacBook credential privately.
