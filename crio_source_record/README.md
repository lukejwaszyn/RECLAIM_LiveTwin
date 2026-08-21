# crio_source_record — Gate 2 offline contract for the cRIO source record

This package is the **offline, repository-only** contract for the RECLAIM Live Twin's
selected telemetry seam: the source-assembled process record that `Data Stream.vi`
already writes to the cRIO USB volume. It exists so that everything about that seam
which can be proven **without touching the cRIO** is proven, tested, and reviewable
before the first supervised cRIO window.

> **Hard boundary.** Nothing in this package touches the cRIO, opens a VI, deploys,
> changes the network, or sends to a live endpoint. It parses sanitized evidence,
> builds candidate frames in memory, and replays fixtures into a *loopback* gateway.
> The production direction (a bounded, lower-priority RT-side TCP client to
> `192.168.1.1:9070`) is **NO-GO** until the controls-owned Gate 0/1 identity,
> coherence, authority, and rollback gates pass. See
> `deployment/CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md`.

## Modules

| Module | Role |
|---|---|
| `evidence_parser.py` | Strict, fail-closed parser for the legacy `name: value` USB record. **Evidence input only — never the wire contract.** |
| `frame_builder.py` | Builds the source frame: one UTF-8 JSON object + LF (contract §4). Requires authoritative `source_id`/`ts`/`cycle_id`/`source_op_state`/`active_chamber`; never invents them. Enforces the 8192-byte bound. |
| `quality_policy.py` | Per-channel validity + incomplete-bed-bank policy (backlog item 1). Applied at the source layer; **no change to the signed cloud validator.** |
| `bench_replay.py` | No-cRIO bench harness (backlog item 3): fixtures → real TCP → real gateway `Receiver` → durable buffer → real cloud `DualPushEngine`. |
| `fixtures/` | Sanitized 30/32/34-field records, a delimiter-defect capture, and a `PL_bottom2` overrange record. No raw runs are committed. |
| `tests/` | 61 tests. `conftest.py` puts `pi_gateway` and `cloud_engine` on the path so the mapping/policy/bench tests bind to the **real** framer and cloud. |

## Running

```bash
# from this directory
PYTHONPATH="$PWD" python3 -m pytest tests -q          # 61 passing

# standalone bench summary (loopback only, no cRIO)
cd .. && PYTHONPATH="pi_gateway:cloud_engine:$PWD" python3 -m crio_source_record.bench_replay
```

## Schema authority

`FIELDS_34` is the evidence-backed 34-field order from PATH_FORWARD §2.3 and is
**authoritative**. `FIELDS_32` and `FIELDS_30` are **UNCONFIRMED reconstructions**: the
captures proved the record grew 30 → 32 → 34, but *which* fields were added at each
step is not established by committed evidence. The reconstructions assume the trailing
probe pair (`PL_Probe1/2`) and the wall pair (`PL_wall1/2`) were the later additions;
controls must confirm this against the retained intermediate captures before either is
trusted.

## Quality and the `PL_bottom2` quarantine

A value may be marked invalid **only** by a `QualityProfile`, which is controls-owned
and **unsigned by default**. The sole default action is the conservative quarantine of
`PL_bottom2` (the persistent ~1383 reading whose physical meaning is unproven). Ranges
and open-channel sentinels apply **only** once a profile is signed, so no physical
validity judgement is ever made on unsigned inference. The real open-thermocouple
trigger must ultimately be the NI-9213's own open-TC status, not a value sentinel.

## Incomplete-bank policy (backlog item 1)

`quality_policy.BankPolicy` offers two behaviors, and the choice is **controls-owned**:

- `REJECT` (default) — the partial bed bank reaches the cloud and the whole frame is
  rejected `telemetry_invalid`, exactly as today. No behavior change ships without a
  signed decision.
- `SUPPRESS_INCOMPLETE` (recommended once open-TC semantics are signed) — the affected
  bed bank is dropped entirely, so the cloud keeps the frame, marks that chamber
  `sensor_valid=false`, and MT/MW survive. Verified end-to-end against the real cloud
  in `tests/test_quality_policy.py`.

See `deployment/CRIO_SOURCE_RECORD_DECISION_RECORD.md` for the evidence table and
`deployment/CRIO_SOURCE_RECORD_SIGNED_MAPS.md` for the worksheet controls must sign.
