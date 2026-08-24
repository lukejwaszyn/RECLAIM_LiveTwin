# Competition-eve MacBook integration plan

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

**Date:** 2026-08-23
**Event:** 2026-08-24
**Objective:** deliver an advisory, evidence-backed demonstration through the
authoritative MacBook scenario host and one production Windows VM engine.

## Ownership

| Lane | Owns |
|---|---|
| MacBook/scenario host | exact SHA, macOS network, protected config, queue, foreground lifecycle, `launchd`, raw gateway |
| Lab/controls | cRIO identity, producer, maps, safety, rollback, same-time evidence |
| Windows VM | engine service, durable identity, Cloudflare, state bridge, `sim_` |
| Joint | bounded scenario, correlation, stale expiry, go/no-go record |

## Critical path

1. Freeze one SHA and preserve the current dirty/untracked evidence.
2. Reserve/confirm `<WINDOWS10_GATEWAY_IP>` and `<CRIO_SOURCE_IP>`; prove OT route isolation.
3. Build the MacBook venv, protected config/state, and run all tests plus bench replay.
4. Foreground-test listener/status, clean shutdown, restart, and queue persistence.
5. Repair the VM run-adoption/`timestamp_stale` problem.
6. Run a bounded nominal synthetic stream through MacBook → VM → raw gateway/`sim_`.
7. Prove DATA NOT LIVE after the stream stops.
8. Install/reboot-test the LaunchAgent.
9. If controls gates close, run one real frame and a five-minute engineering shadow.

## Demonstration decision

Use the real cRIO only if every applicable source and live gate passes. Otherwise
use the bounded nominal synthetic scenario through the same MacBook scenario host and
production VM. Label the source prominently as synthetic and retain run/source/
sequence evidence. Do not substitute the former Windows gateway.

## Rehearsal set

- nominal: primary demonstration;
- power outage: verify lifecycle suspension/resume without batch reset;
- lunar: show environment-specific advisory behavior;
- loss of data: prove freshness expiry and DATA NOT LIVE.

Run one sender at a time. Never run a scenario while the real cRIO is connected
to the gateway listener. Never expose rehearsal ports as production state.

## Evidence packet

Retain the repository SHA, macOS/Python versions, addresses/interface, config
hash, listener bindings, test results, queue/counter deltas, engine run/source/
sequence, state-bridge health, raw gateway/`sim_` screenshots, stale-expiry timestamp,
source label, deviations, and rollback command. Never retain tokens.
