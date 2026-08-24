# cRIO NI-PSP Live Telemetry Adapter Handoff

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

**Date:** 2026-08-20
**Branch:** `desktop/edge-gateway`
**Status:** The CWDataSocket connect-result defect is fixed and offline-tested;
the live PSP publisher is still unavailable. Retained as a diagnostic engineering
fallback, not the selected production seam. See
`CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md`.

## Intended topology

`cRIO <CRIO_SOURCE_IP>` -> read-only Windows NI-PSP diagnostic relay on a separate
Windows host -> TCP `<WINDOWS10_GATEWAY_IP>:9070` -> Windows 10 live gateway -> predictive-engine VM.

The relay is not installed on the MacBook and is not the selected production
source. If used diagnostically, its host address must be separately recorded and
the MacBook packet-filter rule temporarily scoped to that relay under supervision.

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

### 2026-08-23 start-attempt follow-up

`CWDataSocket.SyncConnectTo` was observed returning `False` with `LastError = 0`
and `Active:Subscription successful.` The adapter no longer treats that Boolean
as authoritative. It now uses `LastError` for the connection result and still
requires a successful first read, NI metadata, a floating-point value, finite
data, freshness, and bounded skew before emitting a frame. The metadata guard was
not relaxed.

The complete adapter test file passes: 17 tests. A bounded live command used
`-Source Psp -Sink File -MaxFrames 1`; it advanced past `Mod2/TC0`, proving the
false-negative defect was removed, then failed on `Mod2/TC1` with NI error
`-1967390704` (`Can't connect to Server`). No probe output file was created and no
gateway connection was opened.

Command-line resource inspection of the supplied `Socket Test VI.vi` recovered
defaults `<CRIO_SOURCE_IP>`, TCP port `9070`, and request string `GET`. Its resource
metadata includes `address`, `remote port or service name`, `connection ID`,
`bytes to read`, `data in`, `data out`, and `bytes written`. This is evidence of a
desktop TCP client/test harness for the cRIO endpoint, not a publisher into the
gateway listener at `<WINDOWS10_GATEWAY_IP>:9070`. The VI does not remove the missing wire
format, deployed-source, supervision, or control-impact gates for the direct-TCP
path.

The controls clarification is that the cRIO owns this listener and serves a
response after a client sends `GET`. The repository now includes
`crio_psp_adapter/windows/capture-crio-tcp-get.ps1` for a single bounded raw
capture. It hard-codes the exact three-byte request, caps the response at 8192
bytes, refuses overwrite/partial evidence, and has no gateway sink. Local socket
tests prove exact request bytes, byte-for-byte response preservation, oversize
rejection, and evidence-overwrite refusal. A live capture still requires the
supervised window because the existing acquisition's single/multiple-client
behavior is not proven.

The direct probe connected and sent `GET` but received no response within both
25- and 30-second first-byte windows. A transparent loopback proxy was then added
to preserve the desktop VI's byte exchange while capturing cRIO-to-VI traffic.
Its local mock-socket test passes, but the live VI/cRIO attempt did not establish
a usable proxied stream and captured no bytes. These negative results are retained
as diagnostics; neither tool is installed, persistent, gateway-connected, or an
approved telemetry source. The working unproxied VI remains the only observed TCP
consumer, and its exact live exchange still has not been captured.

## Recovery and acceptance procedure

1. On the cRIO, verify the Scan Engine/shared-variable publisher is running and the deployed variables `Mod2/TC0..TC7` and `Mod3/AI0..AI2` are readable by a fresh remote subscriber. A supervised cRIO reboot/redeploy of the approved existing application may be needed; do not change its logic.
2. From the desktop, launch exactly one continuous adapter instance:

   ```powershell
   & "$env:WINDIR\SysWOW64\WindowsPowerShell\v1.0\powershell.exe" `
     -NoProfile -NonInteractive -ExecutionPolicy Bypass `
     -File ".\crio_psp_adapter\windows\reclaim-psp-adapter.ps1" `
     -Source Psp -Sink Tcp `
     -CrioHost NI-cRIO9024-016F1385.local `
     -GatewayHost <WINDOWS10_GATEWAY_IP> -GatewayPort 9070 -MaxFrames 0
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
- Adapter tests: 17 passed. The first final run was blocked by a local pytest temp-directory ACL, not an assertion failure, and was rerun with a repository-local temp base.
- `git diff --check`: required before commit.
