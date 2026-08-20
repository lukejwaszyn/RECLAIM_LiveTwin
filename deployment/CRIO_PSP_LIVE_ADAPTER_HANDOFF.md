# cRIO NI-PSP Live Telemetry Adapter Handoff

**Date:** 2026-08-20  
**Branch:** `desktop/edge-gateway`  
**Status:** Source complete and offline-tested; retained as a diagnostic engineering
fallback. It is not the selected production seam. See
`CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md`.

## Intended topology

`cRIO 192.168.1.2` -> read-only Windows NI-PSP adapter on `192.168.1.1` -> local gateway TCP `192.168.1.1:9070` -> predictive-engine VM.

No cRIO application, shared variable, output, setpoint, command, or target control is written by the adapter. No Convene endpoint was contacted during this work.

Later discovery proved that `Data Stream.vi` already assembles a repeating named
record for USB logging. The production direction is now to reuse that source-built
record after controls proves its coherence and deployed-source identity. This PSP
adapter remains useful for read-only scan-resource diagnostics and rollback-free
engineering probes.

## Delivered implementation

The adapter is `crio_psp_adapter/windows/reclaim-psp-adapter.ps1`. It uses the installed 32-bit `CWDSLib.CWDataSocket` COM API in read-only mode, one adapter mutex, one TCP writer, compact UTF-8 JSON with exactly one LF, an 8192-byte limit, finite typed scalars, bounded latest-value storage, freshness/skew checks, and reconnect-without-replay behavior.

The live allowlist is deliberately audit-only:

- `scan_Mod2_TC0_degC` through `scan_Mod2_TC7_degC`
- `scan_Mod3_AI0_raw` through `scan_Mod3_AI2_raw`

The prior provisional aliases were removed. The supplied panel screenshot contradicted TC2 as `MT_top` and TC5-TC7 as pyrolysis hotspot aliases. Replaying those aliases through the predictive engine could mark MT valid and publish a false CRITICAL/SAFE_STATE result. Exact zero remains valid; no undocumented open-circuit/high-limit sentinel is assumed.

Cloud normalization now converts Celsius with `K = degC + 273.15`, Torr with `kPa = Torr * 0.1333224`, preserves zero, rejects non-finite values, and leaves the audit-only scan names out of PL/MT model inputs. Explicit PL/MT sensor-availability gates are published even when a chamber is absent.

Gateway framing and receiving enforce the same 8192-byte, UTF-8, object/scalar, finite-value, and line-recovery contract. The bridge configuration source uses a 30-second publication heartbeat and 45-second lease; this corrects the former 5-second lease versus 30-second heartbeat mismatch but still requires the normal supervised VM release.

## Live findings

The old adapter previously reached gateway sequence 2209 at `2026-08-20T02:50:49.3840724Z`, proving the desktop-to-gateway/VM transport path, but with the now-removed provisional aliases.

After LabVIEW was stopped and its remaining process was closed, the new reader could not obtain a valid current snapshot:

- `psp://NI-cRIO9024-016F1385.local/Mod2/TC0` accepts a read-only connection but repeatedly returns only `System.Int32 0` with no NI metadata. The adapter correctly rejects this as an uninitialized/default placeholder.
- Opening `Mod2/TC1` while TC0 is subscribed fails with NI error `-1967390704` (`socket disconnected by peer`).
- The local gateway remains healthy but stale at sequence 2209 because no valid new frame is emitted.

This isolates the immediate blocker to the cRIO PSP/Scan Engine publisher or its deployed shared-variable state, not JSON framing, gateway TCP, naming, or cloud conversion. The adapter was intentionally left stopped after the bounded probe so it does not publish fake zeros or stale replay.

## Recovery and acceptance procedure

1. On the cRIO, verify the Scan Engine/shared-variable publisher is running and the deployed variables `Mod2/TC0..TC7` and `Mod3/AI0..AI2` are readable by a fresh remote subscriber. A supervised cRIO reboot/redeploy of the approved existing application may be needed; do not change its logic.
2. From the desktop, launch exactly one continuous adapter instance:

   ```powershell
   & "$env:WINDIR\SysWOW64\WindowsPowerShell\v1.0\powershell.exe" `
     -NoProfile -NonInteractive -ExecutionPolicy Bypass `
     -File ".\crio_psp_adapter\windows\reclaim-psp-adapter.ps1" `
     -Source Psp -Sink Tcp `
     -CrioHost NI-cRIO9024-016F1385.local `
     -GatewayHost 192.168.1.1 -GatewayPort 9070 -MaxFrames 0
   ```

3. Confirm `http://127.0.0.1:9080/health` shows `received`, `delivered`, and `last_ack_age_s` updating at the three-second cadence. Confirm `/latest` contains only the eleven audit-only names above and a current timestamp.
4. Confirm VM engine ingestion and `/state` freshness independently. On the VM, use `deployment/windows-vm/Get-ConvenePublicationDiagnostics.ps1` to check the bridge service/token/state-file path. Do not use Convene itself for this diagnostic.
5. Release the VM Torr conversion and 45-second bridge lease through the supervised VM process, then verify at least five minutes of sustained freshness and restart/disconnect recovery.

## Remaining mapping work

Do not promote scan channels into canonical PL, MT, or MW names until a versioned worksheet supplies the exact source resource, engineering unit/scale, valid range, invalid/quality semantics, and evidence. The current live source has no authoritative cycle ID, operation state, active chamber, or cRIO timestamp; the adapter marks those engineering assumptions explicitly. MW fields, purge-pump/process fields, pressure scaling, and the SMELT probes remain unbound.

## Rollback

Stop only the Windows adapter process/task. No cRIO or gateway rollback is required because the adapter is input-only and no installed gateway source was changed during the live probe. If the VM source release is later deployed, restore its prior package/config through the VM owner’s normal rollback procedure.

## Verification record

- Cloud tests: 67 passed.
- Bridge tests: 67 passed.
- Adapter tests: 13 passed. The first final run was blocked by a local pytest temp-directory ACL, not an assertion failure, and was rerun with a repository-local temp base.
- `git diff --check`: required before commit.
