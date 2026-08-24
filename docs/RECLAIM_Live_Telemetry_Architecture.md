# RECLAIM live and scenario telemetry architecture

**Effective:** 2026-08-24

## Convene-routed source paths

```text
REAL LIVE DATA
cRIO / LabVIEW -> Windows 10 desktop live gateway -> Convene live machine

SCENARIO DATA
synthetic generator or approved capture file
  -> MacBook 127.0.0.1:9070 (harness/replay)
  -> atomic one-frame LabVIEW-style text
  -> Convene File Watch heartbeat
  -> MacBook Convene machine

BOTH SOURCE PATHS
Convene internal route -> cloud stochastic engine -> Convene sim_*
```

The paths converge in Convene, not on the MacBook. The MacBook is not a live
client, has no direct cloud transport, and has no production ingest token. A
separate gateway-to-cloud HTTPS/cloudflared telemetry seam is not part of this
architecture.

The MacBook also makes no direct Convene API call for scenario telemetry. Its
only egress artifact is the owner-private, one-frame File Watch text; Convene reads it.

## Naming

The MacBook preserves exact scenario/source channel names. It neither adds nor
strips a blanket `gw_` prefix; approved fields that already include `gw_` retain
it. Only the VM/cloud publisher may emit `sim_`.

## Freshness and provenance

The MacBook watched record deliberately matches the live 35-field text shape and
contains no provenance envelope. Convene sends either origin to the same
`POST /ingest`. The engine records `mode=telemetry` and does not classify origin.

Convene sends the Windows machine, MacBook scenario machine, or approved replay
to the same `POST /ingest` interface.
The current physical live record contains authoritative `active_chamber` plus the
exact 34 LabVIEW fields; the engine generates receipt-owned
run/source/sequence/time/cycle metadata rather than
pretending LabVIEW supplied it. Scenario File Watch records use the same field
shape. The engine normalizes exact raw names, allocates
PL/MT by prefix plus `active_chamber`, rejects `sim_*` feedback, and returns
computed `sim_*` variables in the POST response. One engine process
must not receive simultaneous source streams.

The predictive engine remains advisory. No command, setpoint, or actuation path
is authorized by this architecture document.
