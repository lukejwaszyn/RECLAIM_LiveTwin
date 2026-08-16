# RECLAIM RT-03 / RT-05 Failing Regression Baseline

**Session date:** 2026-08-16  
**Repository path:** `/Users/lukewaszyn/RECLAIM_LiveTwin`  
**Scope:** test-first evidence for RT-03 and the type/dimension/finiteness portion of RT-05 only  
**Authority:** advisory only; no command/control connection or active authority was created

## Outcome

The requested executable failing baseline is established.

- The untouched existing cloud-engine suite passes: **21 passed, 0 failed, 0 skipped**.
- The new regression file collects and runs: **35 collected; 32 failed, 3 passed, 0 skipped**.
- The combined cloud-engine suite runs: **56 collected; 32 failed, 24 passed, 0 skipped**.
- The 32 new failures are product-behavior assertions, not import, setup, or collection failures.
- RT-03 is reproduced after the plastics chamber has completed a real step and the injected fault begins the metals step.
- RT-05 is reproduced across non-finite values, prohibited coercions, scalar/container mismatches, sensor-bank shape, power, pressure, timestamp, and sequence fields.
- No runtime fix was implemented. The failures are the intended result of this session.

The workspace is **not a Git worktree**. `git rev-parse --is-inside-work-tree` returned:

```text
fatal: not a git repository (or any of the parent directories): .git
```

No Git repository was initialized and no Git configuration was changed.

## Environment and dependency record

Tests ran in a disposable local virtual environment at
`/private/tmp/reclaim_rt03_rt05_venv`. It was created from the local Homebrew
Python with `--system-site-packages`; only pytest and its direct runner
dependencies were installed into the virtual environment. It did not touch a
production machine.

| Component | Observed value |
|---|---|
| Platform | `macOS-26.5.2-arm64-arm-64bit-Mach-O` |
| Python | `3.14.7` |
| Python executable | `/private/tmp/reclaim_rt03_rt05_venv/bin/python` |
| pytest | `9.1.1` |
| NumPy | `2.4.2` |
| SciPy | `1.17.1` |
| scikit-learn | **Unavailable** (`ModuleNotFoundError: No module named 'sklearn'`) |
| pytest plugin observed | `anyio-4.14.2` |

Scikit-learn's absence did not skip or prevent collection. `gp.py` has an
explicit no-scikit fallback, and `ChamberEngine` constructs both production
predictive engines with `use_gp=False`. The complete suite collected and ran.
The absence is recorded rather than misreported as a version or a passing GP
configuration.

This is a runnable diagnostic environment, **not an approved locked development
environment**. The repository provides lower-bound requirement files but no lock.
An approved lock cannot be created without selecting the supported Python
versions, target OS/ABI set, and lock/wheel tooling. Those are unresolved owner
decisions, so this session did not choose them implicitly or add dependency files.

Repository bytecode and pytest cache writes were disabled for verification with
`PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider`. No repository `.pytest_cache`
was created. The pre-existing `cloud_engine/tests/__pycache__` directory was not
modified intentionally.

## Files inspected

Required documents read in full:

1. `docs/RECLAIM_Integrated_Handoff_Evaluation.md`
2. `docs/RECLAIM_Integrated_Remediation_Architecture.md`
3. `PREDICTIVE_ENGINE_RED_TEAM_ASSESSMENT.md`
4. `docs/RECLAIM_Predictive_Engine_RedTeam_Remediation.md`
5. `docs/RECLAIM_Live_Telemetry_Architecture.md`
6. `deployment/CI_CD_RED_TEAM_INTEGRATION_HANDOFF.md`

Required runtime and state-owning sources inspected:

- `cloud_engine/push_ingest_dual.py`
- `cloud_engine/reclaim_predictive_engine/engine.py`
- `cloud_engine/reclaim_predictive_engine/estimator.py`
- `cloud_engine/reclaim_predictive_engine/lifecycle.py`
- `cloud_engine/reclaim_predictive_engine/anomaly.py`
- `cloud_engine/reclaim_predictive_engine/metrics.py`
- `cloud_engine/reclaim_predictive_engine/plant.py`
- `cloud_engine/reclaim_predictive_engine/forecaster.py`
- `cloud_engine/reclaim_predictive_engine/thread.py`
- `cloud_engine/reclaim_predictive_engine/service.py`

Additional supporting sources inspected to resolve normalization, configuration,
GP availability, and dependencies:

- `cloud_engine/labview_map.py`
- `cloud_engine/reclaim_predictive_engine/config.py`
- `cloud_engine/reclaim_predictive_engine/gp.py`
- `cloud_engine/reclaim_predictive_engine/__init__.py`
- `cloud_engine/reclaim_predictive_engine/requirements.txt`
- `cloud_engine/deploy/requirements-cloud.txt`
- all existing tests under `cloud_engine/tests/`:
  `test_lifecycle_continuous.py` and `test_live_ingest_contract.py`

## Files changed

- Created `cloud_engine/tests/test_rt03_rt05_integrity.py`.
- Created `docs/RECLAIM_RT03_RT05_Test_Baseline.md`.

No production/runtime Python file was modified.

## Complete accepted-frame transaction-state inventory

The test snapshot is recursive and structural. It walks complete nested objects,
arrays, deques, dictionaries, lists, dataclass/config objects, and future object
attributes. It does not use a shallow dictionary or a few selected arrays. Locks
and executable callables are represented only by stable markers. Identity-file
location is not logical state; its exact durable bytes are included separately.

`last_ingest` is mutable and participates in an attempt, but it is deliberately
outside pre/post rollback equivalence: a rejected attempt must update the reported
disposition. Its required status/code/finality are asserted separately. Everything
that represents accepted model, publication, command, time, event, or identity
state is in the equivalence snapshot.

### Dual ingest aggregate

- `DualPushEngine.count`, `t`, and `_last_ts`.
- `production`, `max_frame_age_s`, and the accepted state enumeration are included
  to detect unintended future mutation even though they are presently stable.
- Both `ChamberEngine.chamber` identities and both `ChamberEngine.t` clocks.
- `DualPushEngine.command`, including chamber, mode, setpoint, and safe-state flag.
- `DualPushEngine.last_ingest` as disposition-only state, asserted semantically.
- The adapter-normalized combined record and frame events through service state.

### Each `PredictiveEngine` object graph (PL and MT independently)

- UKF posterior `x` and covariance `P`.
- UKF process/measurement arrays and all sigma-point configuration/weights.
- Cached predicted sigma points `_sigmas_f`.
- Last innovation `_last_innov`, innovation covariance `_last_S`, `nis`, and `nees`.
- Adaptive process-noise `q_scale`, bounds/rates, and `_niswin` contents/max length.
- Forward-model live charge mass `_mf_mass` and the physical parameter graph used by
  capacity, reaction, ignition, melt, and mass-flow behavior.
- Lifecycle `phase`, `batch_present`, `last_cycle_id`, `_suspended`,
  `cycle_elapsed_s`, and `active_heating_s`.
- NIS monitor history, consecutive-breach counter, gate, and window.
- CUSUM high/low accumulators and detector configuration.
- Seal-monitor anchor `t0` and monitor configuration.
- Measurement/runaway window `_meas_win`.
- GP feature/residual windows `_gp_X` and `_gp_r`; deployed chamber engines have
  `gp=None` because `use_gp=False`. If GP is later enabled, the recursive snapshot
  will include `fitted`, `prior_var`, and the estimator object state.
- Performance accumulator `_t0`, `_t_prev`, `_p_prev`, `energy_j`, `peak_temp`, and
  `elapsed`, plus its configured mass/yield record.
- Step counter `_k`, `last_forecast`, `_last_op_state`, and `last_advisory`.
- Forecaster/model object state and advisory object state.
- Publisher `_manifest_sent`, manifest, retained `frames`, and sink identity. The
  current chamber publisher uses a no-op sink and therefore has no external side
  effect. A future real publisher must be staged outside candidate evaluation.

### Combined publication and service state

- `TwinStateService._latest` complete output record, including command fields,
  provenance, output values, `last_event`, event count, and accepted status.
- `TwinStateService._history` contents, order, and maximum length.
- Service `cycle` and manifest state.
- State/publisher output is compared with a fixed engine clock so `ts_engine` is
  deterministic in retry-versus-clean equivalence.

### Run, sequence, and durability identity

- `active_run_id`.
- Bounded retired-run list.
- Per-`(run_id, source_id)` sequence high-water mapping.
- Cumulative gap count.
- Exact durable identity-file bytes, including absence versus presence.
- Identity path is excluded only because separate test instances use separate
  temporary files; their durable contents must be identical.

## Test-to-requirement mapping and observed result

