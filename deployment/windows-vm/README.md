# Windows VM retained operator scripts

> **Current-route warning — 2026-08-24:** Convene internal routing now owns
> source-to-engine delivery and computed-state return. The direct public-engine,
> Cloudflare quick-tunnel, and file-state-bridge workflows below are retained for
> audit/recovery history and are not the current deployment procedure. Start at
> `deployment/CURRENT_CONVENE_ROUTED_SYSTEM_HANDOFF.md`.

These scripts are the credential-safe PowerShell workflows exercised during the
2026-08-18/19 `reclaim-engine-2` integration. Run them from elevated Windows
PowerShell 5.1 unless a script explicitly says otherwise. Review the source and
capture redacted output before using them on another VM.

| Script | Purpose | Mutates state? |
|---|---|---|
| `Deploy-ConveneVariableBindings.ps1` | Validates the protected scalar handoff against the environment-local ID manifest, then posts type-preserved values to exact Convene variable IDs | Yes: Convene variable values only |
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

# Validate all IDs, source fields, and scalar types without transmitting values.
.\deployment\windows-vm\Deploy-ConveneVariableBindings.ps1 -WhatIf

# Publish using the installed, token-bearing C:\ConveneAgent\agent.ps1 by default.
.\deployment\windows-vm\Deploy-ConveneVariableBindings.ps1

# Alternatively, use a separately protected token file; the token is never printed.
.\deployment\windows-vm\Deploy-ConveneVariableBindings.ps1 `
  -AgentTokenFile 'C:\secure\convene-agent-token.txt'
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

It is not a generic first-install script. The superseded clean-install runbooks
are preserved under
`Past_Deprecated/deployment/retired-2026-08-24-convene-routing/`.

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
- Do not expose production port `8078` or start a competing direct telemetry
  route; Convene's approved internal route owns engine ingress.
- Rehearsal ports `8177`–`8181` must never be routed into production or bound as
  live mission state.
- All predictive commands remain advisory and must not acquire hardware authority.
