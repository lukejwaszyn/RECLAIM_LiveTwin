# RECLAIM CI/CD Implementation Baseline

**Date:** 2026-08-16  
**Status:** Local Git and hosted-CI baseline; no remote or production CD enabled  
**Authority:** Advisory only

## Outcome

This repository now has the source-side pieces needed to begin controlled CI:

- a local Git repository on `main` and a reviewable baseline commit;
- tracked-content hygiene rules that exclude secrets, runtime state, caches, and
  the historical handoff ZIP;
- a universal, hash-bearing `uv.lock` for Python 3.11 through 3.13;
- GitHub-hosted CI definitions with read-only permissions and actions pinned to
  full commit SHAs;
- separate inherited-baseline and RT-03/RT-05 safety checks;
- deterministic release-candidate packaging with a digest-bound manifest; and
- an explicit refusal to call an unsigned candidate production-promotable.

No remote repository was created, no source was pushed, and no workflow was run
on GitHub. No production host, secret, tunnel, service, task, gateway runtime,
hardware interlock, or command-authority path was changed.

## CI checks

`.github/workflows/ci.yml` runs on pull requests and pushes to `main`.

| Check | Purpose | Expected initial state |
|---|---|---|
| `Repository hygiene` | Reject tracked secret/state/archive material | Green |
| `Baseline / Python 3.11` | Compile and run gateway plus inherited cloud tests | Green |
| `Baseline / Python 3.13` | Same compatibility proof on the second target | Green |
| `Safety gate / RT-03 + RT-05` | Named transactional and validation regressions | Red until RT-03/RT-05 are fixed |

The safety job is not marked `continue-on-error`. A green overall CI result
would therefore be dishonest today. Repairing the product defects in a separately
reviewed runtime phase should turn that gate green without weakening its tests.

CI has only `contents: read`. Checkout credential persistence is disabled. No
production secrets or network endpoints are referenced, and no runner is placed
on a production host or network.

## Reproducible environment

The root `pyproject.toml` describes the combined gateway/engine test environment.
`uv.lock` records exact distributions and hashes across supported platforms.
CI pins `uv` 0.11.21 and executes:

```bash
uv sync --locked --all-extras --dev --python 3.13
```

The `model` and `tdms` extras are installed in CI so optional imports are tested;
deployment-host lock/wheel bundles remain a separate target-specific deliverable.
CI does not prove that a wheel set is deployable on the production VM or Windows
gateway.

## Release-candidate boundary

`.github/workflows/release-candidate.yml` is manual and accepts only `main`. It
runs repository hygiene, compilation, gateway tests, and the complete cloud suite
before calling `tools/build_release_candidate.py`. Because RT-03/RT-05 currently
fail, no candidate can be built from this baseline.

When all gates pass, the builder emits:

- `reclaim-livetwin-<version>.tar.gz`;
- `reclaim-livetwin-<version>.sha256`; and
- `reclaim-livetwin-<version>.manifest.json`.

The manifest binds the artifact digest, commit, tree, dependency-lock digest,
Python targets, schemas, and test-report digests. It also states:

```json
{
  "authority": "advisory",
  "signed": false,
  "production_promotable": false
}
```

This is release-candidate scaffolding, not production CD. A checksum protects
against accidental corruption but is not a trust anchor when obtained beside the
artifact.

## Private remote setup

The GitHub organization/owner, repository name, and approved visibility were not
provided, so no remote was invented. After an owner approves those values:

```bash
git remote add origin git@github.com:<approved-owner>/<approved-private-repo>.git
git push -u origin main
```

Before accepting pull requests, configure the remote repository as follows:

1. Keep Actions permissions read-only by default and disallow Actions from
   creating or approving pull requests.
2. Protect `main`: require a pull request, dismiss stale approvals, require
   conversation resolution, block force-push/deletion, and require the four
   checks listed above.
3. Require signed commits if the team has an approved signing policy.
4. Protect `v*` tags against update or deletion.
5. Replace `.github/CODEOWNERS.example` placeholders with real approved users or
   teams, then rename it to `.github/CODEOWNERS` and require code-owner review.
6. Require controls/safety and software ownership for workflow, deployment,
   predictive-model, gateway, authority, schema, and threshold changes.
7. Do not add production secrets to repository or pull-request environments.

Requiring the RT-03/RT-05 gate will intentionally block merge until the known
defects are remediated. If documentation-only work must proceed beforehand, use
a separately reviewed ruleset policy rather than weakening or skipping the gate.

## Local verification

Run from the repository root:

```bash
uv lock --check
uv sync --locked --all-extras --dev --python 3.13
python3 scripts/check_repository_hygiene.py
.venv/bin/python -m compileall -q cloud_engine pi_gateway scripts tools

cd pi_gateway
PYTHONPATH=. ../.venv/bin/python -m pytest tests -q

cd ../cloud_engine
../.venv/bin/python -m pytest tests -q --ignore=tests/test_rt03_rt05_integrity.py
../.venv/bin/python -m pytest tests/test_rt03_rt05_integrity.py -q
```

The first two test commands should pass. The named integrity command is expected
to fail only for the recorded product defects until the next authorized runtime
remediation phase.

Observed locally on 2026-08-16 with the committed lock:

| Runtime | Gateway baseline | Cloud inherited baseline | RT-03/RT-05 gate |
|---|---:|---:|---:|
| Python 3.11.15 | 10 passed | 21 passed | Not repeated; Python 3.13 is the named gate target |
| Python 3.13.14 | 10 passed | 21 passed | 32 failed, 3 passed for the recorded defects |

The workflow YAML parsed successfully, the lock check passed, repository hygiene
passed, compilation passed, and rebuilding the same candidate twice produced the
same archive digest. The generated test candidate remained unsigned and
non-promotable.

## Decisions still owned outside this implementation

- GitHub organization/owner, repository name, visibility, billing, and admins.
- Real CODEOWNERS identities and approval counts.
- Whether commit signing is mandatory and which identity policy is trusted.
- Release signing mechanism, trusted issuer/key, verifier policy, and signature
  retention.
- Immutable release/tag enforcement and artifact-retention period.
- Production Python ABI/platform targets and per-target offline wheel bundles.
- Persistent identity/queue schema compatibility and migration/rollback policy.
- Stable release roots and fixed, least-privilege pull installers for both hosts.
- Maintenance-state definition, deployment receipt schema, and named operators.
- Approved physical envelopes. CI includes no invented range thresholds.

Until these are resolved, CI may validate source, but production promotion is
prohibited. The independent hardware interlock remains authoritative and outside
this pipeline.
