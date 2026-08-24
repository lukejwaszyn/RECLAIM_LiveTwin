# RECLAIM live deployment topology

**Status:** authoritative platform record
**Effective:** 2026-08-24
**Competition:** LunaRecycle demonstration, 2026-08-24

## Platform decision

The Windows 10 desktop remains the sole live-data client/gateway. The MacBook is
scenario-only and cannot receive cRIO live data or publish directly to the cloud
engine. The predictive-engine VM remains Windows Server 2025.

| Component | Platform | Responsibility |
|---|---|---|
| RECLAIM hardware | cRIO + LabVIEW | Authoritative telemetry and process sequencing |
| Live gateway | Windows 10 desktop | Receives the real cRIO/LabVIEW stream and owns the production live-data path |
| Scenario host | MacBook running macOS | Serves local synthetic/capture scenarios to its Convene machine; loopback input only |
| Predictive-engine VM | Cloud-hosted Windows Server 2025 guest | Runs the production dual engine, Cloudflare route, state bridge, and VM Convene agent |
| Convene | External service | Receives MacBook scenario variables and VM `sim_` predictive variables |

The repository directory name `pi_gateway` is retained for compatibility. Its
Windows tooling applies to the live gateway; its macOS tooling is scenario-only.

## Live data path

```text
cRIO / LabVIEW authoritative source
  -> Windows 10 desktop live gateway
  -> production live-data path prepared separately
  -> Windows Server 2025 VM
  -> authenticated GET /state
Windows state bridge
  -> C:\ConveneAgent\sim_vars.json
VM Convene agent
  -> Convene sim_ namespace

MacBook local synthetic/file-replay scenario
  -> 127.0.0.1:9070 (harness/replay mode only)
  -> nonblocking /api/machine/publish
  -> Convene scenario machine
  -> separately owned Convene-to-VM scenario pipe
```

Port `9080` is loopback-only and must never be exposed through Wi-Fi, Internet
Sharing, Tailscale, Cloudflare, or a firewall opening.

## Network record

- MacBook scenario ingress is fixed to `127.0.0.1:9070`; no MacBook OT address is
  required or authorized.
- Windows 10 live-gateway addressing and cRIO interface details remain owned by
  the live-data workstream.

## Ownership and authority

- Live-gateway operator: Windows 10 cRIO interface and production forwarding.
- Scenario operator: MacBook loopback runtime, scenario files/generators,
  `launchd`, and Convene scenario publisher.
- VM operator: Windows service, release, ACLs, secrets, port `8078`, Cloudflare,
  durable ingest identity, state bridge, and `sim_` publisher.
- Controls operator: cRIO build, telemetry producer, channel/quality maps,
  sequencing, interlocks, actuation, and rollback.
- Convene is visualization only. `/command` remains advisory and is not connected
  to any actuator path.

## Current acceptance state

The MacBook scenario lifecycle and capture replay are proven. Live cRIO and
Windows 10 acceptance remain separate. The MacBook is not part of that live-client
acceptance gate.
