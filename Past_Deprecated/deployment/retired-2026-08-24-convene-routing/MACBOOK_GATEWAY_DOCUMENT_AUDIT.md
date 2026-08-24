# MacBook scenario host documentation audit

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

**Decision date:** 2026-08-23
**Scope:** every source-controlled/project Markdown document present during the
audit; generated cache content such as `.pytest_cache/` is excluded
**Authority:** superseded—the Windows 10 desktop is the live gateway; this MacBook is scenario-only

## Audit rules

- Operational gateway instructions were converted to macOS, the MacBook runtime layout, configurable OT addresses, and `launchd`.
- Windows Server 2025 VM, state-bridge, and VM Convene instructions remain Windows-specific.
- Historical Windows/Linux/Pi gateway records were preserved as evidence and marked non-operational.
- Documents with no gateway-platform claim were reviewed and left unchanged.
- The MacBook address observed on 2026-08-23 was `192.168.12.33` on active `en0`; it is not evidence of an isolated OT interface. The emulated endpoint `192.168.12.114` is not assumed to be the real cRIO.

## Reconciled active documents

- `FIXES.md`
- `README.md`
- `convene/RECLAIM_Convene_Live_Binding.md`
- `crio_psp_adapter/README.md`
- `crio_source_record/README.md`
- `deployment/CI_CD_ARCHITECTURE.md`
- `deployment/CI_CD_RED_TEAM_INTEGRATION_HANDOFF.md`
- `deployment/CONVENE_GW_MAPPING.md`
- `deployment/CONVENE_REINTEGRATION_HANDOFF.md`
- `deployment/CRIO_ACQUISITION_OPTIONS_TRADE_STUDY.md`
- `deployment/CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md`
- `deployment/CRIO_DESKTOP_DEPLOY_SESSION_PROMPT.md`
- `deployment/CRIO_GATE3_PRODUCER_REVIEW_CHECKLIST.md`
- `deployment/CRIO_GATEWAY_CUTOVER_RUNSHEET.md`
- `deployment/CRIO_INTEGRATION_ACCEPTANCE_HANDOFF.md`
- `deployment/CRIO_INTEGRATION_ACCEPTANCE_HANDOFF_2.md`
- `deployment/CRIO_INTERFACING_TROUBLESHOOTING_HANDOFF.md`
- `deployment/CRIO_LABVIEW_PRODUCER_HANDOFF.md`
- `deployment/CRIO_PSP_LIVE_ADAPTER_HANDOFF.md`
- `deployment/CRIO_SOURCE_RECORD_DECISION_RECORD.md`
- `deployment/CRIO_TELEMETRY_SOCKET_SETUP.md`
- `deployment/CRIO_TELEMETRY_WRITE_PATH_AUDIT.md`
- `deployment/DEPLOYMENT_TOPOLOGY.md`
- `deployment/GATEWAY_GO_LIVE.md`
- `deployment/HANDOFF.md`
- `deployment/LIFECYCLE_RESTART_AUDIT_RECORD.md`
- `deployment/LUKE_VM_LOCAL_HANDOFF.md`
- `deployment/MACBOOK_GATEWAY_AND_CRIO_VI_HANDOFF.md`
- `deployment/MACBOOK_GATEWAY_HOST_AUDIT.md`
- `deployment/MACBOOK_GATEWAY_DOCUMENT_AUDIT.md`
- `deployment/NEW_GATEWAY_SCENARIO_DEPLOYMENT.md`
- `deployment/NEXT_SESSION_CD_REHEARSAL_PLAN.md`
- `deployment/NewChat_cRIO_Source_Record_TCP_Implementation_Prompt.md`
- `deployment/README.md`
- `deployment/RECLAIM_72_HOUR_DEMO_DEPLOYMENT_STRATEGY.md`
- `deployment/REHEARSAL_CONVENE_PUSH.md`
- `deployment/THREE_ENDPOINT_HANDOFF.md`
- `deployment/VM_ENGINE_RUNBOOK.md`
- `deployment/VM_ENGINE_SESSION_BRIEF.md`
- `docs/RECLAIM_Integrated_Handoff_Evaluation.md`
- `docs/RECLAIM_Integrated_Remediation_Architecture.md`
- `docs/RECLAIM_Live_Telemetry_Architecture.md`
- `docs/RECLAIM_RT03_RT05_Test_Baseline.md`
- `docs/RECLAIM_Remote_Gateway_Preflight.md`
- `pi_gateway/macos/README.md`
- `pi_gateway/windows/README.md`

