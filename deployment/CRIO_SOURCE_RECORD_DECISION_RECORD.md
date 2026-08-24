# cRIO Source-Record — Gate 2 Decision Record

**Date:** 2026-08-21
**Branch:** `desktop/edge-gateway`
**Scope:** offline, repository-only. No cRIO edit, VI run, deployment, network change,
or live send. This record documents what the Gate 2 offline contract proves, what it
deliberately does not, and the evidence standing behind each claim.

## 1. Decision restated

The selected production seam is the existing source-assembled process record (the
repeating `name: value` record `Data Stream.vi` writes to the cRIO USB volume), reused
— after the controls gates pass — by a bounded, lower-priority RT-side TCP client that
emits one UTF-8 JSON object + LF to the existing gateway at `<WINDOWS10_GATEWAY_IP>:9070`. This is
the authoritative decision from `CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md`. This record
does not re-open that decision; it delivers the Gate 2 offline artifacts that make the
seam reviewable before any cRIO window.

## 2. What was built (this branch)

The `crio_source_record/` package (61 passing tests, all offline):

- `evidence_parser.py` — strict fail-closed parser for the legacy record. Evidence
  input only. Rejects missing `": "` delimiter, duplicate names, non-finite numbers,
  invalid booleans, unknown fields, and any unrecognized/partial schema. Exact zero
  stays valid.
- `frame_builder.py` — builds the source frame (contract §4). Requires authoritative
  `source_id`/`ts`(UTC ISO-8601)/`cycle_id`/`source_op_state`/`active_chamber`; never
  invents them. Enforces the 8192-byte line bound. Measured fixture frame sizes: min
  203 / nominal ~902–911 / max 1319 B.
- `quality_policy.py` — per-channel validity flags and the incomplete-bed-bank policy
  (backlog item 1), applied at the source layer with **no change to the signed cloud
  validator**.
- `bench_replay.py` — no-cRIO harness streaming fixtures over real TCP into a loopback
  gateway receiver, then through the real cloud engine (backlog item 3).

No file under `pi_gateway/` or `cloud_engine/` was modified; the pre-existing suites
remain at 55 and 67 passing, confirming zero regression.

## 3. Evidence table

`proven` = established by committed evidence or a passing test against real code.
`inferred` = a reasonable reconstruction not independently confirmed. `unknown` =
requires controls/onsite evidence not available offline.

| Claim | Status | Evidence | Owner | Gate impact |
|---|---|---|---|---|
| The record is a repeating `name: value` process record on the USB volume | proven | PATH_FORWARD §1, §2.2; 13 retained captures | controls | Gate 1 |
| The latest stable schema is the 34-field order in `FIELDS_34` | proven | PATH_FORWARD §2.3 | controls | Gate 1 |
| The 30- and 32-field schemas are exact reconstructions | inferred | Record grew 30→32→34 (§2.3); which fields were added is not in committed evidence | controls | Gate 1 |
| Earliest 30-field captures have `": "` delimiter defects on `MT_crucible_temperature` and `MW_reverse_coupler` | proven | §2.3; encoded in `fixtures/record_30_delimiter_defect.txt`; parser rejects it | RECLAIM dev | Gate 2 |
| `PL_bottom2 ≈ 1383` is NOT a valid temperature until controls signs its meaning | unknown | §2.3; quarantined by default in `QualityProfile` | controls | Gate 1 |
| An ungated `PL_bottom2` contaminates the plastics bed mean (~1656 K) | proven | `push_ingest_dual._bed_temp` averages every `PL_T_bed_tc*`; no range gate at `_require_finite_number` | RECLAIM dev | Gate 1/2 |
| Dropping one PL bed TC rejects the whole frame today (loses MT+MW) | proven | Completeness gate `push_ingest_dual` (`if bank and bank != tc1..4`); test `test_default_quarantine_makes_cloud_reject_the_whole_frame` | RECLAIM dev | Gate 2 |
| An empty bed bank passes the cloud gate and yields `<CH>_sensor_valid=false` | proven | Gate is `if bank and ...`; C6 no-fabrication path; test `test_suppress_policy_keeps_frame_and_flags_chamber_invalid` | RECLAIM dev | Gate 2 |
| Torr→kPa and degC→K conversions are correct through the real adapter | proven | `labview_map.normalize`; tests assert `PL_P_chamber ≈ 139.6847`, `PL_T_wall_meas ≈ 497.269` | RECLAIM dev | Gate 2 |
| `labview_map.__main__` self-check asserts a STALE `PL_P_chamber ≈ 139.6986` (correct is 139.6847) | proven | `1047.721528 × 0.1333224 = 139.6847`; assert at `labview_map` `__main__`; pytest suites unaffected | RECLAIM dev | Gate 2 (hygiene) |
| `labview_map` maps only 2 of 3 MT temperatures; several record fields have no map target | proven | `_MT_BED=(MT_bottom,)`, `MT_top` mapped, `MT_crucible_temperature` unmapped; `PL_wall1/2`, `PL_flow_meter`, `PL_Probe1/2`, `MW_reverse_coupler` unmapped (framer preserves, cloud ignores) | controls | Gate 1 |
| Gateway receiver is input-only (no send path) | proven | `receiver.py` has no `send`/`sendall`; bounded pre-LF buffer; idle drop | gateway | Gate 3 |
| `/command` relay is display-only; no actuation path in the repo | proven | prior audit (publisher/status); confirmed no output/VISA/command reader in gateway | gateway | Gate 3 |
| The inspected VI/project copy is the deployed `startup.rtexe` source | unknown | Project names `/c/ni-rt/startup/startup.rtexe` but build spec not populated; hashes recorded (§2.1) | controls/NI | Gate 0 |
| The record's fields are latched in one Scan Engine iteration | unknown | One serialized line does not prove single-iteration coherence | controls/NI | Gate 1 |
| Authoritative `cycle_id`/`source_op_state`/`active_chamber`/per-frame time exist at source | unknown | Record carries one start timestamp only; no physical cycle/state/chamber channel identified | controls/NI | Gate 1 |

