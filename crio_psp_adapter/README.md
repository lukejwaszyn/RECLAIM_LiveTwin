# Windows cRIO NI-PSP adapter proof of concept

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

> **Current role:** diagnostic engineering fallback, not the selected production
> source. See `deployment/CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md` for the proven
> USB record seam and the authoritative path forward.

This adapter uses the installed 32-bit NI DataSocket COM client to subscribe to
an explicit input-module allowlist on `<CRIO_SOURCE_IP>`. It has no runtime resource
browse option and contains no shared-variable write, target-control, deployment,
output-module, command, setpoint, or actuation call.

Live PSP mode fails closed unless every item returns NI metadata and a
floating-point scan value. Every NI-9213 value keeps an audit-only raw name,
`scan_Mod2_TC0_degC` through `scan_Mod2_TC7_degC`; the `_degC` suffix records
the known source unit without claiming a process-channel identity. Direct
NI-9205 readings remain `scan_Mod3_AIn_raw`; they are not mislabeled as scaled
Torr or temperature. An approved, versioned channel/scaling/quality profile is
required before any of these scan values can become a `PL_*` or `MT_*` model
input.

The POC allowlist is limited to the candidate `Mod2/TC0..TC7` and
`Mod3/AI0..AI2` resources recorded in the controls handoff. Its current source
profile is exactly eight audit-only `scan_Mod2_TCn_degC` values plus three
module-level `scan_Mod3_AIn_raw` values. It emits no canonical `PL_*`, `MT_*`,
or `MW_*` process field.

This quarantine is evidence-driven. The operator-panel screenshot at
2026-08-19 22:37:54 EDT and gateway sequence 1984 about 97 seconds later
contradicted the earlier `TC2 -> MT_top` and `TC5..TC7 -> PL_bottom2..4`
assignments. Repeated values near 1379 were non-identifying; they are not proof
of a channel identity or an invalid-value sentinel. An offline replay also
showed that the old `TC2`/`TC3` aliases could create a false complete MT
measurement and drive `CRITICAL`/`SAFE_STATE`. Therefore all eight semantic
aliases are removed from the live PSP source profile, including the candidates
that the one screenshot did not independently disprove.

Thermocouples remain raw degrees Celsius and exact zero is retained. The three
NI-9205 values are not yet approved engineering-unit pressure or temperature;
the desktop scaling/source seam must be identified before they can be renamed
and interpreted as Torr or degrees Celsius. Cycle/source identity is visibly
labeled as engineering POC. Until authoritative metadata resources are
approved, the envelope uses the POC assumption `source_op_state=S_Idle` and
`active_chamber=NONE`; these are not cRIO sequencer observations and cannot
support full-cycle validation.

The live transport POC sustained one frame every three seconds. The attempted
nominal 1 Hz cadence produced downstream `timestamp_stale` rejections, so 1 Hz
is not an accepted live cadence and the cause remains to be resolved. This is
observed commissioning behavior, not a deployed cadence approval.

Missing fields are absent from each canonical frame; the adapter never invents
or clears them. Convene may retain an older raw gateway value from synthetic or prior
frames, so every absent field—especially `MW_*` and `PL_purge_pump`—must
be gated unavailable using current-frame presence/provenance/freshness. A
retained display value is not evidence that the live PSP stream supplied it.

## Offline proof

Run from the repository root. The file sink is the default and opens no network
connection:

```powershell
& "$env:WINDIR\SysWOW64\WindowsPowerShell\v1.0\powershell.exe" `
  -NoProfile -ExecutionPolicy Bypass `
  -File .\crio_psp_adapter\windows\reclaim-psp-adapter.ps1 `
  -Source Fixture `
  -FixturePath .\crio_psp_adapter\fixtures\engineering-poc.example.json `
  -Sink File -OutputPath "$env:TEMP\reclaim-poc.ndjson" -MaxFrames 1
```

## Direct TCP `GET` discovery

The supplied Socket Test VI establishes a second, distinct source seam: the cRIO
listens on `<CRIO_SOURCE_IP>:9070`, and a Windows client sends exactly the three ASCII
bytes `GET`. `capture-crio-tcp-get.ps1` performs one fail-closed evidence capture.
It never connects to the gateway at `<WINDOWS10_GATEWAY_IP>:9070`, never parses unknown bytes
as telemetry, and refuses to overwrite an existing capture.

Run this only during a controls-approved window in which a second client cannot
disturb the existing LabVIEW acquisition:

```powershell
& "$env:WINDIR\SysWOW64\WindowsPowerShell\v1.0\powershell.exe" `
  -NoProfile -ExecutionPolicy Bypass `
  -File .\crio_psp_adapter\windows\capture-crio-tcp-get.ps1 `
  -OutputPath .\crio-9070-response.bin
```

The probe sends `474554` (`GET`), waits up to the VI-aligned 25 seconds for the
first byte, captures at most 8192 bytes, stops on peer close or a bounded idle
interval, and reports the response length and SHA-256. A relay
must not be enabled until a captured response proves its framing, field syntax,
types, units, validity semantics, and snapshot behavior.

`capture_crio_tcp_proxy.py` is a separate diagnostic experiment for observing the
known-working desktop VI without consuming its socket. It listens only on
`127.0.0.1:19070`, forwards bytes unchanged to `<CRIO_SOURCE_IP>:9070`, and records
only cRIO-to-VI bytes with a timestamped chunk index. Local socket tests pass, but
the 2026-08-23 live VI/cRIO attempt did not establish a usable proxied stream or
capture data. Do not install or treat the proxy as a live source.

## Supervised one-frame live proof

This opens read-only NI-PSP subscriptions and sends one LF-delimited frame to
the Windows 10 desktop live gateway. It does not deploy or run a cRIO VI:

```powershell
& "$env:WINDIR\SysWOW64\WindowsPowerShell\v1.0\powershell.exe" `
  -NoProfile -ExecutionPolicy Bypass `
  -File .\crio_psp_adapter\windows\reclaim-psp-adapter.ps1 `
  -Source Psp -Sink Tcp -MaxFrames 1
```

## Foreground continuous engineering POC

The observed sustainable POC cadence is three seconds per frame:

```powershell
& "$env:WINDIR\SysWOW64\WindowsPowerShell\v1.0\powershell.exe" `
  -NoProfile -ExecutionPolicy Bypass `
  -File .\crio_psp_adapter\windows\reclaim-psp-adapter.ps1 `
  -Source Psp -Sink Tcp -CadenceMs 3000 -MaxFrames 0
```

This is a foreground proof only. It is not installed for startup, does not yet
provide production reconnect supervision, and does not establish the full
channel, state, chamber, cycle, timestamp, validity, or conversion contract.

The code defaults remain an 8192-byte maximum line, three-second cadence,
5-second freshness, and 2-second maximum locally observed snapshot skew. They
are POC parameters, not final controls approval. Do not enable the adapter as a
startup task until the separate deployment gate.
