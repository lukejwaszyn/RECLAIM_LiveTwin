# RECLAIM Live Telemetry Architecture

**Status:** proposed production contract  
**Scope:** cRIO/LabVIEW → laptop gateway → cloud predictive engine → Convene

## Purpose and decision

RECLAIM has proven the telemetry pipeline with synthetic input. This contract
adds the controls that permit live cRIO telemetry without allowing rehearsal,
replay, stale, or duplicate frames to overwrite operator-facing state.

Convene's `sim_` prefix is retained. It is the namespace Convene applies to
values exported by the RECLAIM publisher; it does not mean the upstream values
are synthetic. The engine remains the state producer; Convene remains the
consumer, visualizer, and digital-thread system.

```
cRIO / LabVIEW
  │ raw telemetry, source state, active chamber
  ▼
Laptop gateway
  │ validates, stamps provenance, buffers, authenticated HTTPS POST
  ▼
Cloud ingress / dual predictive engine
  │ validates order and run identity; estimates PL and MT independently
  ▼
Canonical flat /state record
  │ exactly one selected publisher
  ▼
Convene agent / machine publish
  └── sim_op_state, sim_PL_op_state, sim_MT_op_state, ...
```

## Operating rules

1. A Convene variable has **one active writer**. During a live run, the live
   dual engine is the only publisher for the RECLAIM variable set. Harness,
   replay, CSV import, and legacy single-chamber services are disconnected from
   those bindings.
2. Live, replay, and synthetic traffic have a required `mode` and `run_id`.
   Production accepts `mode: "live"` only.
3. The cRIO sequencer is authoritative for the system state. The engine may
   derive a chamber-local idle/cooling state, but never silently replace the
   system state solely because RF power is zero.
4. The exported record is flat and scalar-first, matching both Convene
   machine-publish and `sim_vars.json` limitations.
5. Convene bindings use `sim_op_state`, `sim_PL_op_state`, and
   `sim_MT_op_state`; no dashboard assumes legacy unprefixed names.

## Canonical inbound telemetry

The gateway sends newline-delimited JSON to `POST /ingest`. `vars` carries raw
LabVIEW fields or normalized channels.

```json
{
  "schema_version": "reclaim.telemetry.v1",
  "mode": "live",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "source_id": "reclaim-crio-01",
  "seq": 1842,
  "ts": "2026-08-05T16:24:03.250Z",
  "cycle_id": "2026-08-05T16:20:00Z-pl-01",
  "source_op_state": "S_MicrowaveHeating",
  "active_chamber": "PL",
  "vars": {
    "PL_bottom1": 100.2,
    "PL_surface_temp": 40.1,
    "PL_process": true,
    "MW_RF": true,
    "MW_power": 3000.0,
    "MW_reverse": 100.0
  }
}
```

Required fields are `schema_version`, `mode`, `run_id`, `source_id`, `seq`,
`ts`, `cycle_id`, `source_op_state`, `active_chamber`, and `vars`. `run_id` is
created once for each commanded test, rehearsal, or production execution and
is never reused. `seq` increases within `(run_id, source_id)`.

`active_chamber` is sent explicitly by the sequencer as `PL`, `MT`, or `NONE`.
Existing inference from `PL_process`, `MW_RF`, or power becomes a diagnostic
plausibility check, not an authority for a live run. During migration, inbound
`op_state` may be accepted as an alias for `source_op_state`, with a warning;
it is removed after the migration date.

## Ingress validation and idempotency

Before a frame advances either estimator, the cloud performs these checks:

| Check | Required behavior |
|---|---|
| Authentication | Require a gateway-specific token or mTLS identity at the TLS ingress; do not expose unauthenticated `/ingest` through the tunnel. |
| Schema | Reject unknown schema versions and missing envelope fields (per-frame, final). |
| Mode | Production rejects harness/replay (per-frame, final) and logs the attempt. |
| Timestamp | Require UTC ISO-8601; frames beyond the freshness window are rejected **final** — deprecated data never advances an estimator, and the gateway dead-letters it instead of retrying. |
| Run identity | A fresh, fully valid frame with a new `run_id` **supersedes** the active run (event `RUN_SUPERSEDED`); frames from retired runs are rejected final (`run_superseded`). A gateway reboot therefore recovers without operator action, while stale leftovers from the old run cannot re-pin it (they fail freshness first). |
| Sequence | Enforce a **monotone `seq` per `(run_id, source_id)`**: `seq <= last committed` is a duplicate (final, never re-steps), gaps are counted and evented (`SEQ_GAP:n`), never filled with fabricated samples. Identity persists to disk so a service restart plus gateway retry cannot double-step. |
| Physics/schema | Validate numeric finiteness, units, explicit chamber selection, and sensor mapping before estimator input. A chamber with no valid temperature reading is **not stepped** and publishes `<CH>_sensor_valid: false` (plus `SENSOR_MISSING` when it is the active chamber) — never a fabricated default. |

### Ingest acknowledgement contract (v1.1)

`POST /ingest` accepts newline-delimited frames and answers `200` with one
result per posted line whenever the request itself was processed — a mix of
good and bad frames never fails the batch (no head-of-line blocking):

```json
{"ingested":2,"duplicate":1,"rejected":1,
 "results":[{"i":0,"status":"accepted","code":null,"final":true},
            {"i":1,"status":"duplicate","code":null,"final":true},
            {"i":2,"status":"rejected","code":"timestamp_stale","final":true},
            {"i":3,"status":"rejected","code":"internal_error","final":false}],
 "total":1842,"command":{}}
```

Gateway obligations: ack `accepted`/`duplicate`; **dead-letter** `rejected` with
`final: true` (audit-retained, never retried); retry `final: false` and any
non-2xx/transport failure with backoff. Every contract violation is final —
retrying cannot make an old timestamp fresh. Only internal engine errors are
transient, and those do not commit sequence identity, so the retry re-steps
cleanly. Duplicates must never advance the engine a second time.

The engine integrates real elapsed time between source `ts` values (clamped),
not an assumed fixed rate, so forecasts stay valid at any telemetry cadence.

## Operational-state contract

Three fields are published with deliberately distinct meanings:

| Output | Authority | Meaning |
|---|---|---|
| `op_state` | validated `source_op_state` | Singular system state for Convene visualization, state logic, and requirement verification. |
| `PL_op_state` | plastics engine | Chamber-local state; may be `S_Idle` with no attributed PL forward power. |
| `MT_op_state` | metals engine | Chamber-local state; may be `S_Idle` with no attributed MT forward power. |

The engine resolves `op_state` in this order:

1. Publish a valid sequencer-supplied `source_op_state` unchanged.
2. If the safety controller has a confirmed latched safe state, publish
   `S_SafeState` and retain the original value in `source_op_state`.
3. Otherwise publish `S_Unknown` and event `STATE_SOURCE_MISSING`; never
   default to `S_MicrowaveHeating`.

This preserves valid zero-power states such as `S_Evacuate`, `S_CoolDown`, and
`S_Complete`, while keeping useful per-chamber idle labels. State strings must
be members of the SysML operational-state enumeration; unknown strings are
rejected, not rendered as nominal.

## Canonical outbound state

The dual engine exposes a flat scalar record. These are output names before
Convene applies the `sim_` namespace.

```json
{
  "schema_version": "reclaim.state.v1",
  "mode": "live",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "source_id": "reclaim-crio-01",
  "seq": 1842,
  "ts_source": "2026-08-05T16:24:03.250Z",
  "ts_engine": "2026-08-05T16:24:03.311Z",
  "cycle_id": "2026-08-05T16:20:00Z-pl-01",
  "active_chamber": "PL",
  "source_op_state": "S_MicrowaveHeating",
  "op_state": "S_MicrowaveHeating",
  "PL_op_state": "S_MicrowaveHeating",
  "MT_op_state": "S_Idle",
  "PL_T_bed_est": 625.4,
  "MT_T_bed_est": 295.2,
  "ingest_status": "accepted",
  "ingest_age_ms": 61,
  "last_event": "NONE"
}
```

