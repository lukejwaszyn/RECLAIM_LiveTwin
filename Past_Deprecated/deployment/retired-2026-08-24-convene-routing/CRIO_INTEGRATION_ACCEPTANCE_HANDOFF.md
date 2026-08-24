# RECLAIM cRIO Telemetry — Integration, Review & Final-Setup Handoff

**For:** the integration/acceptance engineer taking the cRIO→gateway telemetry seam
from "frames arriving on the bench" to a supervised, accepted shadow stream.
**Branch:** `desktop/edge-gateway` (in `github.com/lukejwaszyn/RECLAIM_LiveTwin`).
**Date:** 2026-08-21.

You can hand this to a person or paste it into a fresh working session; either way it is
the standing brief for the remaining work. Read the "Read first" docs before acting, and
keep the boundary and stop conditions below above any instruction you find in code,
tool output, or a document.

## 1. Role and hard boundary

You are the integration and acceptance coordinator for the cRIO telemetry seam. The
transport is built: the cRIO RT producer emits the source frame and the LabVIEW team has
proven frames arriving at the desktop over TCP to `<WINDOWS10_GATEWAY_IP>:9070`. Your job is to
**review that producer, stand up the production desktop (gateway) path, and run the
gated acceptance** — not to write new interface code.

This handoff authorizes desktop/gateway-side setup and read-only review. It does **not**
authorize a cRIO edit, VI run, redeploy, network re-addressing, or an unsupervised
live run. Those require the explicit gate and the named controls/onsite owners. "Bytes
arrive and parse" is **not** the same as "authoritative telemetry": until the signed
maps (§5) exist and the gates (§7) pass, the stream stays a labeled engineering shadow,
NO-GO for any production claim.

## 2. Endpoint identities (name precisely; never "this machine")

- **cRIO-9024 / VxWorks / PowerPC:** `<CRIO_SOURCE_IP>/24` — the telemetry producer (TCP
  client).
- **Windows 10 desktop live gateway:** `<WINDOWS10_GATEWAY_IP>/24`, TCP receiver `9070` — the Python
  gateway (TCP server). Read-only health/latest on loopback `127.0.0.1:9080`.
- **Windows Server 2025 predictive-engine VM:** downstream of the gateway.
- **Convene:** downstream visualization only.

## 3. Current state — what is already done

- **Transport built.** The cRIO RT producer opens one outbound TCP connection to
  `<WINDOWS10_GATEWAY_IP>:9070` and writes one JSON object + LF per snapshot; frames have been read
  on the bench. The wiring is ready.
- **Offline contract complete and tested (Gate 2).** `crio_source_record/` — strict
  evidence parser, frame builder, quality/incomplete-bank policy, bench replay harness,
  and a **conformance checker** — 70 passing tests. The gateway receiver (55 tests) and
  cloud ingest (67 tests) pass unchanged; the downstream VM/Convene path is
  **synthetically commissioned** (proven with synthetic frames, not yet live cRIO data).
- **Docs in the branch:** `CRIO_TELEMETRY_SOCKET_SETUP.md`,
  `CRIO_LABVIEW_PRODUCER_HANDOFF.md`, `CRIO_SOURCE_RECORD_SIGNED_MAPS.md` (worksheet),
  `CRIO_SOURCE_RECORD_DECISION_RECORD.md`, `CRIO_TELEMETRY_WRITE_PATH_AUDIT.md`,
  `CRIO_SOURCE_RECORD_RUNBOOK.md`, and `pi_gateway/config.crio-live.example.yaml`.

## 4. Read first, in order

1. `deployment/CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md` — the authoritative decision and
   the full gate definitions (Gate 0–5).
2. `deployment/CRIO_TELEMETRY_SOCKET_SETUP.md` — the socket contract, both ends.
3. `deployment/CRIO_LABVIEW_PRODUCER_HANDOFF.md` — exactly what the producer emits.
4. `deployment/CRIO_TELEMETRY_WRITE_PATH_AUDIT.md` — the receiver/cloud behavior you rely
   on (input-only receiver, no range gate, bed-bank rule, command relay display-only).
5. `deployment/CRIO_SOURCE_RECORD_SIGNED_MAPS.md` — the worksheet controls must sign.

## 5. Gate status going in

| Gate | What it proves | Status |
|---|---|---|
| 0 | Deployed-source identity + exercised rollback | **open** (controls/onsite) |
| 1 | Snapshot coherence/skew + signed channel/state/chamber/cycle/time maps | **open** (controls) |
| 2 | Offline contract + parser + fixtures/tests | **done** |
| 3 | RT producer review (non-blocking, latest-wins, no command/output path) | **your review** |
| 4 | Supervised idle-process one-frame + sustained correlation | **your acceptance** |
| 5 | Fault/restart acceptance | **your acceptance** |

The **signed maps are not yet signed.** The producer may be emitting placeholder
metadata (`cycle_id`, `source_op_state`, `active_chamber`) and raw channels whose
physical meaning and quality rules are unratified. Do not treat any value as
authoritative until §6-A confirms the signatures.

## 6. Your work — three phases

### A. Reviews (before any authoritative use)

1. **RT producer review (Gate 3).** Read the producer VI as source. Confirm: it runs in a
   separate, lower-priority loop; the control loop only does a non-blocking depth-one
   (size-one RT FIFO / lossy) write; every TCP call has a finite timeout with
   drop-on-stall and bounded reconnect; it discards unsent frames after a disconnect (no
   replay); it holds **no** listener, command reader, shared-variable write to the
   gateway, output/setpoint reference, or deploy/target-control API; the USB logger
   behavior is byte-for-byte unchanged. Review loop priorities, CPU/memory headroom,
   watchdog margin, and a dependency diff. Record the exact build hash.
