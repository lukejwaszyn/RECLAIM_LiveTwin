# Live gateway and scenario-host decision

**Effective:** 2026-08-24
**Status:** authoritative; supersedes every MacBook-as-live-gateway statement

## Fixed ownership

| Role | Host | Allowed input | Allowed output |
|---|---|---|---|
| Live-data client/gateway | Windows 10 desktop | Real cRIO/LabVIEW stream | Production live-data path |
| Scenario host | MacBook | Local synthetic generators and approved capture replays | Convene scenario machine |
| Predictive engine | Prepared separately | Live/scenario interface prepared by its owner | `sim_*` computed state |

The MacBook must not connect to, listen for, impersonate, or forward the real
cRIO live stream. Its scenario receiver binds only `127.0.0.1`, runs in
`harness` or `replay` mode, and has no direct cloud transport or ingest token.
Convene publishing remains enabled for scenario data. Any Convene-to-VM pipe is
owned and configured outside the MacBook workstream.

## Scenario naming

The MacBook publisher adds no blanket prefix and strips no source-defined
prefix. It preserves exact canonical field names, including approved `gw_`
names that already exist in a scenario/source contract. It never publishes a
cloud-owned `sim_` field.

## Supplied Windows capture

`08_03_26_12_57_43 PM_data_stream.txt` is treated only as data. It contains one
timestamp header and 5,894 records, each with the same 34 comma-separated
`name: value` channels. The MacBook scenario replayer preserves those values and
wraps them in a scenario envelope; it does not claim the MacBook acquired them
live.

Use `tools/replay_windows_data_stream.py` for bounded replay through the local
scenario receiver. Unknown source state is labeled `S_Unknown`; it is never
invented from sensor values.