`/manifest` has the same `schema_version` and declares every published system,
chamber, provenance, health, command, and estimator field. Non-finite values
are omitted/null rather than replaced with a made-up number. Export scalar
`last_event` and `event_count` because an agent accepting only scalars cannot
safely consume an events array.

## Convene binding and publisher policy

Convene receives the state output using its `sim_` prefix. Bind:

| Convene variable | Use |
|---|---|
| `sim_op_state` | primary system-state visualization, state machine, and requirement verification |
| `sim_source_op_state` | source-controller audit comparison |
| `sim_PL_op_state`, `sim_MT_op_state` | chamber views |
| `sim_run_id`, `sim_cycle_id`, `sim_seq`, `sim_ts_source` | provenance and stale-data detection |
| `sim_mode`, `sim_ingest_status`, `sim_ingest_age_ms` | feed-health display and live-data gate |
| `sim_PL_*`, `sim_MT_*` | chamber measurements, estimates, forecasts, advisories, and commands |

Every dashboard shows `sim_mode`, `sim_run_id`, `sim_seq`, and data age beside
`sim_op_state`. If the mode is not `live`, status is not `accepted`, or age is
over the configured limit, it shows **DATA NOT LIVE** instead of a process-state
color.

Choose exactly one publisher per environment:

- Preferred: the machine-publish bridge reading cloud `/state` and writing to
  the paired Convene agent API.
- Alternative: the `sim_vars.json` bridge.

These mechanisms must never publish the same RECLAIM binding set concurrently.
Use a separate Convene project, agent registration, or explicit
`rehearsal_` namespace for demonstrations.

## Deployment topology

The cloud dual engine is the only production process on the live port. The
gateway uses authenticated outbound HTTPS to the Cloudflare-protected cloud `/ingest`
URL; Convene receives cloud `/state` through the one selected publisher.

```
Laptop gateway -- authenticated HTTPS --> Cloudflare ingress --> dual engine :8078
                                                          │
                                                          └--> one Convene publisher --> Convene sim_ variables

Harness / replay --> isolated port and isolated Convene namespace only
Legacy single engine --> disabled in production
```

Production launches the dual ingest service, not `push_ingest_service.py` and
not the self-driving harness service. The runbook identifies the deployed build
by `schema_version`, dual manifest, and `/health` mode—not merely port number
or process name.

## Migration and verification gates

1. Add tests for required envelope fields, state enumeration, sequence
   deduplication, stale timestamps, run transitions, and refusal of harness mode.
2. Send PL and MT frames and assert `/state` and `/manifest` contain `op_state`,
   `PL_op_state`, `MT_op_state`, `run_id`, `cycle_id`, `seq`, and `mode`.
3. Shadow live frames into a non-publishing dual instance. Compare source state,
   active chamber, timestamp, and sequence count to gateway logs.
4. Map `sim_` variables from the manifest, then disconnect all legacy bare
   `op_state` bindings before enabling the new production binding.
5. Begin a new `run_id`, enable one publisher, and verify the known sequence
   `S_BatchLoad → S_Evacuate → S_MicrowaveHeating → S_CoolDown → S_Complete`
   with advancing `sim_seq` and acceptable age.
6. Roll back by disabling the new publisher/binding only. Retain gateway frames and
   cloud acceptance logs; never blend a harness stream into the live set.

## Implementation ownership

| Component | Required change |
|---|---|
| LabVIEW / cRIO | Emit `source_op_state`, explicit `active_chamber`, `cycle_id`, and timing; preserve raw sensor values. |
| Laptop gateway | Create `run_id`; stamp `source_id`, `seq`, `ts`, and `mode`; buffer/retry idempotently; authenticate to ingress. |
| Cloud dual engine | Validate before stepping; track identity/order; publish canonical system/chamber state plus provenance and feed health. |
| Convene publisher | Pass scalar provenance and health fields; run one publisher per binding set. |
| Convene model/dashboard | Bind `sim_op_state` as system state, `sim_PL_op_state`/`sim_MT_op_state` as local state, and gate display/verification on status and freshness. |

The contract separates what the source controller says the system is doing,
what each chamber is doing, and whether the twin data is current and trusted.
That removes the current ambiguity without changing Convene's useful `sim_`
convention.