### 3.1 Addendum — integration pre-flight session, 2026-08-23 (commit `3608872`)

| Claim | Status | Evidence | Owner | Gate impact |
|---|---|---|---|---|
| All three suites pass unchanged at `3608872`: pi_gateway 55, cloud_engine 67, crio_source_record 70 | proven | pytest runs 2026-08-23 (integration workstation, Python 3.11) | RECLAIM dev | §B.4 pre-flight |
| Bench replay green end-to-end: sent 3 / received 3 / accepted 3 / rejected 0, max frame 902 B | proven | `python -m crio_source_record.bench_replay` 2026-08-23 | RECLAIM dev | §B.4 pre-flight |
| Conformance checker binds the REAL gateway framer and REAL cloud engine (not reimplementations) | proven | `conformance.py` imports `reclaim_edge.framer`/`push_ingest_dual`; exercised 2026-08-23 | RECLAIM dev | Gate 3 §6 |
| Quarantining `PL_bottom2` with NO bank policy yields gateway-PASS but whole-frame cloud rejection (`telemetry_invalid`) on every frame; `SUPPRESS_INCOMPLETE` on the same records yields cloud-accepted | proven | conformance runs 2026-08-23 on fixture-built frames (871 B rejected / 806 B accepted) | RECLAIM dev | Gate 3 checklist 6.3 |
| `config.crio-live.example.yaml` Seam A values match the socket contract (bind <WINDOWS10_GATEWAY_IP>:9070, idle 15 s, 8192 B, strict_fields false) | proven | line-by-line review vs `CRIO_TELEMETRY_SOCKET_SETUP.md` §3, 2026-08-23 | gateway | §B.2 |
| Windows firewall rule is scoped to `<CRIO_SOURCE_IP>→<WINDOWS10_GATEWAY_IP>:9070`, OT interface has no default route, and 9080 has no exposure | open | capture the Windows rule and rollback onsite | gateway | §B.3 |
| Gate 3 producer review remains OPEN — VI source unavailable this session; evidence questionnaire issued | unknown | `deployment/CRIO_GATE3_PRODUCER_REVIEW_CHECKLIST.md` | controls/NI + integration | Gate 3 |
| Gates 0 and 1 remain OPEN — no deployed-source hash, rollback exercise, coherence proof, or signed maps received | unknown | signed-maps worksheet still UNSIGNED | controls/NI | Gate 0/1 |

## 4. What Gate 2 deliberately does not establish

Snapshot coherence/skew, deployed-source identity, rollback, and every physical
channel→sensor assignment remain controls-owned and unmet. The parser encodes the
schema; it does not sign the meaning of any channel. The frame builder requires
authoritative metadata; it does not manufacture it. The project stays **NO-GO** for any
source change until Gate 0 and Gate 1 pass.

## 5. Follow-ups recorded

- Correct the stale `labview_map.__main__` self-check constant (139.6986 → 139.6847).
  Left unchanged here because it is controls-adjacent and outside the Gate 2 remit; it
  is a `__main__`-only assertion with no effect on the pytest contract suites. Flagged
  for a separate focused fix with controls awareness.
- Controls to sign the channel/unit/quality worksheet in
  `CRIO_SOURCE_RECORD_SIGNED_MAPS.md`, including the incomplete-bank policy choice.
