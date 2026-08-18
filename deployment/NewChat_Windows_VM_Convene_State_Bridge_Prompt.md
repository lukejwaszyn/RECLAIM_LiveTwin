# Fresh-Agent Prompt — Implement the Windows VM Convene State Bridge

Copy the prompt below into a fresh AI coding session rooted at the
`RECLAIM_LiveTwin` repository.

---

You are implementing the repository-owned state-publication bridge for the RECLAIM
predictive-engine Windows VM.

Repository:

```text
lukejwaszyn/RECLAIM_LiveTwin
```

Primary design contract:

```text
deployment/WINDOWS_VM_CONVENE_STATE_BRIDGE_HANDOFF.md
```

Read these files before changing anything, in this order:

1. `deployment/WINDOWS_VM_CONVENE_STATE_BRIDGE_HANDOFF.md`
2. `cloud_engine/push_ingest_dual.py`
3. `cloud_engine/tests/test_convene_binding_contract.py`
4. `deployment/CONVENE_REINTEGRATION_HANDOFF.md`
5. `convene/RECLAIM_Convene_Live_Binding.md`
6. `docs/RECLAIM_Live_Telemetry_Architecture.md`
7. `pyproject.toml`
8. `uv.lock`

## Critical context

- The target is a cloud-hosted Windows Server 2025 VM in Kubernetes-managed
  infrastructure, registered in Convene as `reclaim-engine-2`. Kubernetes is the
  outer hosting boundary; guest work uses PowerShell, Windows services, NTFS, and
  ACLs, not Linux container commands.
- The Convene agent installed during clean-VM bootstrap independently includes
  `C:\ConveneAgent\sim_vars.json` in that VM's heartbeat.
- Other Convene agents run on entirely separate devices. They may use mechanically
  similar heartbeat behavior, but they do not overlap with this VM implementation.
- Do not inspect, reuse, modify, coordinate, or make assumptions about those other
  agents. This task changes only the Windows VM state-bridge infrastructure in the
  repository.
- The installed VM Convene agent is the transport consumer of `sim_vars.json`; it is
  not the `/state` bridge and must not be rewritten.
- The VM predictive engine continues to receive authenticated `POST /ingest`
  telemetry through its Cloudflare Tunnel. Preserve that required engine route; the
  new bridge neither implements nor replaces it.
- The engine's `/command` surface is preserved as deferred future scope. This bridge
  must not consume or relay it. Future command integration requires a separate
  design and safety gate.
- The bridge is read-only and local: it may call only authenticated `GET /state` and
  must not connect directly to a telemetry producer, cRIO, LabVIEW, PLC, HMI control,
  or actuator.
- No VM mutation is authorized during this implementation task. Build and test the
  repository deliverables locally. Installation is a later, explicit checkpoint.
- Never copy, print, commit, or request a live Convene agent token, engine read token,
  ingest token, hostname, or machine configuration secret.
- The approved implementation decision adds a short `bridge_valid_until` lease.
  Convene must compare its own UTC clock to that deadline so a bridge crash or
  persistent file-sharing violation expires the last complete live payload.

## Objective

Implement a small, dependable Python bridge that runs as an independent Windows
service, polls authenticated `GET http://127.0.0.1:8078/state`, validates the
`reclaim.state.v1` contract and freshness, enriches it with bridge/deployment
metadata, and atomically replaces `C:\ConveneAgent\sim_vars.json` for the existing
VM Convene agent to read.

The implementation must be suitable for a reproducible demonstration deployment in
the next few days. Production-grade orchestration, fleet management, automated
promotion, and elaborate secret infrastructure are out of scope.

## Required behavior

1. Poll loopback `/state` at a configurable interval, default one second.
2. Use a read bearer credential from a separate ACL-protected secret source.
3. Refuse a missing credential in live mode.
4. Refuse non-loopback source URLs unless a separately named override is explicitly
   configured.
5. Validate HTTP success, JSON-object shape, `reclaim.state.v1`, required identity
   fields, scalar types, mode, ingest status, and `state_age_ms`.
6. Default the freshness limit to 15000 ms.
7. Enforce monotone sequence only within the same `(run_id, source_id)` identity.
   Accept and log a valid identity transition.