| Test ID | Required invariant | Observed current result | Intended defect reproduced? |
|---|---|---|---|
| `test_RT_03_failure_after_PL_before_MT_preserves_dual_engine_state` | A retryable fault after PL completes and as MT begins preserves the entire pre-frame aggregate. | `rejected/internal_error/final=false`, but `count 0→1`, `t 0→1`, `_last_ts` set, PL `_k 0→1`, lifecycle latched/advanced, measurement window/CUSUM/forecast/advisory/UKF caches/mass state changed. | **Yes — RT-03.** |
| `test_RT_03_retry_after_partial_failure_equals_clean_one_pass` | Retrying the identical frame after removing the fault equals a fresh one-pass engine across model, timing, output, events, command, and identity. | Retried engine has `count=2`, `t=1.05`; clean engine has `count=1`, `t=1.0`. The retry re-steps PL and processes MT at the compressed `0.05 s` delta; MT lifecycle, windows, NIS/CUSUM, performance timing, state, and covariance differ from clean. | **Yes — RT-03 retry corruption.** |
| `test_RT_03_identity_persist_failure_is_not_reported_accepted` | Durable identity failure must not report accepted and must preserve visible/in-memory transaction state. | Injected `os.replace` failure is logged and swallowed. Result is `accepted`, `code=None`, `final=true`; durable file is absent while model/output/command and in-memory active run/sequence are committed. | **Yes — RT-03 false acceptance/durability split.** |
| `test_RT_05_nan_inf_bool_string_and_wrong_dimension_rejected_before_mutation` | Every malformed value receives its stable final code before either chamber, model, clock, command, output, or identity changes. | 32 parameter cases: 29 fail the future invariant and 3 already comply. Detailed outcomes follow. | **Yes — RT-05.** |

The RT-05 type/dimension/finiteness contract used by the test is:

- chamber numeric/type/dimension failures: final `telemetry_invalid`;
- malformed timestamp type/format: final `timestamp_invalid`;
- malformed sequence type/value: final `sequence_invalid`.

These codes are software contract identifiers, not physical thresholds.

### Exact RT-05 parameter outcomes

`Changed=yes` means the complete model/time/command/output/identity snapshot changed.
`PL`/`MT` are chamber-step entry counts.

| Case | Current disposition | PL | MT | Changed | Future assertion |
|---|---|---:|---:|---|---|
| bed-bank-nan | accepted | 1 | 1 | yes | final `telemetry_invalid` |
| bed-bank-pos-inf | accepted | 1 | 1 | yes | final `telemetry_invalid` |
| bed-bank-neg-inf | accepted | 1 | 1 | yes | final `telemetry_invalid` |
| bed-bank-bool | accepted | 1 | 1 | yes | final `telemetry_invalid` |
| bed-bank-numeric-string | accepted | 1 | 1 | yes | final `telemetry_invalid` |
| bed-bank-nested | retryable `internal_error` | 1 | 0 | yes | final `telemetry_invalid` |
| bed-bank-wrong-size | accepted | 1 | 1 | yes | final `telemetry_invalid` |
| bed-bank-malformed-object | retryable `internal_error` | 1 | 1 | yes | final `telemetry_invalid` |
| wall-temp-nan | accepted | 1 | 1 | yes | final `telemetry_invalid` |
| wall-temp-bool | accepted | 1 | 1 | yes | final `telemetry_invalid` |
| wall-temp-numeric-string | accepted | 1 | 1 | yes | final `telemetry_invalid` |
| wall-temp-array | retryable `internal_error` | 1 | 0 | yes | final `telemetry_invalid` |
| power-nan | retryable `internal_error` | 1 | 0 | yes | final `telemetry_invalid` |
| power-pos-inf | retryable `internal_error` | 1 | 0 | yes | final `telemetry_invalid` |
| power-neg-inf | retryable `internal_error` | 1 | 0 | yes | final `telemetry_invalid` |
| power-bool | accepted | 1 | 1 | yes | final `telemetry_invalid` |
| power-numeric-string | accepted | 1 | 1 | yes | final `telemetry_invalid` |
| power-object | retryable `internal_error` | 1 | 0 | yes | final `telemetry_invalid` |
| reflected-power-array | retryable `internal_error` | 1 | 0 | yes | final `telemetry_invalid` |
| pressure-inf | accepted | 1 | 1 | yes | final `telemetry_invalid` |
| pressure-bool | accepted | 1 | 1 | yes | final `telemetry_invalid` |
| pressure-numeric-string | accepted | 1 | 1 | yes | final `telemetry_invalid` |
| pressure-object | retryable `internal_error` | 1 | 0 | yes | final `telemetry_invalid` |
| timestamp-numeric-string | final `timestamp_invalid` | 0 | 0 | no | **passes current code** |
| timestamp-bool | final `timestamp_missing` | 0 | 0 | no | final `timestamp_invalid` |
| timestamp-array | final `timestamp_missing` | 0 | 0 | no | final `timestamp_invalid` |
| sequence-bool | accepted | 1 | 1 | yes | final `sequence_invalid` |
| sequence-numeric-string | accepted | 1 | 1 | yes | final `sequence_invalid` |
| sequence-fractional | accepted | 1 | 1 | yes | final `sequence_invalid` |
| sequence-nan | final `sequence_invalid` | 0 | 0 | no | **passes current code** |
| sequence-inf | uncaught `OverflowError` | 0 | 0 | no | final `sequence_invalid` |
| sequence-array | final `sequence_invalid` | 0 | 0 | no | **passes current code** |

