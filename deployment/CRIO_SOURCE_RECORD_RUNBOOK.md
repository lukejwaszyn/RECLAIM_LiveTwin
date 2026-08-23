# cRIO Source-Record — Offline Runbook

Operational steps for the **offline, no-cRIO** work in `crio_source_record/`. Every
step here runs on a developer workstation against sanitized fixtures. None of it
touches the cRIO, a VI, the gateway host, or any live endpoint.

## 0. Guardrails (read first)

- Do **not** run or open any VI as an adapter. The inspected VIs carry output/VISA/RF
  dependencies; treat them as read-only mapping evidence and hash what you inspect.
- Do **not** commit raw `*_data_stream.txt` runs, LabVIEW binaries, screenshots with
  secrets, credentials, or target exports. Fixtures must be sanitized.
- Do **not** change `pi_gateway/` or `cloud_engine/` production behavior to make a
  source-side experiment pass. The quality policy is applied at the source layer for
  exactly this reason.

## 1. Set up and run the suites

```bash
cd crio_source_record
PYTHONPATH="$PWD" python3 -m pytest tests -q          # expect 70 passing (61 Gate 2 + 9 conformance)
```

Baselines (must stay green — proof of no regression):

```bash
cd ../pi_gateway   && PYTHONPATH="$PWD" python3 -m pytest tests -q   # 55
cd ../cloud_engine && PYTHONPATH="$PWD" python3 -m pytest tests -q   # 67
```

## 2. Sanitize a retained capture into a fixture

The parser is fail-closed and positional. A fixture is one or more records, each a
block of `"<field>: <value>"` lines in the exact `FIELDS_34` (or 30/32) order, blocks
separated by a blank line, with the leading start-timestamp header removed. Confirm a
candidate fixture parses before committing it:

```bash
PYTHONPATH="$PWD" python3 - <<'PY'
from crio_source_record.evidence_parser import parse_records
recs = parse_records(open("crio_source_record/fixtures/record_34_stream.txt").read())
print(len(recs), "records", {r.schema for r in recs})
PY
```

A capture that fails to parse (delimiter defect, unknown field, reordered fields,
non-finite value) is **rejected by design** — that is evidence about the capture, not a
parser bug to work around.

## 3. Build a candidate frame from a record

`frame_builder.build_frame` requires all five authoritative metadata values. There is
no default; a missing one is an error. Until controls signs the authority maps, supply
clearly-labeled placeholder metadata for offline size/shape checks only:

```bash
PYTHONPATH="$PWD" python3 - <<'PY'
from crio_source_record.evidence_parser import parse_record
from crio_source_record.frame_builder import build_frame
rec = parse_record(open("crio_source_record/fixtures/record_34_nominal.txt").read())
line = build_frame(rec.valid_vars(),
                   source_id="reclaim-crio-rt-01",
                   ts="2026-08-21T12:00:00Z",
                   cycle_id="OFFLINE-PLACEHOLDER",
                   source_op_state="S_MicrowaveHeating",
                   active_chamber="PL")
print(len(line), "bytes; PL_bottom2 present:", b"PL_bottom2" in line)
PY
```

## 4. Add a candidate signed quality profile

A profile only acts on ranges/sentinels once `signed_by` is set. Encode a controls-
signed profile like this, and record the signer in `CRIO_SOURCE_RECORD_SIGNED_MAPS.md`:

```python
from crio_source_record.evidence_parser import QualityProfile
prof = QualityProfile(
    signed_by="controls: <name> <date>",
    quarantine=frozenset(),                       # or keep PL_bottom2 if still unproven
    ranges={"PL_bottom1": (0.0, 900.0)},          # example, from the signed worksheet
    sentinels={"PL_bottom2": (1383.0,)},          # ONLY if controls confirms the sentinel
)
```

## 5. Run the bench replay harness

```bash
cd ..
PYTHONPATH="pi_gateway:cloud_engine:$PWD" python3 -m crio_source_record.bench_replay
```

This binds a loopback port, streams the fixture stream through the real gateway
receiver and durable buffer, and drains it through the real cloud engine. It proves
framing, byte bounds, conversions, quarantine, duplicate/stale/reconnect, and
absent-field gating — all with no cRIO.

## 6. When to stop and escalate

Stop and report rather than improvise if deployed-source identity or rollback is
unproven; the snapshot cannot be shown coherent/bounded; state/chamber/cycle/time
authority is unavailable; open-sensor/quality semantics for a model-required channel
are unresolved; or any step would touch control, interlocks, outputs, watchdogs, or
USB logging. The goal is an evidence-backed shadow stream whose failure cannot affect
the physical process — not merely making bytes arrive.
