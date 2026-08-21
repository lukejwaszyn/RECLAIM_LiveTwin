# cRIO Telemetry Write-Path Audit

A read-only audit of every place a telemetry frame is written, validated, transformed,
or could conceivably become an actuation path — from the gateway ingress at
`192.168.1.1:9070` to the cloud estimator. Line references are against this branch
(`desktop/edge-gateway`) and were re-verified here, not carried over from the earlier
zip. Purpose: prove the shadow-stream design cannot backpressure or actuate the
physical process, and record the exact validity/quality behavior the source layer must
respect.

## 1. Gateway receiver — input only (Seam A)

`pi_gateway/reclaim_edge/receiver.py`. The `Receiver` thread accepts one cRIO
connection, reads LF-delimited lines within a bounded pre-LF buffer, and enqueues to
the durable buffer. **There is no `send`/`sendall` anywhere in the module** (the only
textual "send" is a comment about a half-open FIN). The single write side effect is
`buffer.enqueue(...)` at `_handle_line`. Half-open sockets are dropped after
`conn_idle_timeout_s` so a reconnect can be served, and a line exceeding
`max_line_bytes` (8192) drops the connection before any oversized allocation. **Finding:
the receiver cannot transmit to the cRIO; it is structurally incapable of actuation.**

## 2. Cloud structural validation — no physical range gate

`cloud_engine/push_ingest_dual.py`, `_require_finite_number` (line ~504): the docstring
states *"Physical ranges deliberately do not live here: this is the inference-safe
structural boundary only."* Validation enforces type, finiteness, boolean-ness, and
bed-bank shape — **never a physical range**. **Finding: an out-of-range but finite value
(e.g. `PL_bottom2 ≈ 1383 °C`) passes structural validation and, ungated, normalizes to
~1656 K and contaminates `_bed_temp` (line 145), which averages every `PL_T_bed_tc*`
present.** This is why a controls-signed quality gate is mandatory, and why the source
layer quarantines `PL_bottom2` by default.

## 3. Bed-bank completeness gate — whole-frame rejection on a partial bank

`push_ingest_dual._validate_raw_telemetry`, bed-bank check ending at the raise on line
546 (`"{chamber} bed sensor bank must contain {expected} channels"`), run on the
normalized values. The gate is `if bank and bank != [tc1..N]` — so:

- a **partial** PL bed bank (e.g. `tc1, tc3, tc4`) raises `telemetry_invalid` and the
  **entire frame is rejected**, losing MT and MW with it;
- an **empty** bed bank passes the gate, and the chamber publishes `sensor_valid=false`
  (no fabrication — the C6 path), keeping the rest of the frame.

**Finding: the difference between "reject the whole frame" and "keep the frame, flag the
chamber" is decided entirely by whether the source sends a partial bank or an empty
one.** The `quality_policy.SUPPRESS_INCOMPLETE` option uses this to keep MT/MW alive
without any change to this validator. `ingest()` raises on rejection; `ingest_line()`
returns a disposition dict — use the latter to observe rejections.

## 4. Conversion correctness and a stale self-check constant

`cloud_engine/labview_map.py` applies degC→K (`+273.15`) and Torr→kPa (`×0.1333224`).
Verified against the fixtures: `PL_chamber_pressure = 1047.721528 Torr` →
**139.6847 kPa**, `PL_surface_temp = 224.119084 °C` → **497.269 K**.

**Finding (hygiene):** the module's `__main__` self-check at **line 226** asserts
`PL_P_chamber ≈ 139.6986`, but `1047.721528 × 0.1333224 = 139.6847`. This branch has
**not** fixed the stale constant. Impact is confined to `python labview_map.py`
(the `__main__` self-check would fail); the pytest contract suites do not exercise it,
so the 67-test suite is unaffected. Recommend a separate one-line fix
(`139.6986 → 139.6847`) with controls awareness; not changed here to keep this branch's
diff scoped to the source-record package.

## 5. Adapter map coverage gaps

`labview_map` maps `_MT_BED=(MT_bottom,)` and `MT_top`, but **not**
`MT_crucible_temperature` — the record carries three MT temperatures and only two are
mapped. Record fields with **no** adapter target: `PL_wall1`, `PL_wall2`,
`PL_flow_meter`, `PL_Probe1`, `PL_Probe2`, `MW_reverse_coupler`, `MW_period`,
`MW_width`. The gateway framer preserves these (logged once as "unknown field
preserved for cloud normalization"); the cloud adapter ignores them. **Finding: these
are signed-map gaps for controls** — see the worksheet. No data is silently discarded,
but nothing consumes these channels yet.

## 6. Command relay — display only, no actuation

`pi_gateway/reclaim_edge/publisher.py`: an optional `command` field on a cloud response
is stored (`last_command`, lines ~92–95) and exposed **read-only** via the loopback
status endpoint (`last_command`, `last_command_age`, lines ~224–230). It is surfaced
for display on `127.0.0.1` only. **Finding: there is no code path anywhere in the repo
that turns a `command` into a cRIO write, setpoint, output, or deploy action.** The
loopback status port must not be exposed through a tunnel.

## 7. RT-side producer constraints (for Gate 3, not authorized here)

When Gate 3 is authorized, the producer must be an outbound TCP **client** only (one
connection to `192.168.1.1:9070`), branch one immutable snapshot into a depth-one,
latest-wins handoff with no wait, run serialize+connect+write in a lower-priority loop
with finite timeouts and drop-on-stall, discard stale unsent frames after disconnect
(no replay), and apply the signed quality map so bad channels never reach the
estimator. Telemetry loss must never delay control, interlocks, or the USB logger. This
audit records that the *downstream* path cannot actuate; the *upstream* RT safety
properties remain a Gate 3 review item and are not proven by anything offline.

## 8. Summary

| Concern | Result |
|---|---|
| Gateway can transmit to cRIO | No — receiver is input-only |
| Telemetry can backpressure control | Not from the downstream path audited here (Gate 3 reviews the RT loop) |
| Out-of-range value silently used | Yes if ungated — **quality gate mandatory** |
| One open bed TC destroys a frame | Yes today (REJECT); avoidable via source SUPPRESS |
| Conversions correct | Yes (kPa/K verified); `__main__` self-check constant stale |
| Command path actuates | No — display-only on loopback |
