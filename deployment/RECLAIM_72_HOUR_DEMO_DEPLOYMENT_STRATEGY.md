<!-- generated-by: gsd-doc-writer -->
# RECLAIM 72-Hour Demo and Endpoint Deployment Strategy

**Date:** 2026-08-16

**Clock:** `T+0` is the moment this plan is accepted; demo-ready deadline is `T+72h`

**Commitment:** one guaranteed nominal synthetic demo plus two synthetic practice scenarios
**Live posture:** optional stretch path only; currently NO-GO

**Platform correction (2026-08-17):** the live cloud guest is Windows Server
2025 in Kubernetes-managed infrastructure and the edge gateway is a Windows 10
laptop. All VM guest work uses PowerShell, Windows services, NTFS paths, and
ACLs. There is no Linux or Raspberry Pi runtime in Track B.

## Decision

Run two tracks in parallel without coupling the guaranteed demo to unavailable
live infrastructure:

- **Track A — committed demo:** isolated synthetic services for nominal Earth-lab,
  power outage, and lunar-surface operation. No cRIO or live data is required.
- **Track B — live nominal stretch:** cRIO → gateway → cloud ingest → Convene,
  attempted only if every backend, network, credential, contract, and operational
  gate below is green by `T+48h`.

If Track B misses a gate, the demonstration remains Track A. Do not compress or
bypass a safety gate to preserve the live stretch goal.

## Demo success definition

At `T+72h`, the operator can start or select three clearly labeled, non-live
experiences and show `/health`, `/manifest`, `/state`, and `/history`:

| Demo | Engine selection | Purpose | Approximate wall time |
|---|---|---|---:|
| Nominal, primary | `nominal` + `earth_lab`, 6x | Full nominal narrative and stable advisory display | ~67 s/cycle |
| Power outage, practice | `power_outage` + `earth_lab`, 12x | Outage, thermal coast, and recovery behavior | ~75 s/cycle |
| Lunar operation, practice | `nominal` + `lunar_surface`, 6x | Synthetic environment contrast without live data | ~67 s/cycle |

The lunar practice is the existing synthetic environment model. It is **not**
the unimplemented live-anchored dual Earth/lunar counterfactual proposed by
ADR-002.

Success also requires:

- rehearsal labels/namespaces are unmistakable and never use live `sim_` bindings;
- no rehearsal service can reach the production ingest route;
- advisory output is shown as advisory, not as actuator authority;
- an operator run sheet, screenshots/records, known-issues note, and fallback are
  on the demo laptop;
- the nominal scenario completes twice consecutively during dress rehearsal.

## Endpoint map and readiness

| Hop / endpoint | Intended role | Track A | Track B gate |
|---|---|---|---|
| cRIO | Real LabVIEW source | Not used | Static IP/link, approved source contract, safe operating window |
| Gateway ingress `:9070` | Receive cRIO telemetry | Not used | Bound only to approved interface; firewall and single-source behavior verified |
| Gateway status `127.0.0.1:9080` | Local health/latest visibility | Optional display only | `/health` and `/latest` green; raw `/command` is not consumed or surfaced as actionable |
| Synthetic services `127.0.0.1:8177-8179` | Isolated scenario engines | Required | Never tunnel or route to production |
| Windows Server 2025 VM ingest `127.0.0.1:8078` | Production dual push engine | Not used | RT-03/RT-05 green, locked artifact, persistent Windows state path writable, advisory mode, maintenance gate |
| Cloudflare public route | Authenticated VM egress edge | Not used | Stable hostname, TLS, tokens, route-to-loopback, health and auth checks |
| Convene rehearsal namespace | Demo visualization | Preferred; local HTTP viewer is fallback | Distinct fields such as `rehearsal_nominal_*`, `rehearsal_outage_*`, and `rehearsal_lunar_*` |
| Convene live `sim_` namespace | One live publisher | Prohibited | Six contract gates, three-column V&V, single-writer cutover, owner GO |

The production `/command` representation remains advisory output. It must not be
wired to the gateway, PLC, cRIO, or an actuator for this demonstration.

## 72-hour critical path

### T+0 to T+6 — freeze the demo contract

1. Record the exact demo start time and name the demo operator plus backup.
2. Freeze the three scenario/environment/port assignments above.
3. Create a backend remediation feature branch and begin the accompanying prompt.
4. Start all three synthetic services locally and capture health/state evidence.
5. Decide whether Convene rehearsal binding can be completed without touching the
   live namespace; retain browser/curl output as the zero-dependency fallback.

**Gate A (`T+6`):** all three services start on loopback and produce state. If not,
repair Track A before working on live connectivity.

### T+6 to T+24 — close the backend safety gate

1. Implement the backend handoff in
   `RECLAIM_BACKEND_REMEDIATION_HANDOFF.md`.
2. Make all 35 RT-03/RT-05 tests pass without weakening their invariants.
3. Run full cloud and gateway suites, hygiene scan, and CI on Python 3.11/3.13.
4. Review the diff and record the commit and CI evidence.

**Gate B (`T+24`):** backend CI is green. A failure blocks Track B, but it does
not block the isolated synthetic Track A demo service.

### T+24 to T+36 — build the demo surface

1. Map the four read-only REST resources from each service to the selected demo
   surface.
2. Apply explicit rehearsal namespace and scenario badges at the publisher/UI;
   do not rename or reuse live variables.
3. Prepare one page or view per scenario; prevent cross-port mixing.
4. Write a five-minute operator narrative: system identity → health → manifest →
   current state → history → advisory interpretation.
5. Capture a local fallback package: commands, expected ports, and screenshots.

