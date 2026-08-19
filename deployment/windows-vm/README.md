# Windows VM Proven Operator Scripts

These scripts are the credential-safe PowerShell workflows exercised during the
2026-08-18/19 `reclaim-engine-2` integration. Run them from elevated Windows
PowerShell 5.1 unless a script explicitly says otherwise. Review the source and
capture redacted output before using them on another VM.

| Script | Purpose | Mutates state? |
|---|---|---|
| `Register-ConveneAgentTask.ps1` | Validates the VM-specific installed Convene agent, locks its ACL, and registers the headless SYSTEM startup task | Yes |
| `Deploy-ProvenScalarStateRelease.ps1` | Transactionally deploys exact engine SHA `726804b...`, updates bridge provenance, and rolls the engine back on startup failure | Yes |
| `Test-EnginePublicAcceptance.ps1` | Runs the public 20-check harness, restarts the engine, and proves durable duplicate detection | Yes: telemetry + one engine restart |
| `Test-ConveneLiveExpiry.ps1` | Streams correlated frames, proves live publication, stops the source, and requires stale/lease expiry | Yes: telemetry only |
| `Get-ConvenePublicationDiagnostics.ps1` | Prints selected non-secret engine/bridge/task fields and log evidence | No |
| `recovery/Reregister-EngineService.ps1` | Rebuilds the engine WinSW SCM registration from a validated release | Recovery mutation |
| `recovery/Reregister-StateBridgeService.ps1` | Rebuilds the finalized bridge WinSW SCM registration without restarting the engine | Recovery mutation |

## Common invocations

Use the current approved HTTPS origin; quick-tunnel hostnames are ephemeral.

```powershell
.\deployment\windows-vm\Test-EnginePublicAcceptance.ps1 `
  -PublicUrl 'https://<approved-engine-origin>'

.\deployment\windows-vm\Test-ConveneLiveExpiry.ps1 `
  -PublicUrl 'https://<approved-engine-origin>'

.\deployment\windows-vm\Get-ConvenePublicationDiagnostics.ps1 `
  -ProofRun '<correlated-run-id>'
```

The acceptance scripts read the ACL-protected engine secret file locally, keep
credentials out of arguments and output, and clear in-memory credential variables
in `finally` blocks.

## Proven pinned deployment

`Deploy-ProvenScalarStateRelease.ps1` is intentionally evidence-specific. It
expects:

- engine SHA `726804b012279a0f3c675c4d9d3e76b16cf18d46` already staged with its
  locked `.venv` under `C:\ProgramData\RECLAIM\releases`;
- bridge SHA `1d7512346806d994cd95a1b485f4f500f650286d` already installed;
- WinSW net461 at `C:\ProgramData\RECLAIM\staging\WinSW-net461.exe` with SHA-256
  `91BCE26B4FA3A7534E7967C1804D7417737B7169014435E5B3B31924BF19F3EE`;
- healthy engine and bridge services before the transaction; and
- the existing protected engine state/credential and bridge credential files.

It is not a generic first-install script. Use `VM_ENGINE_RUNBOOK.md` and
`WINDOWS_VM_CONVENE_STATE_BRIDGE_RUNBOOK.md` for clean installation.

## Recovery note

The re-registration scripts address a WinSW failure observed when finalized XML
was modified after installation and restricted-account auto-refresh could not
reopen the SCM service. They preserve credentials and durable identity files.
They are not routine restart commands; use them only after retaining logs and
confirming the registered executable path is repository-owned.

## Security boundaries

- Never commit or print the Convene VM token, engine ingest token, or engine read
  token.
- The agent installer supplied by Convene is VM-specific and token-bearing; it is
  deliberately not in this repository.
- Production port `8078` remains loopback-only; cloudflared is the only external
  route.
- Rehearsal ports `8177`–`8179` must never be routed into production or bound as
  live mission state.
- All predictive commands remain advisory and must not acquire hardware authority.
