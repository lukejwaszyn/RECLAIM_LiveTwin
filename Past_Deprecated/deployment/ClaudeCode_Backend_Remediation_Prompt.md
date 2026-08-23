<!-- generated-by: gsd-doc-writer -->
# Claude Code Prompt — Integrate the RECLAIM Backend Integrity Fixes

Copy the prompt below into a fresh implementation session rooted at the private
RECLAIM repository.

```text
You are the senior Python backend, controls-integration, test, and safety-domain
engineer for RECLAIM Live Twin. Work in the repository root. Your task is to
implement the RT-03 and inference-safe RT-05 backend fixes, make the named safety
gate green, preserve all existing behavior, and hand back reviewable evidence.

Read these files completely before editing:

1. deployment/RECLAIM_BACKEND_REMEDIATION_HANDOFF.md
2. docs/RECLAIM_RT03_RT05_Test_Baseline.md
3. docs/RECLAIM_Integrated_Remediation_Architecture.md
4. docs/RECLAIM_Predictive_Engine_RedTeam_Remediation.md
5. deployment/CI_CD_RED_TEAM_INTEGRATION_HANDOFF.md
6. cloud_engine/push_ingest_dual.py
7. cloud_engine/tests/test_rt03_rt05_integrity.py
8. cloud_engine/tests/test_live_ingest_contract.py
9. every predictive-engine module whose mutable state is inventoried by the RT
   tests, before deciding how candidate state will be isolated

First report the current branch/status, current RT-03/RT-05 result, the accepted-
frame state aggregate, and your proposed transaction boundary. Then implement;
do not stop merely to restate the documents. Preserve unrelated user changes.

Implementation requirements:

- Validate and normalize the complete envelope and consumed telemetry before any
  chamber, model, clock, counter, service, command/advisory, or identity mutation.
- Reject bools, numeric strings, containers, wrong dimensions, and non-finite
  values with the exact final codes asserted by the baseline.
- Do not invent physical min/max thresholds; those remain blocked on controls and
  thermal-owner approval.
- Execute PL, MT, combined output, service state, command/advisory state, time,
  counters, events, gaps, and identity as one isolated candidate transaction.
- On any candidate failure, return retryable internal_error and preserve the
  entire pre-frame accepted-state aggregate.
- A retry after the injected PL-then-MT fault must equal a clean one-pass engine.
- Make durable identity persistence raise/propagate failure. Never report accepted
  when durable identity did not commit.
- Commit/swap visible state only after candidate evaluation and required durability
  succeed. Keep candidate publishers side-effect-free.
- Keep the runtime advisory-only. Do not create, connect, or strengthen any active
  command path.

Default file ownership is cloud_engine/push_ingest_dual.py and the existing RT
test file only. Do not weaken or delete baseline assertions. If a predictive-
engine snapshot/clone API is truly required, explain why a transaction aggregate
or isolated candidates in push_ingest_dual.py cannot meet the invariant, declare
the additional files, and keep the change minimal.

Verification, from the repository root:

uv sync --locked --all-extras --dev --python 3.13
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q cloud_engine
cd cloud_engine
PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -m pytest tests/test_rt03_rt05_integrity.py -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -m pytest tests -q -p no:cacheprovider
cd ../pi_gateway
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -m pytest tests -q -p no:cacheprovider

Before committing, inspect the complete diff, run the repository hygiene check,
and scan changed files for credentials/private keys. Make one focused commit on a
feature branch and push it. Do not deploy, dispatch a release candidate, change
GitHub protection settings, connect hardware, alter firewall/tunnel/Convene
configuration, or post data to any live endpoint.

Finish with: mechanism chosen, files changed, exact test counts, CI result/link,
commit SHA, remaining risks, and an explicit no-deployment/no-authority-change
statement.
```
