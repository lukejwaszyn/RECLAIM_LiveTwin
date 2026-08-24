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
| Live gateway | Windows 10 desktop | Receives the real cRIO/LabVIEW stream and publishes source variables to Convene |
| Scenario host | MacBook running macOS | Serves local synthetic/capture scenarios through one owner-private, one-frame Convene File Watch text file; loopback input only |
| Predictive-engine VM | Cloud-hosted Windows Server 2025 guest | Runs the stochastic dual engine and returns computed state to Convene |
| Convene | External service | Common source ingress, internal route to/from the engine, and `sim_*` visualization |

The repository directory name `pi_gateway` is retained for compatibility. Its
Windows tooling applies to the live gateway; its macOS tooling is scenario-only.

## Live data path

```text
cRIO / LabVIEW authoritative source
  -> Windows 10 desktop live gateway
  -> Convene live machine

MacBook local synthetic/file-replay scenario
  -> 127.0.0.1:9070 (harness/replay mode only)
  -> atomic one-frame LabVIEW-style text
  -> Convene File Watch heartbeat
  -> Convene scenario machine

Either Convene source machine
  -> Convene internal route
  -> Windows Server 2025 cloud stochastic engine
  -> computed state returned to Convene
  -> sim_ namespace and STEP visualization
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
  `launchd`, owner-private File Watch text, and Convene heartbeat bindings.
- VM operator: Windows service, release, ACLs, engine authentication, durable
  ingest identity, result return, and single-writer `sim_*` enforcement.
- Controls operator: cRIO build, telemetry producer, channel/quality maps,
  sequencing, interlocks, actuation, and rollback.
- Convene is telemetry routing and visualization only. `/command` remains
  advisory and is not connected to any actuator path.

## Current acceptance state

The MacBook scenario lifecycle and capture replay are proven to the Convene
source machine. Cloud code accepts unavailable LabVIEW sensor values without
fabricating them. The actual Convene internal round trip, including scenario-mode
handling, still requires correlated acceptance evidence. Live cRIO and Windows
10 acceptance remain separate.
