# RECLAIM Cloud Engine — VM Session Handoff (Convene deployment)

> **Stage:** 1 — Cloud engine on the Convene VM + egress tunnel · **Status:**
> CURRENT / read-first for the VM session. This is the **full-story** entry point;
> the step commands live in `VM_ENGINE_RUNBOOK.md`, the objective outline in
> `VM_ENGINE_SESSION_BRIEF.md`, and the fault/fix rationale in
> `../docs/RECLAIM_Predictive_Engine_Lifecycle_Memo.md`.

**Written:** 2026-08-15 · Read this before deploying. This endpoint previously
produced **unanticipated results and required a reboot**, and ad-hoc debugging made
it worse. That failure mode is now understood, fixed, and covered by tests. The
purpose of this document is to make sure the VM session **does not re-introduce it.**

---

## 1. Read this in order

1. **This document** — the story, the guardrails, and the acceptance gates.
2. `../docs/RECLAIM_Predictive_Engine_Lifecycle_Memo.md` — the authoritative
   fault/fix analysis (why the reboot was needed, and §4.1 the design of record).
2b. `../docs/RECLAIM_Predictive_Engine_RedTeam_Remediation.md` — the red-team
   findings (RT-01..08), the **command-authority mode**, and what blocks the
   advisory deploy vs. active control. Read before wiring `/command`.
3. `DEPLOYMENT_TOPOLOGY.md` — authoritative Windows-only live platform map.
4. `VM_ENGINE_RUNBOOK.md` — the exact Windows Server 2025 deployment commands
   (release, venv, ACL-protected secrets, WinSW, cloudflared, verify, hand back).
5. `VM_ENGINE_SESSION_BRIEF.md` — the one-page objective + step outline.
6. `GATEWAY_GO_LIVE.md` / `HANDOFF.md` — project-wide status and the go/no-go list.

If you only remember one thing: **§4 (Do not debug it back).**

---

## 2. What this endpoint is

The cloud **dual predictive engine** (`cloud_engine/push_ingest_dual.py`) runs on
the cloud-hosted Windows Server 2025 Convene VM inside Kubernetes-managed
infrastructure, bound to loopback and fronted by a Cloudflare Tunnel. Kubernetes
hosts the VM; guest operation uses Windows services, PowerShell, NTFS paths, and
ACLs. It:

- accepts authenticated live telemetry frames at `POST /ingest` (the gateway posts
  them), one estimator per chamber (plastics `PL`, metals `MT`);
- runs a UKF + residual/anomaly/forecast stack per chamber and publishes one flat
  `reclaim.state.v1` record at `GET /state` (plus `/manifest`, `/history`,
  `/health`);
- is the **single writer** of the Convene `sim_` set; the Convene-native `.stp`
  visualization and the publisher read `/state` only.

It is meant to run **continuously and autonomously** alongside the plant — no
operator startup, no scheduled reset. It must recognize idle vs. running on its own.

---

## 3. The full story — why this endpoint is high-risk, and what was fixed

**What happened before.** In continuous operation the engine's per-cycle metrics
drifted and results diverged from expectation; a **process reboot "fixed" it.**
Debugging around the symptoms tended to make things worse, because the symptom
(wrong numbers) had nothing to do with where people looked (the estimator math, the
ingest path).

**The actual root cause.** The engine was designed and validated as a *per-cycle*
estimator but deployed as a *process-lifetime* one. Several sub-components carried
per-cycle / per-run state that **nothing ever reset except restarting the process**:
the performance accumulator (energy, elapsed, peak), the live charge mass, the CUSUM
drift detector, and the adaptive process-noise scale. A reboot re-instantiated the
engine and zeroed them — so the reboot *was* the reset the code never performed.
The simulation harness hid this because it rebuilt the engine every cycle; production
kept one engine forever. Full analysis: the lifecycle memo §3.

**The fix (already implemented and tested).** The engine now has an explicit,
per-chamber **autonomous lifecycle** (`cloud_engine/reclaim_predictive_engine/lifecycle.py`)
that infers idle / running / suspended and the real batch boundaries from telemetry
it already receives (sequencer `source_op_state`, `cycle_id`, forward power, bed
temperature). At a real batch boundary it resets **only the per-cycle analytics**;
it never force-resets the estimator state, and it never resets on a power cut or on a
gateway reboot. The ingest/validation/identity/ack pipeline was **not touched.**
This removed the reboot dependency. See memo §4.1 for the design of record.

---

## 4. DO NOT DEBUG IT BACK — behaviors that are correct by design

These will look surprising if you don't know the history. **They are intended. Do
not "fix" them.** Each is asserted by the acceptance gates in §6, so if you change
them, those gates will fail and tell you.