8. Preserve state scalar types and do not fabricate process values.
9. Add `data_live`, `bridge_status`, `bridge_observed_at`, `bridge_error_code`,
   `bridge_instance_id`, `environment`, `engine_source_sha`, and
   `freshness_limit_ms`, plus the approved `bridge_valid_until` lease.
10. Publish `data_live=true` only when every live-data invariant passes.
11. On startup, timeout, unauthorized response, invalid state, stale state, sequence
    regression, or write failure, publish or retain a current fail-closed status with
    `data_live=false` and a stable non-secret error code.
12. Support explicit `passthrough` and `sim` prefix modes. Default to passthrough,
    reject unknown modes, and never double-prefix `sim_` keys.
13. Write to a temporary file in the destination directory, flush/close it, then use
    `os.replace`. Retry Windows sharing violations for a short bounded interval and
    leave the last complete destination intact if replacement ultimately fails.
14. Enforce one bridge writer with a Windows-compatible singleton mechanism.
15. Produce useful rotating logs without tokens or full payload dumps.
16. Preserve the engine's existing external `/ingest` route, but do not call or write
    `/ingest` from the bridge. Do not consume `/command` in this phase, and never
    connect the bridge to hardware or another Convene machine.

## Repository outputs

Create:

- the `convene_bridge` implementation package;
- an example non-secret configuration;
- focused unit and loopback integration tests;
- a WinSW service XML template;
- idempotent PowerShell install and uninstall/rollback scripts;
- an operator runbook for configuration, installation, verification, logging, and
  rollback; and
- any minimal dependency/lock updates required by the implementation.

Do not commit WinSW or another third-party executable. Treat it as a verified
external prerequisite and document the expected location/version/checksum workflow.

The installer must:

- discover existing files, services, tasks, and ACLs before changing anything;
- preserve unexpected deployments and stop for operator direction;
- create directories under `C:\ProgramData\RECLAIM\convene-bridge`;
- configure a dedicated least-privilege service identity where practical;
- apply explicit ACLs to configuration, secrets, logs, and
  `C:\ConveneAgent\sim_vars.json`;
- never modify or unregister the installed VM Convene agent task; and
- support rollback of only the bridge artifacts it owns.

## Tests and proof

At minimum, test:

- valid live state;
- authentication failure and connection failure;
- malformed/non-object JSON;
- missing/wrong schema and invalid identity types;
- freshness boundary below, at, and above 15000 ms;
- mode and ingest-status failures;
- same-run sequence progression and regression;
- valid run/source transition;
- both prefix modes and double-prefix prevention;
- atomic replacement under a concurrent reader;
- simulated sharing violation and bounded retry;
- singleton writer enforcement;
- fail-closed startup, failure, recovery, and subsequent stale transition; and
- static proof that the bridge HTTP client performs only authenticated `GET /state`
  and has no command, ingest-write, or hardware-control call path.

Use a fake local HTTP server. Tests must not contact the real VM, engine, Convene,
Cloudflare, gateway, or Internet.

Run the repository's locked environment and the relevant existing cloud/gateway
tests after the focused bridge tests. Preserve unrelated user changes and do not
weaken existing invariants.

## Working method

1. Review the handoff critically against the repository and report contradictions
   before implementation.
2. Inspect the current branch and worktree; do not overwrite unrelated changes.
3. Propose a short implementation plan tied to the handoff requirements.
4. Implement in small, reviewable units.
5. Run focused tests, then proportionate repository regression tests.
6. Review the diff for secrets, unsafe remote access, command paths, and accidental
   coupling to other Convene machines.
7. Report files changed, test results, unresolved decisions, and the exact commit SHA
   tested. Do not claim VM or Convene acceptance without performing the later
   operator checkpoint.

## Decisions intentionally deferred to VM acceptance

- Whether Convene publishes `simVars` keys literally or automatically adds `sim_`.
  Implement both modes and default to passthrough; prove the final choice with a
  harmless canary field.
- The final Windows service identity and local policy details.
- The exact WinSW binary/version approved for the VM.
- Live credentials and VM-specific paths that differ from the documented defaults.

Stop and report rather than improvising if the repository contract conflicts with
the handoff, if safe atomic Windows replacement cannot be proven, or if any proposed
path could give the twin hardware-control authority.

---
