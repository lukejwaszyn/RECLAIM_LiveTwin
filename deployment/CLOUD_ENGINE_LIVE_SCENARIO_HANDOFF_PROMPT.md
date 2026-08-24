# Cloud-engine live scenario recovery handoff prompt

Copy the prompt below into a Codex session running **on the Windows Server 2025
predictive-engine VM**. Run it from a checkout of the same commit deployed to the
gateway. Do not paste tokens into chat or command output.

---

You are operating directly on the RECLAIM Windows Server 2025 cloud-engine VM.
Use commands only; do not control GUI applications. Read the repository docs and
execute the diagnostic and repair workflow. Do not weaken authentication, remove
the production `mode=live` gate, create another estimator, or introduce a second
`sim_*` writer.

## Objective

Restore the one required live path:

```text
scenario/cRIO -> edge gateway -> authenticated POST /ingest
-> production DualPushEngine -> GET /state
-> RECLAIMStateBridge -> VM Convene agent -> sim_*
```

The gateway already publishes the same canonical frame directly as exact-name gateway variables.
`sim_*` must come only from this production `DualPushEngine` instance.

## Proven live evidence from the gateway

- Gateway scenario run: `c26e3f03-d380-4e1b-adbf-58edba146ac5`.
- Engine remained on active run: `e61a982f-2d31-456b-9213-7a403361a4af`.
- Public engine health was fast (~0.5 s) and stayed at `ingested_total=2830`.
- Actual gateway runs delivered exact-name gateway variables successfully with zero Convene failures:
  30 frames at 10 Hz, 150 at 10 Hz, 120 at 2 Hz, 180 at 1 Hz, plus one isolated
  frame.
- Cloud acknowledgements were zero for every run. Every frame was eventually
  final-dead-lettered as `timestamp_stale`.
- The isolated frame took 27.8 s before dead-letter. The 1 Hz run accumulated
  15.5-85.9 s of source-to-dead-letter delay.
- The corrected raw scenario contract includes non-empty `source_id`,
  `source_op_state`, `active_chamber=PL`, `cycle_id`, current `ts`, and `vars`.
- Local real-component tests prove the exact gateway canonical frame is accepted
  by a production `DualPushEngine`; this is a deployment/runtime failure.

The most important hypothesis to test is a retryable pre-commit failure when the
engine tries to supersede/adopt the new gateway run (especially durable identity
state persistence or ACL failure). The gateway retains only the later final
`timestamp_stale` reason, so inspect the engine's earlier retryable errors.

## Required reading

Read completely before mutating anything:

- `deployment/REHEARSAL_CONVENE_PUSH.md`
- `deployment/VM_ENGINE_RUNBOOK.md`
- `deployment/WINDOWS_VM_CONVENE_STATE_BRIDGE_RUNBOOK.md`
- `deployment/windows-vm/README.md`
- `cloud_engine/push_ingest_dual.py`
- `cloud_engine/windows/run-ingest-engine.ps1`

## Diagnostic commands

Do not print `RECLAIM_INGEST_TOKEN` or `RECLAIM_READ_TOKEN`.

```powershell
$ErrorActionPreference = 'Stop'
$run = 'c26e3f03-d380-4e1b-adbf-58edba146ac5'
$engineRoot = 'C:\ProgramData\RECLAIM\engine'

Get-Service RECLAIMIngestEngine,RECLAIMStateBridge | Format-Table Name,Status,StartType
Get-NetTCPConnection -State Listen -LocalPort 8078
Invoke-RestMethod http://127.0.0.1:8078/health

Get-ChildItem "$engineRoot\logs" -File |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 8 |
  ForEach-Object {
    Select-String -Path $_.FullName `
      -Pattern $run,'internal_error','persist','permission','supersession','timestamp_stale'
  }

$state = "$engineRoot\state\ingest_state.json"
Get-Item $state | Select-Object FullName,Length,LastWriteTime
Get-Acl $state | Format-List Owner,AccessToString,AreAccessRulesProtected
Get-Content $state

.\deployment\windows-vm\Get-ConvenePublicationDiagnostics.ps1 -RunId $run
```

Also establish whether the service identity can atomically create/replace a
probe file in `$engineRoot\state` without changing `ingest_state.json`. Preserve
all existing state and logs.

## Repair boundary

Repair the actual logged fault only. Likely valid repairs include restoring the
documented NTFS rights for the existing service identity, correcting an invalid
state path, or deploying the reviewed engine revision through the guarded VM
release procedure. Do not delete or reset `ingest_state.json`; it is the durable
deduplication/supersession record. Do not simply raise `--max-frame-age-s`: that
would allow delayed measurements to look freshly predicted without fixing the
pre-commit/throughput failure.

If a restart is necessary, restart only `RECLAIMIngestEngine`, verify loopback
binding and `/health`, and leave the gateway/cRIO stopped until ready for the
coordinated acceptance stream.

## Exit gate

Coordinate one bounded 1 Hz scenario run from the gateway. PASS requires all:

1. Gateway `received` advances and its queue returns to zero.
2. Gateway `delivered` advances; dead-letter count does not.
3. Engine `ingested_total` advances and `active_run_id` equals the gateway run.
4. Authenticated loopback `/state` has `mode=live`, `ingest_status=accepted`, the
   matching run/source/sequence, and fresh `state_age_ms`.
5. State bridge health is `ok`, writes the same correlated state, and renews its
   lease.
6. Convene visibly advances matching `sim_run_id`, `sim_source_id`, and `sim_seq`.
7. `source_id` and `sim_source_id` match; only the VM owns `sim_*`.
8. Stopping the stream makes `sim_data_live=false` after the configured freshness
   limit.

Return the diagnosed root cause, exact files/services changed, commands run,
before/after evidence, selected Git SHA, and rollback path. Do not claim success
from local tests or `/health` alone; the correlated live `sim_*` observation is
mandatory.

---