1. **Metrics FREEZE while the plant is IDLE.** Between batches, `consumed_energy_wh`,
   `cycle_elapsed_s`, `peak_temp_K`, etc. hold their last-completed-cycle values and
   do **not** climb. `engine_phase` reads `IDLE`. This is the fix, not a stuck sensor.
2. **A POWER CUT does NOT reset anything.** On `S_PowerInterrupted`/`S_Restart` the
   phase is `SUSPENDED`; `active_heating_s` freezes, `cycle_elapsed_s` keeps counting
   wall-clock, charge mass is not recharged, and on resume it all continues in place.
   A power interruption is **not** a batch boundary. Do not add a "reset on power
   loss" — that is the exact bug we removed.
3. **The estimator (UKF) is never cold-restarted at a boundary.** Bed/wall
   temperatures are physical and measured, so the filter tracks them continuously and
   self-heals. There is deliberately no re-seed on a new cycle or a new `run_id`.
4. **Reset authority is BATCH IDENTITY (`cycle_id`), not power and not `run_id`.**
   A new batch (cycle_id turnover, guarded by a batch-present latch) resets per-cycle
   analytics. A gateway/cRIO reboot (`run_id` churn) is a *transport* event and must
   not reset the batch. Don't wire resets to `run_id` or to a power threshold.
5. **The ingest pipeline is proven — leave it alone.** Auth on `/ingest`, read-token
   gating on the GET routes, harness-mode rejection under `--production`, timestamp
   freshness, run supersession, monotone-sequence dedup, and the v1.1 per-frame ack
   are all validated. Lifecycle work lives strictly *downstream* of an accepted
   frame. Do not modify `_validate_frame` / `ingest_line` to chase an engine symptom.
6. **Cloudflare quick-tunnel `530`s are transport flakiness, not an engine fault.**
   Account-less quick tunnels intermittently return HTTP 530 (tunnel-not-ready). The
   acceptance harness retries through them. If you see 530s, that is the tunnel, not
   the engine — for a stable endpoint move to a named tunnel (runbook §8), don't
   "debug" the engine.

---

## 4A. Command authority — advisory by default (from the red-team)

A second review (`../docs/RECLAIM_Predictive_Engine_RedTeam_Remediation.md`, findings
verified against source) established that the engine's `/command` output is a **real
control path**, not a visualization side effect. The agreed design:

- `/command` (the `cmd_*` fields) is **always populated** — Convene can always show the
  intended action — but a config setting `command_authority` governs whether anything
  acts on it. **Default `advisory`: `cmd_actionable=false` always; nothing actuates.**