**Gate C (`T+36`):** each scenario is distinguishable at a glance and can be run
without external data or production credentials.

### T+36 to T+48 — endpoint preflight and optional shadow candidate

For Track B only, gather—not infer—the current state of cRIO addressing, gateway
configuration, VM Python/runtime, stable hostname, token provisioning, tunnel,
and Convene agent. Run read-only health/preflight checks first. A candidate VM
engine may be installed side-by-side only through the approved artifact/process;
it remains loopback, advisory, and disconnected from the live gateway route.

**Live decision gate (`T+48`):** Track B continues only if all live gates in the
next section have named owners, evidence, and green status. Otherwise declare the
demo synthetic and stop spending critical-path time on live integration.

### T+48 to T+64 — dress rehearsal

1. Run power-outage practice and lunar-operation practice once each.
2. Run the complete nominal operator script twice from a clean start.
3. Deliberately exercise the fallback: remove the visualization dependency and
   complete the narrative from local REST output.
4. Record launch time, endpoint health, scenario completion, UI/REST evidence,
   observed warnings, and recovery steps.
5. If Track B qualified, run one controlled live nominal rehearsal in the approved
   safe window while retaining Track A ready on the laptop.

**Gate D (`T+64`):** two consecutive nominal passes, one pass for each practice
scenario, and one successful fallback run.

### T+64 to T+72 — freeze and present

- Freeze code and configuration except for a documented P0 demo blocker.
- Export the tested commit SHA, commands, configs with secrets removed, evidence,
  contact/owner list, and known issues to the demo laptop.
- Stop unused services and verify only the intended scenario port is displayed.
- Thirty minutes before the demo, run health checks and a short nominal smoke test.
- If any live condition is ambiguous, switch to Track A before the audience joins.

## Synthetic service launch sheet

Run each command from `cloud_engine/` in a separate terminal. All hosts are
loopback and intentionally use non-production ports.

```sh
../.venv/bin/python -m reclaim_predictive_engine.service \
  --scenario nominal --env earth_lab --host 127.0.0.1 --port 8177 --speed 6

../.venv/bin/python -m reclaim_predictive_engine.service \
  --scenario power_outage --env earth_lab --host 127.0.0.1 --port 8178 --speed 12

../.venv/bin/python -m reclaim_predictive_engine.service \
  --scenario nominal --env lunar_surface --host 127.0.0.1 --port 8179 --speed 6
```

Read-only smoke checks:

```sh
curl --fail --silent http://127.0.0.1:8177/health
curl --fail --silent http://127.0.0.1:8177/manifest
curl --fail --silent http://127.0.0.1:8177/state
curl --fail --silent http://127.0.0.1:8177/history
```

Repeat for ports `8178` and `8179`. Never substitute the public tunnel hostname
or production port into these rehearsal commands.

## Track B live nominal gates

Every row must be green by `T+48h`; unknown equals NO-GO.

- [ ] RT-03/RT-05 named CI safety gate passes on the exact candidate commit.
- [ ] Baseline CI passes on supported Python versions and repository hygiene is green.
- [ ] Candidate is immutable/digest-bound with its locked environment and test evidence.
- [ ] VM service is loopback-only, advisory, uses a writable durable identity path,
      and passes local health plus authenticated ingest/read checks.
- [ ] Stable Cloudflare hostname, route, TLS, read token, and ingest token are
      provisioned without exposing credentials.
- [ ] cRIO/gateway static addressing and physical link are verified by their owners.
- [ ] Gateway live config passes preflight; queue/status behavior and strict cloud
      acknowledgment correlation are verified.
- [ ] The six telemetry contract gates and three-column V&V pass using `gw_` audit
      fields before the single live publisher binds `sim_` fields.
- [ ] Active chamber is `NONE`, power is independently verified removed, and the
      approved operational window is open for deploy/cutover.
- [ ] Exactly one live gateway and one live Convene publisher are selected.
- [ ] Rollback target, state compatibility, operator, and non-secret deployment
      receipt are ready.
- [ ] Independent hardware interlock remains outside this pipeline and unchanged.

## Operator demo script

1. State the banner: **synthetic rehearsal, advisory-only, no actuator authority**.
2. Show `/health` and identify scenario, environment, cycle, and endpoint port.
3. Show `/manifest` to establish the data contract.
4. Show `/state`; narrate measured/estimated state and advisory severity without
   describing the computed command fields as executed control.
5. Show `/history` to demonstrate temporal behavior.
6. For the nominal demo, complete one full cycle and summarize stable behavior.
7. For practice, point out outage/recovery behavior and lunar environmental
   contrast; do not claim either is live telemetry.
8. End with the boundary: active authority and live deployment remain separate,
   gated work unless the live checklist has an approved evidence record.

## Stop conditions and fallback

Immediately abandon the live stretch path and use Track A if the safety gate is
red, endpoint identity is uncertain, credentials are unavailable, multiple
writers appear, hardware state is not independently safe, or any rehearsal data
could enter a live namespace. If Convene is unavailable, use the local REST
surface and saved screenshots. If one practice scenario is unstable, preserve
the nominal demo and show the recorded practice evidence; do not patch production
during the final eight-hour freeze.

## Evidence record

For every rehearsal, record timestamp, commit SHA, scenario/environment, port,
cycle count, health result, start/stop operator, result, warnings, and artifact or
screenshot location. Redact tokens and never capture environment secret files.

<!-- VERIFY: Stable Cloudflare hostname, tokens, cRIO addressing, VM runtime state,
Convene rehearsal namespace, and live maintenance window require operator evidence;
the repository currently documents them as unprovisioned, incomplete, or future. -->
