# Live gateway and scenario-host decision

**Effective:** 2026-08-24
**Status:** authoritative; supersedes every MacBook-as-live-gateway statement

## Fixed ownership

| Role | Host | Allowed input | Allowed output |
|---|---|---|---|
| Live-data client/gateway | Windows 10 desktop | Real cRIO/LabVIEW stream | Convene live machine |
| Scenario host | MacBook | Local synthetic generators and approved capture replays | Convene scenario machine |
| Routing plane | Convene | Source-machine variables | Common `/ingest` request to cloud engine and computed state back to Convene |
| Predictive engine | Cloud VM | Route-normalized source telemetry | `sim_*` computed state returned through Convene |

The MacBook must not connect to, listen for, impersonate, or forward the real
cRIO live stream. Its scenario receiver binds only `127.0.0.1`, runs in
`harness` or `replay` mode, and has no direct cloud transport or ingest token.
Direct Convene API publishing is disabled on the MacBook. Its scenario data is
exposed as one owner-private, atomically replaced text frame for Convene File
Watch. Convene's internal routing is the only approved source-to-engine and
engine-to-display path.

Production cloud ingest accepts the common 35-field record without attempting to
infer whether it is live or scenario. Receipt provenance uses `mode=telemetry`.
One engine process accepts only one active source stream at a time.

The current Windows physical record contains authoritative `active_chamber` plus
the 34 raw LabVIEW fields. Convene
routes it to `/ingest`; the engine creates explicitly receipt-owned run,
source, sequence, timestamp, cycle, and state metadata when absent. Chamber
inference is fallback-only for older 34-field captures.
MacBook scenarios expose the identical 35-field record and use the same `/ingest`
interface. The engine cannot and must not classify origin from that record.

## Scenario naming

The MacBook publisher adds no blanket prefix and strips no source-defined
prefix. It preserves exact canonical field names, including approved `gw_`
names that already exist in a scenario/source contract. It never publishes a
cloud-owned `sim_` field.

## Supplied Windows capture

`08_03_26_12_57_43 PM_data_stream.txt` is treated only as data. It contains one
timestamp header and 5,894 records, each with the same 34 comma-separated
`name: value` channels. The MacBook scenario replayer preserves those values,
adds authoritative `active_chamber` to the watched frame, and does not claim the
MacBook acquired them live.

Use `tools/replay_windows_data_stream.py` for bounded replay through the local
scenario receiver. Unknown source state is labeled `S_Unknown`; it is never
invented from sensor values.