- Only `command_authority=active` **and** `cmd_health=="ok"** makes a command actionable;
  any unhealthy state (stale/sensor-missing/seq-gap/degraded) forces the fail-safe.
- The command carries `cmd_authority`, `cmd_actionable`, `cmd_health`, and
  `cmd_valid_until`; the actuator side must act only when actionable and unexpired, and
  **fail closed independently of the cloud**. The hardware interlock stays independent.

**For this Convene deployment: run `advisory`.** The `cmd_*` variable populates and is
visible, but nothing on the plant acts on it. Flipping to `active` is a separate,
gated milestone (see the remediation plan's disposition matrix and exit criteria).

**Blocks this advisory deploy (integrity, mode-independent):** the two Workstream-A
fixes — RT-03 (make chamber stepping transactional so a failed frame can't double-step
on retry) and RT-05 (reject non-finite / out-of-range values before the estimator).
Everything else is gated to `active` authority or to operators *relying* on the
forecast/advisory fields, which stay clearly labeled non-authoritative until then.

## 5. Deploy sequence (pointer, not a duplicate)

Follow `VM_ENGINE_RUNBOOK.md` exactly. In brief: fresh immutable release under
`C:\ProgramData\RECLAIM\releases\<SHA>` → locked Windows venv → import/dependency
smoke → ACL-protected secret file with distinct `RECLAIM_INGEST_TOKEN` and
`RECLAIM_READ_TOKEN` → WinSW `RECLAIMIngestEngine` service on
`127.0.0.1:8078` with durable `RECLAIM_INGEST_STATE` → Windows cloudflared route →
endpoint acceptance → independent Windows state bridge → Convene lease/prefix
acceptance → private gateway handoff. `--production` accepts `mode: "live"` only;
deploy side-by-side and never overwrite a running release.

**The old "scipy missing from requirements-cloud.txt" warning is stale** — the file
already pins numpy/scipy/scikit-learn. Still run the import smoke to catch a
numpy/scipy ABI mismatch on the VM's Python.

---

## 6. Acceptance gates — MUST pass before wiring Convene

Run both. They are the guardrail against silently re-introducing the reboot bug.

**Gate 1 — continuous-run regression test (offline, on the VM after venv install):**

```powershell
Set-Location C:\ProgramData\RECLAIM\releases\<TARGET_SHA>
$env:UV_CACHE_DIR = 'C:\ProgramData\RECLAIM\uv-cache'
uv run --frozen pytest -q cloud_engine\tests
```

`tests/test_lifecycle_continuous.py` drives multiple batches + a power cut through
ONE engine instance and asserts: power-cut = no reset, new cycle = reset, idle =
freeze, adaptive-Q stays off its bound. This is the test the old harness could not
catch (it rebuilt the engine each cycle).

**Gate 2 — live acceptance harness through the tunnel (the endpoint proof):**

```powershell
# From a trusted workstation; environment variables keep credentials out of the process list.
$env:RECLAIM_INGEST_TOKEN = '<private value>'
$env:RECLAIM_READ_TOKEN = '<different private value>'
python cloud_engine\tools\redteam_ingest.py --url https://<your-tunnel-host>
Remove-Item Env:RECLAIM_INGEST_TOKEN, Env:RECLAIM_READ_TOKEN
# expect: ==== ACCEPTANCE RESULT: 20/20 checks passed ====
```

It emits real cRIO/LabVIEW terminology, exercises the pipeline contract, then proves
the lifecycle end to end: ACTIVE while heating → SUSPENDED on power cut with
`active_heating_s` **frozen** → resume continues → new `cycle_id` recharges mass and
zeros heating/energy. A clean **20/20 means the reboot dependency is gone and the
pipeline is unchanged.** Anything less: read the failing check, then re-read §4 before
touching code.

---

## 7. Watch these on `/state` to confirm autonomy live

After the gateway feeds real frames, `GET /state` (read token) should show, per
chamber (`PL_`/`MT_` prefix):

| Field | Idle | Running | Power cut |
|---|---|---|---|
| `*_engine_phase` | `IDLE` | `ACTIVE` (or `LOADING`/`COOLDOWN`) | `SUSPENDED` |
| `*_active_heating_s` | frozen | climbing | **frozen** |
| `*_cycle_elapsed_s` | frozen | climbing | climbing (wall-clock) |
| `*_consumed_energy_wh` | frozen | climbing | flat (no power) |
| `*_charge_mass_kg` | last value | decaying | held |

A new batch should snap `*_active_heating_s` and `*_consumed_energy_wh` to ~0 and
`*_charge_mass_kg` back to its `mf_m0` — with no operator action. If those numbers
climb across batches or reset on a power blip, that is the regression; go to §4.

---

## 8. Known non-issues (do not chase)

- **HTTP 530 from the tunnel** — account-less quick-tunnel transient; retry or move
  to a named tunnel. Not the engine.
- **`*_engine_phase: IDLE` with stale-looking metrics between batches** — intended
  freeze (§4.1). The freshness gate (`state_age_ms` / DATA NOT LIVE) is the separate,
  correct mechanism for "is the feed live."
- **Restricted-DNS test boxes** can't resolve `*.trycloudflare.com`; pin the visitor
  edge IP (`--pin-ip`, resolvable via DoH). This is an environment quirk, not a
  deploy problem — the real VM resolves normally.

---

## 9. Open items / decisions carried (from memo §7)

Defaults are chosen and safe; confirm against the real sequencer when convenient:

- Confirm the VM's Python version as supported (record it; GO_LIVE §9.2).
- Confirm the sequencer emits `S_PowerInterrupted`/`S_Restart` on a real outage
  (vs. simply dropping frames — both are handled).
- Confirm the lifecycle power-on threshold and ACTIVE debounce against real cadence
  (`config.py` `LifecycleConfig`).
- Charge-mass source: per-cycle config re-seed today; a real per-batch `charge_mass`
  envelope field is a future gateway negotiation.

---

## 10. What changed in this work (delta from earlier snapshots)

- **Repo reconciled and cleaned**: newest reconciled docs, deployment handoff set,
  Unreal path retired in favor of the Convene-native `.stp` visualization, build
  junk removed, `.gitignore` added.
- **Engine lifecycle implemented**: `reclaim_predictive_engine/lifecycle.py`,
  `PredictiveEngine.reset_cycle()`, adaptive-Q anti-windup, charge-mass recharge,
  and new `engine_phase` / `active_heating_s` outputs. Pipeline unchanged.
- **Tests**: `tests/test_lifecycle_continuous.py` (regression guard) added;
  `cloud_engine/tools/redteam_ingest.py` (live acceptance harness) added.
- **Validated**: full cloud-engine suite green; live red-team **20/20 through a real
  Cloudflare tunnel** and on loopback.
