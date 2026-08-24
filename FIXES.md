# RECLAIM Live Twin — Hardening Changes (2026-08-10)

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

Implements the full priority fix order from `CODE_REVIEW.md` for the flight
deployment: NI cRIO → Windows 10 desktop live gateway → production path → cloud-VM
dual predictive engine → Convene. Every fix is covered by a test; both suites
pass (18 cloud + 9 gateway) plus an end-to-end HTTP exercise of the real
publisher against the real production server.

> **Platform note (2026-08-14):** this document was written against a
> Raspberry Pi 3B+ gateway. The deployment target is now an onsite
> Windows 10 desktop; hardware references have been updated accordingly.
> The fixes themselves are unchanged — several were motivated by Pi 3B+
> constraints and are noted as such where the rationale still matters.

## The ingest contract is now v1.1 (per-frame acknowledgement)

The single most important change. `POST /ingest` returns `200` with one
`{status, code, final}` result per posted line; a bad frame never fails its
batch-mates. The gateway acks accepted/duplicate frames, **dead-letters** frames
rejected as `final` (kept auditable in a bounded SQLite table with the
reason), and retries only transient failures. This removes both permanent
wedge modes found in review:

- an outage longer than the freshness window no longer deadlocks the queue —
  stale frames are rejected final and dead-lettered, satisfying the hard
  requirement that deprecated data never reaches the estimator or `/state`;
- a single poison frame no longer blocks delivery for days.

## Fix-by-fix

| Review ID | Change |
|---|---|
| C1/H3 | Per-frame ack contract above (`push_ingest_dual.py` handler + `publisher.py` + `buffer.dead_letter`). Stale = rejected final, by design. |
| C2 | Run supersession: a fresh, fully valid frame with a new `run_id` retires the old run (`RUN_SUPERSEDED` event); retired runs are rejected final. A gateway reboot recovers with zero operator action; stale old-run leftovers cannot re-pin the run because they fail freshness first. |
| C3 | Monotone `seq` per `(run_id, source_id)`: regressions/duplicates never re-step; gaps counted, published as `gap_count`, and evented (`SEQ_GAP:n`), never fabricated. |
| C4 | `IngestIdentityStore` persists run/seq identity atomically to `RECLAIM_INGEST_STATE` (required in `--production`); a cloud restart plus gateway retry can no longer double-step. Identity commits only **after** a successful estimator step, so transient engine errors retry cleanly instead of losing the frame (also fixes M3's silent-loss case). |
| C5 | Seal monitor: kPa→Pa conversion at the boundary; phase-gated to `S_Evacuate`/`S_SealCheck` using the **system** op-state (the chamber-local label relabels zero-power evacuation as `S_Idle`); pump-down curve re-anchors at each evacuation entry. A leak (chamber stuck at 1 atm while evacuating) now raises `SEAL_LEAK`; no false alarms outside evacuation. |
| C6 | No fabricated measurements: a chamber with no valid temperature readings is not stepped and publishes `<CH>_sensor_valid: false` (+ `SENSOR_MISSING` when it is the active chamber) instead of a made-up 300 K. |
| C7 | Sequencer authority: explicit `active_chamber: NONE` is honored (power attributed to neither chamber); missing `MW_RF` now means RF **off**, not on; sensor inference survives only as a `CHAMBER_MISMATCH` diagnostic event, never an override. |
| H1 | Real dt: the engine integrates the actual elapsed time between source timestamps (clamped 0.05–10 s), applied to the UKF predict, the mass-flow advance, and the residual-slope window. Forecast lead times are now valid at any cRIO cadence. |
| H2 | Receiver: TCP keepalive + configurable idle drop (`conn_idle_timeout_s`), so a half-open socket from a cRIO power-cycle can no longer stall telemetry until a manual restart. |
| H4 | GET `/state` `/manifest` `/history` `/command` now support a `RECLAIM_READ_TOKEN` bearer (give it to the Convene publisher, which also feeds the Convene-native `.stp` visualization); `/health` stays open for probes. Token checks are constant-time. `/state` adds `state_age_ms` computed at read time, so every consumer can gate DATA NOT LIVE without trusting a stored age. |
| H5 | Ingest token removed from the systemd command line; consumed from the (now required, mode-600) `EnvironmentFile` only. |
| H6 | Historical Linux unit: `StateDirectory=reclaim-edge` fixed the then-current first-boot crash loop. The package name remains `pi_gateway`; the authoritative live gateway is now the Windows 10 desktop. The MacBook uses `launchd` only for its loopback scenario-host service. |
| H7 | Config fail-fast: explicit-but-missing path, unparseable YAML, unknown (typo) keys, invalid transport/mode, and live-HTTPS-without-token all refuse to start; defaults-only operation is a logged dev mode. Cloud side: `EnvironmentFile` is now mandatory. |
| M1 | `--feed replay` raises a clear, actionable error instead of a bare ImportError. |
| M2 | All identity decisions + estimator stepping run under one lock; the HTTP handler consumes per-call dispositions instead of racing on shared `last_ingest`. |
| M5 | Unknown-field warnings log once per field name, not per frame (was ~2M lines/day at 1 Hz — an SD-card killer on the original Pi 3B+ target). |
| M6 | MQTT connects lazily inside `deliver` (a down broker is a retryable failure, not a thread death); receiver/publisher liveness is supervised — a dead worker exits the service non-zero so systemd restarts it. `paho-mqtt` pinned `<2.0`. |
| M7 | The framer's sequence high-water mark persists in the buffer DB (same transaction as the frame); resuming a pinned `run_id` after a gateway restart continues the sequence instead of colliding. |

## Operational notes for this deployment

- **Cloudflare Tunnel:** the engine binds `127.0.0.1:8078`; `cloudflared` on the
  VM is the only path in. Route both `POST /ingest` and the GET endpoints
  through the tunnel hostname (the Convene publisher and its `.stp` visualization
  read `/state` through it).
- **Gateway sizing:** the gateway is stdlib + requests, so it is comfortable on
  either target. The warn-once logging fix and the bounded dead-letter table
  were driven by the SD card on the original Pi 3B+ — the fragile part of that
  build — and both remain worth keeping on the laptop. Keep
  `buffer_max_frames` at 500 k (~a week at 1 Hz) and monitor `/health`
  `dead_letter` + `drops`.
- **Freshness:** end-to-end "no deprecated data" is enforced three times —
  cloud rejects stale frames final at ingest, `/state` self-reports
  `state_age_ms` at read time, and Convene (publisher + `.stp` visualization)
  gates DATA NOT LIVE on `sim_mode`/`sim_ingest_status`/age.
- **New preflight gates** (see `docs/RECLAIM_Remote_Gateway_Preflight.md` §4):
  stale-batch, gateway-reboot supersession, cloud-restart dedup, and freshness
  decay are now explicit go/no-go checks before Convene cutover.
