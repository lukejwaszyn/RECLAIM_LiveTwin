# Cloud-engine VM audit and Convene-routed rework

**Effective:** 2026-08-24

**Use with:** `CURRENT_CONVENE_ROUTED_SYSTEM_HANDOFF.md`

**Status:** prepared locally; VM inventory and deployment remain supervised work

The PowerShell files in `deployment/windows-vm/` are source artifacts on the
scenario desktop. Do not run them on the MacBook and do not start a local cloud
engine or `sim_*` publisher. Copy/pull the same SHA on the actual VM, then run
them there.

## Required end state

The VM runs one loopback-only `RECLAIMIngestEngine`. Convene sends the same
35-field text/object contract from Windows live, MacBook scenario, or approved
replay to `/ingest`. The engine does not classify origin. It returns
computed state in the same HTTP response under a flat
cloud-owned `sim_*` `variables` object. No state bridge, `sim_vars.json` file,
direct variable publisher, scenario service, or application-level Cloudflare
tunnel participates.

```text
Windows live text -> Convene variables ---\
Mac scenario text -> Convene variables -----+-> POST /ingest -> dual engine
Approved replay -> Convene variables -------/                       |
                                                                   v
                                                   response.variables.sim_*
                                                                   |
                                                                   v
                                                               Convene
```

One engine process may receive only one active source stream at a time. Pause
Convene forwarding before switching from live to scenario or scenario to live.
Concurrent streams require isolated engine instances and identity stores.

## Source naming and text-extraction contract

The source names are exact and case-sensitive. Do not add `gw_`. The physical
live record is authoritative `active_chamber` plus the 34 LabVIEW fields; it does
**not** need to contain a
run ID, source ID, sequence, timestamp, cycle, mode, or source operating state.

Convene sends that record to `POST /ingest`. The engine then adds
receipt-time transport metadata: a stable per-process generated run ID, the
receipt/header source identity, a monotone receipt sequence, UTC receipt timestamp,
and a conservative cycle/state classification. `mode=telemetry` explicitly means
origin is unclassified. These values describe
engine receipt and are never represented as LabVIEW-produced metadata.

If Convene can provide it, set `X-RECLAIM-Source-ID` to the stable live machine
identity. Otherwise the engine uses `convene-routed-frame`. The generated canonical
envelope is:

`schema_version`, `mode`, `run_id`, `source_id`, `cycle_id`, `seq`, `ts`,
`source_op_state`, `active_chamber`.

The raw field set is the signed 34-field LabVIEW order defined by
`cloud_engine/labview_map.py` and repeated in `pi_gateway/macos/README.md`.
MacBook File Watch extracts `active_chamber` and each raw field from the one-line
`.txt` frame with:

```text
(?:^|, )FIELD_NAME: ([^,\r\n]+)
```

Convene may therefore submit extracted values as strings. The current engine
adapter restores:

- numeric raw fields to floats;
- `TRUE`/`FALSE` to booleans;
- `NaN` to unavailable and omits it before inference;
- authoritative `active_chamber` without renaming.

The same adapter accepts already typed flat objects and nested canonical frames.
Production accepts only honestly labeled `live`, `harness`, or `replay`. Any
flat `sim_*` input is rejected to prevent a feedback loop. `active_chamber` is
authoritative for shared `MW_*` power allocation.

`POST /ingest` is the sole current endpoint. Missing envelope metadata is generated
as receipt-owned `mode=telemetry`. A legacy complete canonical envelope remains
accepted, but it is not required for the current interface. With no chamber in an
older capture, PL pre/process/post flags select PL; otherwise RF-on selects MT;
RF-off with no PL activity selects `NONE`. Current frames always supply the
authoritative `active_chamber`.

## VM pickup procedure

Give the VM agent this document plus the release branch and SHA. The agent must
report the VM's existing service identity, checkout/path, installed source hash,
listener ownership, and competing processes before changing anything.

