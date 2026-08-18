# Windows VM Convene State Bridge — Operator Runbook

**Scope:** repository-owned bridge on the Windows predictive-engine VM only
**Target machine registration:** `reclaim-engine-2`
**Installation status:** not performed by repository implementation

This service reads authenticated `GET http://127.0.0.1:8078/state`, validates the
`reclaim.state.v1` live-data contract, and atomically replaces
`C:\ConveneAgent\sim_vars.json`. The existing Convene agent remains the heartbeat
transport. The bridge does not call `/ingest`, consume `/command`, or connect to a
telemetry producer or control system.

## Safety contract and publication lease

Every successful live payload includes `bridge_valid_until`, normally five seconds
after `bridge_observed_at`. Convene must compare its own current UTC clock to this
deadline. This is required because a persistent Windows sharing violation can stop
the bridge from replacing the last complete file.

The operator view's single effective predicate is:

```text
DATA IS LIVE only when
  data_live == true
  AND current_utc <= bridge_valid_until
  AND mode == "live"
  AND ingest_status == "accepted"
  AND state_age_ms <= freshness_limit_ms
otherwise DATA NOT LIVE
```

In `sim` prefix mode, use the corresponding `sim_` names. Do not treat
`data_live` alone as sufficient. If Convene cannot evaluate its own current time
against `bridge_valid_until`, do not claim fail-closed acceptance and do not promote
the binding to an operator view.

## Files and identities

Default bridge layout:

```text
C:\ProgramData\RECLAIM\convene-bridge\
  app\
  config\bridge.yaml
  secrets\read-token.txt
  state\bridge.lock
  state\health.json
  logs\bridge.log
  service\reclaim-state-bridge.exe
  service\reclaim-state-bridge.xml
  venv\
```

The installer defaults to `NT AUTHORITY\LocalService`. Final service identity and
local policy remain a VM-acceptance decision. The installer requires the actual
existing Convene agent identity so it can grant that identity read-only access to
`sim_vars.json`; it never guesses the identity.

## Prerequisites and preflight

Use an elevated PowerShell session only after repository review authorizes VM
installation.

1. Record `git rev-parse HEAD` for the reviewed bridge source and the exact deployed
   engine revision. These become `bridge_source_sha` and `engine_source_sha`;
   abbreviated or placeholder SHAs are rejected.
2. Confirm supported Python 3.11–3.13 is installed.
3. Select an operator-approved WinSW 3.x release. Obtain it from the official WinSW
   release channel, verify the publisher/release provenance, calculate
   `Get-FileHash -Algorithm SHA256`, and record the version and checksum in the
   deployment evidence. No WinSW executable is committed here.
4. Discover and record existing files, services, tasks, identities, and ACLs:

   ```powershell
   Get-ChildItem C:\ConveneAgent -Force
   Get-CimInstance Win32_Service | Where-Object { $_.Name -match 'Convene|RECLAIM' }
   Get-ScheduledTask | Where-Object { $_.TaskName -match 'Convene|RECLAIM' }
   Get-Acl C:\ConveneAgent
   if (Test-Path C:\ConveneAgent\sim_vars.json) { Get-Acl C:\ConveneAgent\sim_vars.json }
   ```

5. Stop if another process writes `sim_vars.json`, if the intended source is not
   loopback, or if the engine's `/state` read is not bearer-authenticated.
6. Verify the engine still has its required external Cloudflare `/ingest` route.
   Do not change or test that route with this bridge.

Never paste a live token into a command line, transcript, ticket, or repository.

## Local repository proof

From the repository root:

```powershell
$env:UV_CACHE_DIR = Join-Path $env:TEMP 'reclaim-uv-cache'
uv run --frozen pytest -q convene_bridge/tests
uv run --frozen pytest -q cloud_engine/tests pi_gateway/tests
```

The integration tests bind only a fake `127.0.0.1` server and make no external
connections.

## Installation checkpoint

First run discovery without mutation:

```powershell
convene_bridge\windows\install-state-bridge.ps1 `
  -RepositoryRoot C:\path\to\RECLAIM_LiveTwin `
  -WinSWPath C:\staging\WinSW-x64.exe `
  -WinSWSha256 '<APPROVED_SHA256>' `
  -ConveneAgentIdentity '<DISCOVERED_AGENT_IDENTITY>' `
  -WhatIf
```

Review every discovered service, task, file, and ACL. The installer stops if its
install directory or service exists without its ownership marker. On approval, run
the same command without `-WhatIf`. It creates the service but does not start it and
does not request or print a credential.

The script creates a local virtual environment and installs exactly
`PyYAML==6.0.3`. If the VM has no approved Python package source, pre-stage that
wheel from the locked environment and configure pip to use the approved offline
source before running the installer.

Edit the non-secret configuration:

```text
C:\ProgramData\RECLAIM\convene-bridge\config\bridge.yaml
```

Required review points:

- source is exactly `http://127.0.0.1:8078/state`;
- `allow_non_loopback_state_url` remains `false`;
- `bridge_source_sha` is the exact reviewed bridge SHA and `engine_source_sha` is
  the exact deployed engine SHA;
- `freshness_limit_ms` is `15000` unless a reviewed decision changes it;
- `lease_duration_ms` remains longer than poll interval plus request timeout;
- prefix starts as `passthrough`; and
- output remains the existing VM agent's `C:\ConveneAgent\sim_vars.json`.

Place only the read token into `secrets\read-token.txt` using a secure local method,
then re-check that only Administrators, SYSTEM, and the service identity can read it.
The ingest token and Convene token never belong in this file.

Start and inspect:

```powershell
Start-Service RECLAIMStateBridge
Get-Service RECLAIMStateBridge
Get-Content C:\ProgramData\RECLAIM\convene-bridge\logs\bridge.log -Tail 50
Get-Content C:\ProgramData\RECLAIM\convene-bridge\state\health.json
```

Logs contain identity/sequence/status information but no token or full state dump.

## Acceptance sequence

1. Confirm startup publishes `data_live=false` before the first valid poll.
2. Confirm valid synthetic live state advances run/source/sequence and produces
   `data_live=true` with a future `bridge_valid_until`.
3. Stop telemetry and prove the view becomes `DATA NOT LIVE` within the approved
   freshness window.
4. Hold an exclusive lock that forces replacement beyond the retry interval. Prove
   the local health record reports `write_failed` and the Convene view becomes
   `DATA NOT LIVE` when the last published lease expires.
5. Exercise invalid authentication, malformed/non-object state, engine restart, and
   bridge restart.
6. Add a harmless canary scalar and observe whether Convene adds `sim_`. Retain
   `passthrough` if it does; otherwise change to `sim`, restart, and prove exactly one
   prefix. Record the result.
7. Confirm the existing Convene agent still owns its heartbeat and that no other
   device, task, machine registration, `/ingest` route, or command path changed.

## Upgrade

Stop the bridge, retain `config`, `secrets`, `state`, and logs, run the guarded
installer against the reviewed source, revalidate configuration and ACLs, and start
the service. Re-run the startup, live, stale, write-lock/lease, and prefix gates.

## Rollback

```powershell
convene_bridge\windows\uninstall-state-bridge.ps1 -ArchiveSimVars -WhatIf
convene_bridge\windows\uninstall-state-bridge.ps1 -ArchiveSimVars
```

The rollback removes only the owned bridge service, application copy, WinSW files,
and virtual environment. By default it preserves diagnostic bridge data and always
preserves the existing Convene task and original `sim_vars.json`. Use
`-PurgeBridgeData` only after explicitly deciding that bridge configuration,
credential file, state, and logs may be irrecoverably removed.
