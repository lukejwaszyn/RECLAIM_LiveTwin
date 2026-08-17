<!-- generated-by: gsd-doc-writer -->
# RECLAIM Backend Integrity Remediation Handoff

**Date:** 2026-08-16

**Status:** Implementation-ready; production deployment remains blocked

**Primary scope:** RT-03 accepted-frame transactionality and RT-05 structural telemetry validation
**Authority:** Advisory only; this work does not create an actuator or command path

## Outcome required

Convert the existing failing RT-03/RT-05 regression baseline into a green,
reviewable backend change while preserving every currently passing gateway and
cloud-engine test. The completed slice must make one ingest frame behave as a
single transaction across validation, both chamber object graphs, combined
publication, command/advisory state, and durable run/sequence identity.

This is the backend prerequisite for any live nominal demonstration. It is not
permission to deploy, connect the cRIO, publish rehearsal data into the live
Convene namespace, or enable active command authority.

## Verified starting point

| Item | Current evidence |
|---|---|
| Repository | Private GitHub repository; local `main` tracks `origin/main` |
| CI baseline | Repository hygiene and Python 3.11/3.13 baseline jobs are active |
| Existing behavior | Gateway tests and inherited cloud-engine tests pass |
| Safety gate | `cloud_engine/tests/test_rt03_rt05_integrity.py`: 35 tests, 32 currently fail and 3 pass |
| RT-03 | A failure after PL and before MT leaves partial estimator/time state; persistence errors can be reported accepted |
| RT-05 | Invalid non-finite, boolean, string, container, dimension, timestamp, and sequence inputs can mutate state or receive unstable dispositions |
| Deployment | Live data remains NO-GO; VM endpoint/tokens and cRIO/gateway network gates are not closed |

The detailed evidence and expected failure taxonomy are in
[`../docs/RECLAIM_RT03_RT05_Test_Baseline.md`](../docs/RECLAIM_RT03_RT05_Test_Baseline.md).

## Owned implementation slice

Default edit ownership:

- `cloud_engine/push_ingest_dual.py`
- `cloud_engine/tests/test_rt03_rt05_integrity.py`, only to add coverage or fix a
  demonstrable test defect—never to weaken the stated invariants
- narrowly related documentation if the implementation changes an operator or
  interface contract

Do not edit predictive-engine internals merely to make rollback convenient. If
an explicit snapshot, clone, or candidate-state API is necessary, first document
why `copy.deepcopy`, isolated engine candidates, or a transaction aggregate in
`push_ingest_dual.py` is insufficient. Then name each newly owned module before
changing it.

## Required design invariants

### RT-05: validate and normalize before mutation

The full envelope and every telemetry scalar consumed by either chamber must be
validated before `_last_ts`, clocks, counters, estimators, lifecycle state,
publisher/service state, command/advisory state, or identity can change.

- Accept numeric scalars only where the contract expects numeric telemetry.
- Reject `bool`, numeric strings, mappings, lists/arrays, wrong sensor-bank
  dimensions, `NaN`, and positive/negative infinity.
- Reject malformed timestamps as final `timestamp_invalid`.
- Reject boolean, string, fractional, non-finite, or container sequences as final
  `sequence_invalid`.
- Reject chamber telemetry shape/type/finiteness failures as final
  `telemetry_invalid`.
- Preserve the existing production envelope, mode, freshness, state, and active
  chamber checks.
- Do not add physical min/max thresholds. Approved units, operating envelopes,
  reflected-power semantics, and sensor-disagreement limits remain owner
  decisions.

### RT-03: one accepted-frame transaction

Candidate evaluation must cover the complete accepted-frame aggregate:

- PL and MT `ChamberEngine` clocks and full `PredictiveEngine` object graphs;
- dual-engine `_last_ts`, `t`, `count`, event/gap calculations, and output record;
- `TwinStateService` latest state, history, cycle, and manifest-related state;
- computed advisory/command record;
- active/retired run identity, sequence high-water values, and gap count;
- durable identity bytes.

An exception at any point before final commit must return retryable
`internal_error`, leave that aggregate equivalent to its pre-frame state, and
permit a retry that is equivalent to one clean pass.

Durable identity persistence must be observable: `IngestIdentityStore.save()`
cannot swallow a write/replace failure. A frame is not accepted until the
durable identity transition succeeds. Visible service state and live object
references must not switch before that success.

### Commit order

The implementation may choose the exact mechanism, but it must preserve this
logical order:

1. validate and normalize the complete frame;
2. decide run/sequence disposition without mutating accepted state;
3. evaluate both chamber paths and combined output against isolated candidates;
4. persist candidate run/sequence identity atomically;
5. publish/swap the complete in-memory candidate aggregate;
6. return `accepted`.

If step 4 succeeds and step 5 can still raise, the design must explicitly prove
how durable and in-memory state remain recoverable and consistent. Prefer a
commit boundary that makes the post-persistence in-memory swap deterministic and
non-throwing.

## Explicit non-goals

- No physical safety thresholds or calibration claims.
- No change from advisory to active authority.
- No cRIO, gateway, Cloudflare, Convene, VM service, firewall, or token mutation.
- No synthetic data posted to `/ingest` or any production route.
- No broad dependency, deployment, or predictive-model refactor.
- No implementation of ADR-002 live lunar counterfactual projection.

## Verification gates

Run from the repository root with the locked environment:

```sh
uv sync --locked --all-extras --dev --python 3.13
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q cloud_engine
cd cloud_engine
PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -m pytest tests/test_rt03_rt05_integrity.py -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -m pytest tests -q -p no:cacheprovider
cd ../pi_gateway
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -m pytest tests -q -p no:cacheprovider
```

Required result:

- all 35 RT-03/RT-05 cases pass unchanged in meaning;
- the full cloud-engine suite passes;
- the gateway suite passes;
- both CI baseline matrix jobs and the named RT-03/RT-05 safety gate are green;
- no repository hygiene or secret-scan failure;
- the diff contains no deployment or authority change.

## Review checklist

- [ ] Invalid frames cannot enter either chamber step.
- [ ] A fault after PL and as MT begins preserves the pre-frame aggregate.
- [ ] Retry after an injected partial fault equals a clean one-pass engine.
- [ ] Identity persistence failure is retryable and cannot be reported accepted.
- [ ] Stable final rejection codes match the baseline contract.
- [ ] No test invariant was diluted and no physical threshold was invented.
- [ ] No external publisher or command side effect occurs during candidate work.
- [ ] Implementation comments explain the commit boundary and recovery behavior.
- [ ] A focused commit and CI link are included in the handback.

## Handback package

Return one concise implementation record containing:

1. files changed and the selected transaction mechanism;
2. before/after RT test counts;
3. complete local verification results and CI run link;
4. remaining risks or assumptions;
5. source commit SHA;
6. an explicit statement that no deployment, live endpoint, or command-authority
   change was performed.