1. Pull the exact branch/SHA and verify `git status --porcelain` is empty. Do not
   deploy from a dirty checkout or copy selected files from a different SHA.
2. Run `deployment/windows-vm/Audit-ConveneRoutedEngine.ps1` before stopping or
   modifying any service.
3. Preserve the audit JSON and current service/file hashes as rollback evidence.
4. Treat these as blockers:
   - `RECLAIMStateBridge` registered or running;
   - `cloudflared` service/process used for the application telemetry route;
   - `C:\ConveneAgent\sim_vars.json` or a bridge installation still active;
   - quick-tunnel/scenario scheduled tasks;
   - more than one listener on 8078 or a non-loopback bind;
   - a dirty deployed checkout or missing current contract markers.
5. Distinguish application tunnels from separately authorized administrative
   access. Record ownership before stopping anything.
6. Run `Test-ConveneRoutedEngineContract.ps1` without switches to prove the
   checked-out source contract.
7. During a controlled cutover with Convene forwarding paused, set the existing
   ingest/read token environment variables and rerun with `-ExerciseEndpoint`.
8. Deploy only `cloud_engine/`, its locked Python environment, and the existing
   loopback Windows service runner/template after the audit identifies the
   actual service paths and account. Do not use an archived pinned-SHA script.
9. Restart the single engine service, rerun the audit, then enable exactly one
   Convene source route.

## Convene binding and final proof

MacBook File Watch uses this owner-private, atomically replaced file:

`/Users/lukewaszyn/Library/Application Support/RECLAIM/scenarios/convene_file_watch.txt`

For every field, leave JSON path blank and capture with
`(?:^|, )FIELD_NAME: ([^,\r\n]+)`. Route every source to `/ingest`.
The Windows live machine and MacBook File Watch may send either the complete `text/plain` raw record
(`active_chamber` followed by 34 fields) or an object containing its exact
extracted variables to `/ingest`. The engine still accepts an older bare
34-field capture and uses conservative chamber inference only as fallback.

After the VM loopback contract passes, prove the actual routing in this order:

1. Keep all Convene source routes paused and confirm there is one `sim_*` writer.
2. Enable only MacBook nominal PL; confirm the watched frame changes atomically,
   engine receipt `seq`/timestamps advance, PL is selected, and correlated
   returned `sim_*` values arrive.
3. Stop it, then repeat in isolation for power-outage MT and lunar PL.
4. Exercise loss-of-data/`NaN`; confirm no crash, no fabricated measurement, and
   no stale frame represented as fresh.
5. Stop scenarios. Enable only Windows live; submit `active_chamber` plus its 34
   raw fields and confirm `/ingest` generates receipt provenance and returns
   correlated state.
6. Save the SHA, timestamps, source identity, engine response, and Convene evidence
   for every case. Disable a route before enabling the next one.

Repository tests and MacBook file updates are preflight only. The path is not
end-to-end proven until these steps pass through the authenticated Convene route
and the actually deployed VM service.

## Acceptance evidence

Retain the release SHA, engine source SHA-256, service account/path, loopback
listener, health output, source machine identity, mode/run/cycle/sequence,
engine disposition, selected chamber, sensor-valid flags, and returned
`variables` keys.

Required endpoint cases:

| Case | Required result |
|---|---|
| Older bare 34-field PL through `/ingest` | accepted; receipt metadata generated; PL receives shared power |
| Current raw live with `active_chamber: MT` | accepted; authoritative MT is preserved and receives shared power |
| Same 35-field text from any origin | accepted as unclassified telemetry; strings restored |
| Legacy complete labeled envelope | accepted with its explicit label preserved |
| `NaN` sensors | unavailable values omitted; no crash or fabricated measurement |
| Flat `sim_*` input | rejected as feedback |
| Duplicate/regressed sequence | no estimator re-step |
| Stale timestamp | rejected final |
| Response ownership | every returned scalar variable begins `sim_` |

The repository proves these behaviors locally. They are not VM-proven until the
audit and endpoint exercise run on the actual deployed service.
