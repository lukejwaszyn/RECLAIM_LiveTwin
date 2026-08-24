# RECLAIM live and scenario telemetry architecture

**Effective:** 2026-08-24

## Separate source paths

```text
REAL LIVE DATA
cRIO / LabVIEW -> Windows 10 desktop live gateway -> production live-data path

SCENARIO DATA
synthetic generator or approved capture file
  -> MacBook 127.0.0.1:9070 (harness/replay)
  -> MacBook Convene machine
  -> separately owned Convene-to-VM scenario pipe

COMPUTED DATA
predictive-engine VM -> state bridge -> Convene sim_*
```

The paths must not be merged on the MacBook. The MacBook is not a live client,
has no direct cloud transport, and has no production ingest token.

## Naming

The MacBook preserves exact scenario/source channel names. It neither adds nor
strips a blanket `gw_` prefix; approved fields that already include `gw_` retain
it. Only the VM/cloud publisher may emit `sim_`.

## Freshness and provenance

MacBook records must identify a synthetic or file-replay source and use
`mode=harness` or `mode=replay`. They must never claim current physical data.
Live freshness and identity are owned by the Windows 10/production path.

The predictive engine remains advisory. No scenario, live, command, return,
setpoint, or actuation path is authorized by this architecture document.