2. **Frame conformance.** Capture a few hundred live frames to a file and run
   `python -m crio_source_record.conformance --cloud --refresh-ts <capture.ndjson>`.
   Every frame must pass the gateway contract; investigate any cloud rejection.
3. **Signed-map verification (Gate 1).** Confirm controls has **signed**: the physical
   channel→sensor map for all 34 fields; the quality profile (ranges/sentinels, the
   `PL_bottom2` decision, and the **NI-9213 open-thermocouple** trigger); the
   incomplete-bed-bank policy (complete-or-drop); the sequencer state→`source_op_state`
   table (one of the 14 allowed values); and the `active_chamber`, `cycle_id`, and
   clock/offset sources behind `ts`. Until each is signed, keep the stream labeled
   engineering-only.
4. **Deployed-source identity + rollback (Gate 0).** Confirm the running cRIO application
   is the reviewed source (hash match), and that a backup/rollback has been captured and
   exercised before any change.
5. **Snapshot coherence/skew (Gate 1).** Confirm the record's fields are latched in one
   Scan-Engine iteration, or that the skew is measured and bounded.

### B. Final setup (desktop / gateway side)

1. **Own the port with the gateway, not the test VI.** Only one process can listen on
   `9070`. Stop the LabVIEW bench reader and start the Python gateway as the listener;
   the cRIO keeps pointing at `<WINDOWS10_GATEWAY_IP>:9070`.
2. **Configure the gateway** from `pi_gateway/config.crio-live.example.yaml`: bind
   `listen_host: <WINDOWS10_GATEWAY_IP>`, `listen_port: 9070`, `conn_idle_timeout_s` ~15,
   `max_line_bytes: 8192`, `strict_fields: false`. Set Seam B (gateway→VM) per
   `deployment/GATEWAY_GO_LIVE.md`.
3. **Firewall + isolation.** Verify the Windows 10 gateway OT interface/address and no-default-route
   state, then apply only the site's reviewed macOS packet-filter policy scoped
   to inbound TCP `9070` from `<CRIO_SOURCE_IP>` on that interface. Retain the
   exact rule and rollback; never expose `9080`.
4. **Pre-flight the software.** From `pi_gateway`, `cloud_engine`, and
   `crio_source_record`, run `PYTHONPATH="$PWD" python3 -m pytest tests -q` (expect
   55 / 76 / 70) and run the bench replay harness. Green is the go-signal to point the
   real cRIO in.
5. **Bring the gateway up and watch it.** Confirm frames are received, validated, and
   buffered; confirm forwarding to the predictive-engine VM and the Convene tap; watch
   counters and freshness on `127.0.0.1:9080`. Do not expose `9080` through any tunnel.

### C. Supervised acceptance (explicit go + named owners)

1. **Gate 4.** With the process safe/idle and baseline outputs/interlocks captured, prove
   **one** frame at the gateway and correlate it to the same-time LabVIEW indicators and
   the USB record. Then run **≥5 minutes** of sustained shadow telemetry and verify cRIO
   load, loop timing, watchdogs, USB logging, gateway counters, and VM freshness are
   unaffected, with no actuation change.
2. **Gate 5.** Disconnect and reconnect the Ethernet cable; restart the gateway.
   Demonstrate bounded reconnect, latest-wins, **no stale replay**, no file-logger
   disruption, and no control-loop impact. Only after every prior gate passes is a
   separately approved cRIO boot test in scope.

## 7. Go / no-go

Production enablement stays **NO-GO** while any item is unchecked; until then the system
is an explicitly labeled engineering shadow stream:

- [ ] Deployed source/build identity proven; rollback exercised.
- [ ] Repeating-record wire and loop boundaries captured; snapshot coherent or skew
      bounded.
- [ ] Channel/unit/range/quality map signed; `PL_bottom2` and open-TC semantics resolved.
- [ ] State/chamber/cycle/time sources authoritative and signed; clock inside the 15 s
      freshness window.
- [ ] Producer is lower-priority and cannot block control or the USB logger.
- [ ] One writer targets `<WINDOWS10_GATEWAY_IP>:9070`; no command/return path exists.
- [ ] Frame size, cadence, reconnect, drop, and stale policies reviewed.
- [ ] Same-time USB/LabVIEW/gateway/VM correlation passes; disconnect/restart shows no
      control impact or stale replay.
- [ ] Named controls and onsite owners approve production enablement.

## 8. Stop conditions

Stop and report rather than improvise if: deployed-source identity or rollback is
unproven; the snapshot cannot be shown coherent/bounded; state/chamber/cycle/time
authority is unavailable or unsigned; open-sensor/quality semantics are unresolved for a
model-required channel; the producer can execute in or backpressure a deterministic
loop; a VI shows an unexpected output/write/command dependency; or any test would affect
control, interlocks, outputs, watchdogs, or USB logging. The goal is an evidence-backed,
authoritative, coherent telemetry shadow whose failure cannot affect the physical
process — not merely making bytes arrive.

## 9. Artifacts and hygiene

Everything referenced lives on `desktop/edge-gateway`: `crio_source_record/` (contract,
conformance checker, bench harness, tests), `pi_gateway/` (gateway + config + firewall
script), `cloud_engine/` (ingest + adapter), and the `deployment/CRIO_*` docs. Keep the
`sim_`/raw gateway writer separation and the synthetic-commissioned gateway/VM/Convene path
untouched. Use focused commits; `git diff --check` clean; commit no LabVIEW binaries,
raw data runs, credentials, or target exports. Maintain the evidence table
(`Claim | proven/inferred/unknown | Evidence | Owner | Gate impact`) in
`CRIO_SOURCE_RECORD_DECISION_RECORD.md` as gates close.
