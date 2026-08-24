# RECLAIM deployment documentation

## Start here

[`CURRENT_CONVENE_ROUTED_SYSTEM_HANDOFF.md`](CURRENT_CONVENE_ROUTED_SYSTEM_HANDOFF.md)
is the sole active handoff and architecture pickup point.

The current route is:

```text
Windows live gateway or MacBook scenario gateway
  -> Convene source machine
  -> Convene internal route
  -> cloud stochastic engine
  -> Convene sim_* result and visualization
```

Do not configure a separate gateway-to-cloud HTTPS/cloudflared telemetry route.
The Windows 10 desktop owns real cRIO data. The MacBook is scenario-only and
publishes fabricated/replayed telemetry to its Convene machine.

## Active supporting records

- `LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md` — host ownership.
- `DEPLOYMENT_TOPOLOGY.md` — current topology.
- `NEW_GATEWAY_SCENARIO_DEPLOYMENT.md` and `pi_gateway/macos/README.md` — MacBook
  scenario setup and one-command controller.
- `CRIO_SOURCE_RECORD_SIGNED_MAPS.md`, `CRIO_SOURCE_RECORD_DECISION_RECORD.md`,
  and `CRIO_SOURCE_RECORD_RUNBOOK.md` — live cRIO source contract and evidence.
- `CONVENE_GW_MAPPING.md` — prior binding inventory; naming and routing decisions
  in the current handoff take precedence.
- `windows-vm/README.md` — index of retained VM scripts. Direct-tunnel scripts
  are legacy and not part of the current route.

## Archived handoffs

All older handoffs, handovers, and session prompts were moved to
`Past_Deprecated/deployment/retired-2026-08-24-convene-routing/`. They are kept
for traceability only and must not be used as operating instructions.
