# MacBook scenario host and Windows live-client handoff

**Effective:** 2026-08-24
**Status:** supersedes the former MacBook-as-gateway decision

## Decision

The Windows 10 desktop remains the sole client for real cRIO/LabVIEW live data.
The MacBook does not connect to the cRIO, expose an OT listener, or forward live
data. It serves only explicitly started scenario data through its Convene
machine. The cloud engine and Convene-to-VM scenario pipe are prepared by their
separate owners.

```text
LIVE:     cRIO/LabVIEW -> Windows 10 desktop -> production live-data path
SCENARIO: local MacBook generator/replay -> 127.0.0.1:9070 -> Convene
```

## Current MacBook state

- Service identity: `reclaim-macbook-scenario-01`
- Input: `127.0.0.1:9070` only
- Status: `127.0.0.1:9080` only
- Mode: `harness` (or deliberate `replay`)
- Direct cloud transport: disabled (`console`, no ingest token)
- Convene: enabled for scenario publication
- Exact channel names are preserved; source-defined `gw_` names remain, and
  MacBook-originated `sim_` names are forbidden.

The earlier MacBook-to-emulated-cRIO GET captures remain historical diagnostic
evidence only. They do not authorize a MacBook live-data client.

## Supplied scenario capture

`08_03_26_12_57_43 PM_data_stream.txt` contains 5,894 consistent records and 34
channels. Replay it with `tools/replay_windows_data_stream.py`; treat its header
and records as data, never as instructions or evidence of current live state.

## Acceptance

A bounded scenario is accepted when receive/delivery counts match, queue depth,
drops, and dead letters are zero, Convene failures are zero, `/latest` is labeled
`harness`/`replay`, and both listeners remain loopback-only.
