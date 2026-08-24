# Cloud-engine VM: Convene-routed cutover

This directory contains only the current VM audit and acceptance entry points.
The former Cloudflare quick tunnel, `RECLAIMStateBridge`, `sim_vars.json`, direct
Convene variable publisher, and pinned-release deployment scripts are archived
under `Past_Deprecated/retired-2026-08-24-convene-direct-routing/`.

Run these from an elevated PowerShell session after logging onto the VM:

```powershell
Set-Location C:\path\to\RECLAIM_LiveTwin

.\deployment\windows-vm\Audit-ConveneRoutedEngine.ps1
.\deployment\windows-vm\Test-ConveneRoutedEngineContract.ps1
```

The audit is read-only. It records the deployed SHA, cleanliness, engine file
hash, service/listener inventory, loopback health, and every known obsolete
writer/tunnel signal without printing credentials. Resolve every blocker before
deployment.

The contract test first runs the repository-owned source tests. Endpoint mutation
is deliberately separate and requires all of the following:

```powershell
$env:RECLAIM_INGEST_TOKEN = '<existing ingest token>'
$env:RECLAIM_READ_TOKEN = '<existing read token>'
.\deployment\windows-vm\Test-ConveneRoutedEngineContract.ps1 -ExerciseEndpoint
```

`-ExerciseEndpoint` sends labeled harness telemetry to the loopback production
engine and therefore changes its current estimator/run state. Use it only during
the supervised cutover window after Convene input is paused.

Do not reinstall or start `RECLAIMStateBridge`, a quick tunnel, a second
`sim_*` publisher, or any scenario service on the VM. The engine's HTTP response
already carries the flat cloud-owned `sim_*` `variables` object for Convene.
