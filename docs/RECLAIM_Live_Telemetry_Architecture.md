# RECLAIM live and scenario telemetry architecture

**Effective:** 2026-08-24

## Convene-routed source paths

```text
REAL LIVE DATA
cRIO / LabVIEW -> Windows 10 desktop live gateway -> Convene live machine

SCENARIO DATA
synthetic generator or approved capture file
  -> MacBook 127.0.0.1:9070 (harness/replay)
  -> MacBook Convene machine

BOTH SOURCE PATHS
Convene internal route -> cloud stochastic engine -> Convene sim_*
```

The paths converge in Convene, not on the MacBook. The MacBook is not a live
client, has no direct cloud transport, and has no production ingest token. A
separate gateway-to-cloud HTTPS/cloudflared telemetry seam is not part of this
architecture.

## Naming

The MacBook preserves exact scenario/source channel names. It neither adds nor
strips a blanket `gw_` prefix; approved fields that already include `gw_` retain
it. Only the VM/cloud publisher may emit `sim_`.

## Freshness and provenance

MacBook records must identify a synthetic or file-replay source and use
`mode=harness` or `mode=replay`. They must never claim current physical data.
Live freshness and identity are owned by the Windows 10/production path.

Convene must rebuild the canonical envelope and nest raw channels under `vars`
before `POST /ingest`. The existing production engine and return bridge enforce
`mode=live`; scenario round trips need a deliberately isolated, honestly labeled
policy and are not yet proven by repository evidence.

The predictive engine remains advisory. No command, setpoint, or actuation path
is authorized by this architecture document.