Summary of the 29 RT-05 failures:

- 17 invalid frames were reported accepted and committed.
- 9 invalid frames entered chamber processing, mutated state, and became retryable
  `internal_error` results instead of final validation rejections.
- 2 malformed timestamps were rejected without mutation but used the unstable/wrong
  code `timestamp_missing` rather than `timestamp_invalid`.
- 1 infinite sequence value escaped `ingest_line` as an uncaught `OverflowError`.

The 8 runtime warnings in the standalone/combined runs are further evidence that
infinite values reached plant arithmetic; they are not test setup failures.

## Exact commands and results

### Worktree check

```sh
git rev-parse --is-inside-work-tree
```

Result: exit 128; not a Git repository. No initialization/configuration followed.

### Disposable environment setup

```sh
python3 -m venv --system-site-packages /private/tmp/reclaim_rt03_rt05_venv
/private/tmp/reclaim_rt03_rt05_venv/bin/python -m pip install 'pytest>=7'
```

The first sandboxed install attempt could not resolve `pypi.org`; the approved
network retry succeeded and installed pytest 9.1.1 plus `iniconfig`, `pluggy`, and
`pygments` into the disposable environment. No production host or repository
dependency file was changed.

### Version capture

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/reclaim_rt03_rt05_venv/bin/python - <<'PY'
import platform, pytest, numpy, scipy, sys
print(platform.platform())
print(sys.version)
print(pytest.__version__, numpy.__version__, scipy.__version__)
try:
    import sklearn
    print(sklearn.__version__)
except Exception as exc:
    print(type(exc).__name__, exc)
PY
```

Result: versions recorded in the environment table; scikit-learn unavailable.

### Existing test baseline before the new test file was written

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=cloud_engine \
  /private/tmp/reclaim_rt03_rt05_venv/bin/python -m pytest \
  -p no:cacheprovider \
  cloud_engine/tests/test_lifecycle_continuous.py \
  cloud_engine/tests/test_live_ingest_contract.py -vv
```

Result: **21 passed in 2.52 s**, exit 0, no skips or collection failures.

### New regression file, final standalone run

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=cloud_engine \
  /private/tmp/reclaim_rt03_rt05_venv/bin/python -m pytest \
  -p no:cacheprovider cloud_engine/tests/test_rt03_rt05_integrity.py \
  -q --tb=no
```

Result: **32 failed, 3 passed, 8 warnings in 1.32 s**, exit 1. All 35 collected.
No skip, import, fixture, collection, or environment failure occurred in this final
run.

An earlier development run used `PL_T_bed_tcs` as the valid fixture and failed before
the injected MT fault because the current `_bed_temp` prefix scan treated the list
key itself as a flattened scalar channel. That was a test-fixture/setup defect, not
accepted as RT-03 evidence. The fixture was corrected to the engine's explicit
`PL_T_bed_tc1..4` and `MT_T_bed_tc1` scalar channels before the final results above.

### RT-03 focused confirmation

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=cloud_engine \
  /private/tmp/reclaim_rt03_rt05_venv/bin/python -m pytest \
  -p no:cacheprovider cloud_engine/tests/test_rt03_rt05_integrity.py \
  -k 'RT_03' -q --tb=short
```

Result: **3 failed, 32 deselected in 0.97 s**. All three are intended RT-03 product
failures, including confirmed PL completion before MT fault entry.

### RT-05 focused confirmation

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=cloud_engine \
  /private/tmp/reclaim_rt03_rt05_venv/bin/python -m pytest \
  -p no:cacheprovider cloud_engine/tests/test_rt03_rt05_integrity.py \
  -k 'RT_05' -q --tb=short
