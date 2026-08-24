# Cloud-engine VM audit and Convene-routed rework

**Effective:** 2026-08-24

**Use with:** `CURRENT_CONVENE_ROUTED_SYSTEM_HANDOFF.md`

**Status:** prepared locally; VM inventory and deployment remain supervised work

The PowerShell files in `deployment/windows-vm/` are source artifacts on the
scenario desktop. Do not run them on the MacBook and do not start a local cloud
engine or `sim_*` publisher. Copy/pull the same SHA on the actual VM, then run
them there.

## Required end state

The VM runs one loopback-only `RECLAIMIngestEngine`. Convene sends either the
Windows live machine or MacBook scenario machine frame to `POST /ingest`. The
engine returns computed state in the same HTTP response under a flat
cloud-owned `sim_*` `variables` object. No state bridge, `sim_vars.json` file,
direct variable publisher, scenario service, or application-level Cloudflare
tunnel participates.

```text
Windows live text -> Convene live variables ---\
                                             -> POST /ingest -> dual engine
Mac one-frame text -> Convene scenario vars --/                    |
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

The source names are exact and case-sensitive. Do not add `gw_`. The canonical
envelope is:

`schema_version`, `mode`, `run_id`, `source_id`, `cycle_id`, `seq`, `ts`,
`source_op_state`, `active_chamber`.

The raw field set is the signed 34-field LabVIEW order defined by
`cloud_engine/labview_map.py` and repeated in `pi_gateway/macos/README.md`.
MacBook File Watch extracts each field from the one-line `.txt` frame with:

```text
(?:^|, )FIELD_NAME: ([^,\r\n]+)
```

Convene may therefore submit extracted values as strings. The current engine
adapter restores:

- `seq` to an integer;
- numeric raw fields to floats;
- `TRUE`/`FALSE` to booleans;
- `NaN` to unavailable and omits it before inference;
- all envelope identity strings without renaming.

The same adapter accepts already typed flat objects and nested canonical frames.
Production accepts only honestly labeled `live`, `harness`, or `replay`. Any
flat `sim_*` input is rejected to prevent a feedback loop. `active_chamber` is
authoritative for shared `MW_*` power allocation.

## VM pickup procedure

1. Pull the exact branch/SHA and do not deploy a dirty checkout.
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

## Acceptance evidence

Retain the release SHA, engine source SHA-256, service account/path, loopback
listener, health output, source machine identity, mode/run/cycle/sequence,
engine disposition, selected chamber, sensor-valid flags, and returned
`variables` keys.

Required endpoint cases:

| Case | Required result |
|---|---|
| Flat typed live PL | accepted; PL receives shared power; mode/source preserved |
| Flat text-extracted harness MT | accepted; strings restored; MT receives shared power |
| Replay frame | accepted and remains labeled replay |
| `NaN` sensors | unavailable values omitted; no crash or fabricated measurement |
| Flat `sim_*` input | rejected as feedback |
| Duplicate/regressed sequence | no estimator re-step |
| Stale timestamp | rejected final |
| Response ownership | every returned scalar variable begins `sim_` |

The repository proves these behaviors locally. They are not VM-proven until the
audit and endpoint exercise run on the actual deployed service.
