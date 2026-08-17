<!-- generated-by: gsd-doc-writer -->
# New-Chat Prompt — Backend Fixes, Cloud Pipeline, and Convene Reintegration

Copy everything inside the block below into a new Codex or Claude Code chat with
the repository open at its root.

```text
You are taking ownership of the next RECLAIM Live Twin implementation session as
the senior Python backend, cloud/DevOps, controls-integration, test, and safety-
domain engineer. Work from the repository root. Do not merely produce another
plan: inspect the current state, implement the repository-owned fixes, verify
them, and leave a precise operator handoff for external Convene and endpoint work.

Primary outcome:

1. Make the RT-03/RT-05 backend integrity safety gate green without weakening it.
2. Prove the cloud-native CI and isolated REST pipeline on the exact fixed commit.
3. Prepare and validate the repository-owned side of Convene reintegration using
   synthetic/rehearsal data first.
4. Preserve a reliable nominal demo plus power-outage and lunar-surface practice
   scenarios within the existing 72-hour strategy.

Read these documents completely before editing, in this order:

1. deployment/HANDOFF.md
2. deployment/README.md
3. deployment/RECLAIM_BACKEND_REMEDIATION_HANDOFF.md
4. deployment/ClaudeCode_Backend_Remediation_Prompt.md
5. deployment/RECLAIM_72_HOUR_DEMO_DEPLOYMENT_STRATEGY.md
6. docs/RECLAIM_RT03_RT05_Test_Baseline.md
7. docs/RECLAIM_Integrated_Remediation_Architecture.md
8. docs/RECLAIM_Predictive_Engine_RedTeam_Remediation.md
9. deployment/CI_CD_RED_TEAM_INTEGRATION_HANDOFF.md
10. deployment/CI_CD_ARCHITECTURE.md
11. deployment/VM_ENGINE_HANDOFF.md
12. deployment/VM_ENGINE_RUNBOOK.md
13. deployment/GATEWAY_GO_LIVE.md
14. docs/RECLAIM_Live_Telemetry_Architecture.md
15. convene/RECLAIM_Convene_Live_Binding.md
16. deployment/CONVENE_GW_MAPPING.md

Then inspect the implementation and tests directly, including:

- cloud_engine/push_ingest_dual.py
- cloud_engine/reclaim_predictive_engine/
- cloud_engine/tests/
- cloud_engine/deploy/
- pi_gateway/reclaim_edge/
- pi_gateway/tests/
- .github/workflows/
- convene/

Start by reporting:

- branch, HEAD, worktree status, remotes, and latest CI state;
- exact current RT-03/RT-05 counts and inherited baseline counts;
- what is implemented versus documentary or operator-owned;
- the transaction mechanism you intend to use;
- the current cloud and Convene endpoint/namespace boundary;
- any unrelated user changes you must preserve.

Proceed in the following gated order.

PHASE 1 — Backend integrity fixes

Implement deployment/RECLAIM_BACKEND_REMEDIATION_HANDOFF.md faithfully.

- Validate and normalize the complete envelope and consumed telemetry before any
  model, chamber, clock, counter, output, advisory/command, or identity mutation.
- Reject prohibited coercions, containers, dimensions, booleans, and non-finite
  values with the stable final codes asserted by the tests.
- Treat PL, MT, time/counters, events, combined service state, advisory/command
  representation, and run/sequence durability as one accepted-frame transaction.
- A failure after PL and before MT must preserve the complete pre-frame aggregate.
- Retry after a partial fault must equal a clean one-pass engine.
- Durable identity failure must be observable, retryable, and never accepted.
- Do not invent physical min/max thresholds.
- Do not weaken, delete, skip, xfail, or move the RT tests out of the required CI
  gate. Add focused coverage where it strengthens the same contract.
- Keep candidate publishers side-effect-free and runtime authority advisory-only.

Default ownership is cloud_engine/push_ingest_dual.py and the existing integrity
test. Open predictive-engine modules only if a minimal candidate/snapshot API is
truly necessary, and explain that boundary in the handback.

Do not begin Phase 2 until all named integrity tests and the complete cloud-engine
and gateway test suites pass locally.

PHASE 2 — Cloud-native pipeline proof

Use the locked environment and the existing GitHub-hosted workflows. Do not hide
known failures or add production credentials to CI.

- Run repository hygiene, compilation, gateway tests, inherited cloud tests, and
  the RT-03/RT-05 gate locally.
- Confirm CI exercises Python 3.11 and 3.13 against the locked dependency graph.
- Push a focused feature branch and obtain a CI run for the exact commit.
- Confirm the isolated synthetic REST services expose /health, /manifest, /state,
  and /history for:
    * nominal + earth_lab on 127.0.0.1:8177;
    * power_outage + earth_lab on 127.0.0.1:8178;
    * nominal + lunar_surface on 127.0.0.1:8179.
- Verify that production dual ingest remains a different process and port, and
  that synthetic services cannot post to or become the production /ingest route.
- Do not dispatch or promote a production release merely because CI is green.
- Do not install a general GitHub Actions runner on the VM or gateway.

If release-candidate generation is already implemented, verify its manifest,
digest, test evidence, and no-production-access properties. If it is incomplete,
record the exact gap; do not broaden this session into an unsafe deployment-system
rewrite unless it is required for the demo and can be completed without external
production mutation.

PHASE 3 — Repository-owned Convene reintegration

Reconcile the actual cloud /state and gateway /latest schemas against:

- convene/RECLAIM_Convene_Live_Binding.md
- deployment/CONVENE_GW_MAPPING.md

Implement the safe local work that can be proven from this repository:

- Add or update automated contract tests that prove required /state fields,
  provenance, mode, accepted status, source timestamp, sequence, active chamber,
  chamber-local state, freshness, and advisory fields are present and typed as
  documented.
- Verify the gateway audit mapping preserves the raw gw_ view while the cloud
  sim_ view carries normalized engine state. Account for documented unit
  conversions and shared microwave-power attribution.
- Produce a machine-readable binding/check artifact only if its format is proven
  by an existing Convene export, schema, or repository example. Never invent a
  proprietary import format. If no format is available, produce a field-level
  gap report and an operator checklist instead.
- Define separate rehearsal identities/namespaces for nominal, outage, and lunar
  practice. They must never write live sim_ fields.
- Preserve exactly one future live sim_ publisher and a separate read-only gw_
  audit machine.
- Ensure the UI/binding contract shows DATA NOT LIVE when mode is not live,
  ingest status is not accepted, or freshness exceeds the approved limit.
- Treat /command and cmd_* values as advisory representations only. Do not connect
  them to the gateway, PLC, cRIO, Convene actions, or actuators.
- Keep the .stp visualization a read-only consumer. Do not claim a geometry
  binding is complete without the actual model and element mapping evidence.

Do not mutate the external Convene account, connected machines, live sim_
namespace, credentials, tunnel, agent privileges, or operator view without the
user's explicit confirmation in this new chat. When an external step is reached,
stop at a concise checkpoint containing the exact operator action, expected
result, evidence to capture, and rollback.

PHASE 4 — Demo and endpoint handback

Re-run the nominal scenario twice and the two practice scenarios once each. Keep
the local REST output as the zero-dependency fallback if Convene is unavailable.
Update only documentation made inaccurate by the implementation.

Required local verification from the repository root:

uv sync --locked --all-extras --dev --python 3.13
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q cloud_engine pi_gateway scripts tools
cd cloud_engine
PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -m pytest tests/test_rt03_rt05_integrity.py -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -m pytest tests -q -p no:cacheprovider
cd ../pi_gateway
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -m pytest tests -q -p no:cacheprovider
cd ..
python3 scripts/check_repository_hygiene.py

Git and delivery rules:

- Preserve unrelated changes and never use destructive reset/checkout commands.
- Work on a focused feature branch rather than committing fixes directly to main.
- Make atomic commits by concern: backend integrity, Convene contract/tests, and
  necessary documentation.
- Inspect every diff and scan changed files for secrets before pushing.
- Open a draft pull request if the GitHub connection supports it; do not merge it.
- Do not deploy, connect hardware, change firewall/TLS/tokens, publish rehearsal
  data to live namespaces, or enable active authority without explicit approval.

Finish with a handback that includes:

1. transaction mechanism and files changed;
2. exact before/after test counts;
3. CI run and draft-PR links;
4. cloud REST proof for all three scenarios;
5. Convene contract coverage added and remaining operator-owned steps;
6. every unresolved endpoint or credential gate;
7. commit SHAs and rollback guidance;
8. explicit statements covering deployment status, external Convene mutations,
   hardware connection, and command authority.

Begin now by reading the listed files and inspecting the repository. Do not stop
after summarizing; continue through all safe repository-owned implementation and
verification work, pausing only for an external or production mutation that needs
new authority.
```
