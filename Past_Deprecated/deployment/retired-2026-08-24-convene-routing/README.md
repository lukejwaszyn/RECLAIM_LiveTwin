# Retired handoffs: Convene routing consolidation

**Archived:** 2026-08-24

**Status:** historical evidence only; not operating instructions

These documents were removed from the active `deployment/` directory when
Convene became the common telemetry routing plane. They contain overlapping or
superseded assumptions about MacBook live acquisition, direct gateway-to-cloud
HTTPS/cloudflared transport, separate Convene bridges, or old session pickup
points.

The sole current pickup document is
`deployment/CURRENT_CONVENE_ROUTED_SYSTEM_HANDOFF.md`.

## Manifest

- `CI_CD_RED_TEAM_INTEGRATION_HANDOFF.md`
- `CLOUD_ENGINE_LIVE_SCENARIO_HANDOFF_PROMPT.md`
- `CONVENE_FIRESTORE_INDEX_HANDOVER.md`
- `CONVENE_REINTEGRATION_HANDOFF.md`
- `CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md`
- `CRIO_DESKTOP_DEPLOY_SESSION_PROMPT.md`
- `CRIO_INTEGRATION_ACCEPTANCE_HANDOFF.md`
- `CRIO_INTEGRATION_ACCEPTANCE_HANDOFF_2.md`
- `CRIO_INTERFACING_TROUBLESHOOTING_HANDOFF.md`
- `CRIO_LABVIEW_PRODUCER_HANDOFF.md`
- `CRIO_PSP_LIVE_ADAPTER_HANDOFF.md`
- `ENGINE_SIDE_UPDATES_HANDOFF.md`
- `HANDOFF.md`
- `LUKE_VM_LOCAL_HANDOFF.md`
- `MACBOOK_GATEWAY_AND_CRIO_VI_HANDOFF.md`
- `NewChat_cRIO_Source_Record_TCP_Implementation_Prompt.md`
- `RECLAIM_BACKEND_REMEDIATION_HANDOFF.md`
- `THREE_ENDPOINT_HANDOFF.md`
- `VM_ENGINE_HANDOFF.md`
- `WINDOWS_VM_CONVENE_STATE_BRIDGE_HANDOFF.md`

The former `docs/RECLAIM_Integrated_Handoff_Evaluation.md` is preserved under
`Past_Deprecated/docs/retired-2026-08-24-convene-routing/` for the same reason.

## Additional superseded operating material

The following active-looking documents were also archived because they instruct
operators to use the former direct gateway/Cloudflare/state-bridge path or record
a superseded host decision:

- `CI_CD_ARCHITECTURE.md`
- `CONVENE_MISSION_OPERATIONS_RECAP.md`
- `CRIO_GATEWAY_CUTOVER_RUNSHEET.md`
- `GATEWAY_GO_LIVE.md`
- `LIFECYCLE_RESTART_AUDIT_RECORD.md`
- `MACBOOK_GATEWAY_DOCUMENT_AUDIT.md`
- `MACBOOK_GATEWAY_HOST_AUDIT.md`
- `NEXT_SESSION_CD_REHEARSAL_PLAN.md`
- `RECLAIM_72_HOUR_DEMO_DEPLOYMENT_STRATEGY.md`
- `REHEARSAL_CONVENE_PUSH.md`
- `THREE_PATH_CLOUDFLARE_ACCEPTANCE.md`
- `VM_ENGINE_RUNBOOK.md`
- `VM_ENGINE_SESSION_BRIEF.md`
- `WINDOWS_VM_CONVENE_STATE_BRIDGE_RUNBOOK.md`

`docs/RECLAIM_Remote_Gateway_Preflight.md` was archived with the older handoff
evaluation because its acceptance sequence also depended on the superseded
direct route.
