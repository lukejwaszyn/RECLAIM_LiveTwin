# Past / Deprecated — archived material

This folder holds RECLAIM Live Twin documents that are **historical, superseded,
or spent** and are **not** current work plans. Nothing here is deleted — it is
relocated so the active `deployment/` set stays clean and unambiguous. Every file
is findable by name here; living docs that referenced these were updated to point
at their new location.

**Archived:** 2026-08-23, on branch `desktop/edge-gateway`, as part of the repo
resort requested alongside the cRIO cutover/acceptance handoff. Basis for each
move is the repository's own stage/status banners (`deployment/README.md`) plus
the cRIO source decision that replaced the PSP-subscriber path with the direct
existing-record → TCP seam (`deployment/CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md`).

## What moved and why

### `deployment/` — superseded or spent

| File (was `deployment/…`) | Why archived |
|---|---|
| `START_HERE.md` | Stage-0 staging kickoff pointer. Its own banner marks it HISTORICAL; superseded by `HANDOFF.md`. |
| `ClaudeCode_Staging_Prompts.md` | Stage-0 staging session prompt pack. Executed; record only. |
| `ClaudeCode_Gateway_Reconciliation_Prompts.md` | Stage-0.5 Pi→Windows-laptop naming reconciliation. Executed; not a live plan. |
| `SSH_Tailscale_ClaudeCode_Setup.md` | Access-setup notes; SSH parts superseded by the outbound-only model. |
| `ClaudeCode_Backend_Remediation_Prompt.md` | Spent one-time prompt for the RT-03/RT-05 backend session (implemented; see `CODE_REVIEW.md`/`FIXES.md`). |
| `NewChat_Cloud_Pipeline_Convene_Fix_Prompt.md` | Spent one-time session prompt (backend/cloud/Convene fix; implemented). |
| `NewChat_Windows_VM_Predictive_Engine_Integration_Prompt.md` | Spent one-time VM-engine integration prompt (engine deployed). |
| `NewChat_Windows_VM_Convene_State_Bridge_Prompt.md` | Spent one-time state-bridge implementation prompt (bridge implemented). |
| `NewChat_cRIO_Telemetry_Link_Architecture_Prompt.md` | Spent one-time cRIO producer-seam design prompt (design produced). |
| `NewChat_Windows_PSP_Telemetry_Adapter_Prompt.md` | Spent one-time PSP-adapter prompt; PSP path superseded for production source. |
| `CRIO_TELEMETRY_LINK_HANDOFF.md` | Historical source-selection handoff; its PSP selection is superseded by the direct-record seam. |
| `CRIO_PSP_ADAPTER_DEVELOPMENT_PLAN.md` | Historical PSP diagnostic-adapter development plan; not the selected production seam. |

### `root-level/` — stray archive

| File (was repo root) | Why archived |
|---|---|
| `RECLAIM_LiveTwin 2.zip` | Stray build/handoff archive snapshot. Git-ignored (`*.zip`) — never tracked; relocated to keep the working tree clean. |

## Deliberately NOT archived (kept in place — still cited by living docs)

These read as "historical" at a glance but remain the actively-referenced source
of record; moving them would break the living reference graph, so they stayed:

- `CODE_REVIEW.md`, `FIXES.md` — the current hardening record cited by the root
  `README.md`, `deployment/HANDOFF.md`, `deployment/GATEWAY_GO_LIVE.md`, and the
  lifecycle memo.
- `GATEWAY_DEPLOYMENT_RED_TEAM_ASSESSMENT.md`,
  `PREDICTIVE_ENGINE_RED_TEAM_ASSESSMENT.md` — the finding sources (GW-01..10 /
  RT-01..08) cited by the current remediation and CI/CD docs under `docs/` and
  `deployment/`.

To archive these too, move them here and update every referencing link (~18
references across 8 living docs) in the same change.

## Related PSP material still live

`crio_psp_adapter/` (code) and `deployment/CRIO_PSP_LIVE_ADAPTER_HANDOFF.md` are
**kept** because the PSP subscriber remains the documented controls fallback if
the direct cRIO producer is not delivered. It is no longer the primary seam.