## Reviewed; no gateway-platform edit required

- `.github/pull_request_template.md`
- `CODE_REVIEW.md`
- `GATEWAY_DEPLOYMENT_RED_TEAM_ASSESSMENT.md`
- `PREDICTIVE_ENGINE_RED_TEAM_ASSESSMENT.md`
- `deployment/CLOUD_ENGINE_LIVE_SCENARIO_HANDOFF_PROMPT.md`
- `deployment/CONVENE_FIRESTORE_INDEX_HANDOVER.md`
- `deployment/CONVENE_MISSION_OPERATIONS_RECAP.md`
- `deployment/CRIO_SOURCE_RECORD_RUNBOOK.md`
- `deployment/CRIO_SOURCE_RECORD_SIGNED_MAPS.md`
- `deployment/ENGINE_SIDE_UPDATES_HANDOFF.md`
- `deployment/RECLAIM_BACKEND_REMEDIATION_HANDOFF.md`
- `deployment/VM_ENGINE_HANDOFF.md`
- `deployment/WINDOWS_VM_CONVENE_STATE_BRIDGE_HANDOFF.md`
- `deployment/WINDOWS_VM_CONVENE_STATE_BRIDGE_RUNBOOK.md`
- `deployment/windows-vm/README.md`
- `docs/RECLAIM_ADR-001_Frequency_Steering.md`
- `docs/RECLAIM_ADR-002_Lunar_Counterfactual_Projection.md`
- `docs/RECLAIM_CI_CD_IMPLEMENTATION_BASELINE.md`
- `docs/RECLAIM_Predictive_Engine_Lifecycle_Memo.md`
- `docs/RECLAIM_Predictive_Engine_RedTeam_Remediation.md`

## Archived documents marked historical/non-operational

- `Past_Deprecated/README.md`
- `Past_Deprecated/deployment/CRIO_PSP_ADAPTER_DEVELOPMENT_PLAN.md`
- `Past_Deprecated/deployment/CRIO_TELEMETRY_LINK_HANDOFF.md`
- `Past_Deprecated/deployment/ClaudeCode_Backend_Remediation_Prompt.md`
- `Past_Deprecated/deployment/ClaudeCode_Gateway_Reconciliation_Prompts.md`
- `Past_Deprecated/deployment/ClaudeCode_Staging_Prompts.md`
- `Past_Deprecated/deployment/NewChat_Cloud_Pipeline_Convene_Fix_Prompt.md`
- `Past_Deprecated/deployment/NewChat_Windows_PSP_Telemetry_Adapter_Prompt.md`
- `Past_Deprecated/deployment/NewChat_Windows_VM_Convene_State_Bridge_Prompt.md`
- `Past_Deprecated/deployment/NewChat_Windows_VM_Predictive_Engine_Integration_Prompt.md`
- `Past_Deprecated/deployment/NewChat_cRIO_Telemetry_Link_Architecture_Prompt.md`
- `Past_Deprecated/deployment/SSH_Tailscale_ClaudeCode_Setup.md`
- `Past_Deprecated/deployment/START_HERE.md`

## Verification target

Repository-wide checks must find no active claim that the production edge gateway is Windows, no active gateway dependency on a Windows Scheduled Task or `C:\\RECLAIM`, and no operational use of `192.168.1.1` as the gateway. Windows wording may remain only where it clearly describes the Windows Server 2025 VM or a labeled historical record.