```

Result: **29 failed, 3 passed, 3 deselected, 8 warnings in 1.26 s**. The 3 passes
are the already-correct timestamp/sequence cases identified above; none was skipped.

### Combined cloud-engine suite

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=cloud_engine \
  /private/tmp/reclaim_rt03_rt05_venv/bin/python -m pytest \
  -p no:cacheprovider cloud_engine/tests -q --tb=short
```

Result: **32 failed, 24 passed, 8 warnings in 2.86 s**, exit 1. The 24 passes are the
21 original tests plus the 3 already-correct RT-05 parameters. No skip or collection
failure occurred.

## Environment/setup failures versus product defects

| Observation | Classification |
|---|---|
| Original Homebrew environment lacked pytest; bundled app Python also lacked the complete runner/scientific set. | Environment limitation, resolved for this session with a disposable local venv. |
| First pip attempt could not resolve PyPI in the sandbox. | Environment/network limitation; approved retry succeeded. |
| No approved Python/platform/lock decision or lock file exists. | External owner/tooling blocker to a reproducible locked environment; not a test failure. |
| Early list-bank valid fixture failed before the injected MT fault. | Test-fixture setup failure; corrected and excluded from final evidence. |
| Final RT-03 failures. | Intended product defects: partial mutation, non-equivalent retry, swallowed durable failure/false acceptance. |
| Final RT-05 29 failures and 8 numerical warnings. | Intended product defects: missing stable pre-mutation type/dimension/finiteness validation. |

## Unresolved owner decisions

1. **Supported test/build targets:** approve Python versions and macOS/Linux/Windows
   OS/ABI targets, plus the dependency lock/wheel tool. Until then, the disposable
   environment is evidence only, not a release baseline.
2. **Physical envelopes:** controls/thermal owners must approve temperature,
   pressure, forward/reflected power, reflected-power relationship/ratio, sensor
   disagreement, units, continuity, and clock-skew limits. No min/max tests were
   added in this session.
3. **Captured telemetry schema:** approve the exact sensor-bank dimensions and raw
   cRIO schema/version. The current PL mapping contains four bed channels and the MT
   mapping one, which is what the inference-safe dimension probes characterize.
4. **Persistence transaction policy:** review the candidate-state/durable-identity
   commit order and required retry disposition. This baseline requires that durable
   failure never be reported accepted and never leave visible model/output state.
5. **Publisher commit boundary:** any future external publisher must support staging
   without side effects before the transaction commits.

Physical operating-range cases are explicitly blocked by decisions 2 and 3. They
are not skipped tests and no thresholds were invented.

## Recommended boundary for the subsequent runtime implementation

A separately authorized runtime session should remain narrowly within Phase 1:

1. Validate and normalize the complete envelope and both chamber payloads before
   changing `_last_ts`, `count`, `t`, either chamber, command, service state, or
   identity. Reject booleans, numeric strings, container-valued scalars, wrong bank
   dimensions, and non-finite values with stable final codes.
2. Do not add physical minimum/maximum thresholds until approved envelopes exist.
3. Prepare isolated candidates for both complete chamber object graphs, dual clocks
   and counters, combined output/events, command, service latest/history, and run/gap
   identity. Candidate publishers must have no external side effects.
4. Make identity persistence failure observable; do not swallow it. Define and test a
   commit sequence in which durable failure cannot yield accepted or visible output.
5. Commit the complete candidate aggregate once, only after PL, MT, output/event
   preparation, and durability succeed. Discard it on any failure.
6. Make the tests pass by implementing the invariants, not by weakening snapshots,
   changing failure expectations, skipping cases, or adding coercion.
7. Keep command authority advisory and disconnected. This phase does not authorize
   command envelope exposure, HMI/gateway governor integration, actuator control, or
   any change to the independent physical interlock.

## Scope and safety confirmation

This session changed no runtime behavior and made no changes to:

- predictive/runtime Python modules;
- gateway runtime code;
- service or Scheduled Task definitions;
- deployment scripts or runbooks;
- CI workflows;
- command authority, `/command` exposure, HMI, gateway governor, actuator, or control
  system integration;
- the independent physical hardware interlock;
- secrets, production hosts, VM/gateway deployments, or tunnels;
- Git repository state or Git configuration.

The session stops at the failing regression baseline and this report. Transactional
stepping and validation fixes require separate reviewed authorization.
