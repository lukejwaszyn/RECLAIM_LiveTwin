# RECLAIM Live Twin — MacBook scenario host handoff

**Date:** 2026-08-23
**Competition:** 2026-08-24
**Authoritative edge decision:** Windows 10 is live; MacBook is scenario-only
**Overall live status:** engineering shadow / **NO-GO** pending acceptance

## Current architecture

```text
cRIO / LabVIEW -> Windows 10 desktop live gateway -> production live-data path
MacBook local scenarios -> Convene exact-name scenario variables
Convene -> VM scenario pipe (owned outside this MacBook workstream)
VM -> Convene sim_*
```

The Windows 10 desktop remains the live-data client/gateway. The MacBook must
not connect to or listen for live cRIO data and must not send directly to the
cloud engine.

## Proven state

- MacBook TCP request/response and raw capture against the emulated endpoint
  `192.168.12.114:9070` succeeded.
- The observed MacBook address was `192.168.12.33` on active `en0`; it is not
  evidence of a reserved, isolated cRIO-facing interface.
- Raw responses were test strings, not telemetry.
- Earlier bounded synthetic tests proved the gateway software's two outbound
  paths and VM/Convene processing on the former Windows host.
- The selected real-source design remains the source-built cRIO record emitted
  through a bounded, lower-priority, latest-wins JSON+LF TCP producer.

## Immediate blockers

1. Verify the Windows 10 desktop live-data interface separately.
2. Accept the MacBook loopback scenario runtime under `launchd`.
3. Repair the VM live run-adoption failure that causes delayed
   `timestamp_stale` final rejections.
4. Complete the cRIO source/build, mapping, timing, safety, and rollback gates.
5. Correlate a bounded scenario across MacBook, Convene, VM, and `sim_`.

## Read and execute in this order

1. `DEPLOYMENT_TOPOLOGY.md`
2. `MACBOOK_GATEWAY_AND_CRIO_VI_HANDOFF.md`
3. `MACBOOK_GATEWAY_HOST_AUDIT.md`
4. `../pi_gateway/macos/README.md`
5. `NEW_GATEWAY_SCENARIO_DEPLOYMENT.md`
6. `CRIO_GATEWAY_CUTOVER_RUNSHEET.md`
7. `CLOUD_ENGINE_LIVE_SCENARIO_HANDOFF_PROMPT.md`
8. `GATEWAY_GO_LIVE.md`
9. `CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md`

## Competition-safe fallback

If the real cRIO contract cannot pass in time, run a clearly labeled bounded
synthetic scenario through the real MacBook scenario host and production VM. Retain
provenance and freshness evidence. Do not claim it is physical telemetry, do not
guess a raw protocol, and do not revive the MacBook scenario host as a second path.

## Permanent boundaries

- Only local scenario tools may connect to the MacBook listener.
- One production VM engine owns `sim_*`.
- MacBook publishes only exact-name gateway variables.
- Port `9080` remains loopback-only.
- Tokens remain out of Git, chat, output, and screenshots.
- No command, return, setpoint, cRIO deployment, or actuation path is authorized.
