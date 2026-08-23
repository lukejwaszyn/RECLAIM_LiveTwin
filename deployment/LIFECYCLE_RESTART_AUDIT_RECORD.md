# Lifecycle / Restart Audit — Work Record

> **Stage:** 2→3 · **Date:** 2026-08-23 · **Branch:** `desktop/edge-gateway`
> **Scope:** audit of the graceful-closure and restart handling, scenario
> rehearsal targets, and the deploy-prompt accuracy pass. Advisory path only —
> **no command/actuation path exists or was added.**

This records what was verified, what changed, and what is still open. It is an
engineering record, not an acceptance sign-off: **Gates 0, 1, 3, 4, 5 remain open
and are controls/onsite-owned.** Nothing here signs any of them.

---

## 1. Verified healthy (evidence, not assertion)

**Test baseline — all suites green.**

| Suite | Count | Result |
|---|---|---|
| `pi_gateway` | 55 | pass |
| `cloud_engine` | 73 | pass (was 67; +6 added this session, §3) |
| `crio_source_record` | 70 | pass |

**Gateway graceful closure.** `pi_gateway/reclaim_edge/main.py:49-50` traps
SIGINT/SIGTERM into a `stop` event; receiver/publisher/convene threads are joined
(3 s each) before `buffer.close()`. `buffer.py` commits on every
enqueue/ack/dead-letter, so an *ungraceful* stop (hard power cut, not just a clean
signal) also loses no durable frame.

**Restart durability.** The publisher seq high-water mark survives a restart with
no reuse and no collision — covered by
`pi_gateway/tests/test_publisher_ack_contract.py:84`.

**Twin tracking across an outage.** `consumed_energy_wh` integrates absorbed power
independently of lifecycle phase (`metrics.py:48-57`), so the UKF keeps tracking
through a suspend rather than freezing. This is correct and matches the
power-outage scenario's stated purpose ("state tracking through the interruption").

**Identity-churn guard — logic verified correct.** The branch in
`lifecycle.py:113-122` that distinguishes a *transport* event (a cRIO/gateway
reboot renumbering `cycle_id` mid-batch) from a real batch boundary was exercised
across five permutations and behaved correctly in all of them:

| Case | Expected | Observed |
|---|---|---|
| Reboot renumbers `cycle_id` mid-batch, hot + powered | no reset | no reset |
| Reboot renumbers across a power interruption | no reset | no reset |
| Genuine new batch via `S_BatchLoad` after `S_Complete` | reset | reset |
| New `cycle_id` on a cold chamber | reset | reset |
| New `cycle_id`, hot, no LOAD/COMPLETE seen | suppressed (by design) | suppressed |

---

## 2. Finding still OPEN — `active_heating_s` vs `consumed_energy_wh`

**Not fixed. Requires a semantics decision, and is coupled to Gate 1.**

In `power_outage_scenario` (`harness.py:146`) forward power returns to 3500 W at
t=750 s while `op_state` remains `S_Restart` until t=770 s. `S_Restart` is a member
of `suspend_states` (`lifecycle.py:51`), and the SUSPEND branch returns at
`lifecycle.py:108` *before* the powered check. Measured over the full 900 s
scenario:

```
true powered time     : 600 s
FSM active_heating_s  : 580 s
uncounted             :  20 s  =  19.4 Wh of 583.3 Wh  (3.3% of cycle energy)
```

Both fields are published (`engine.py:261,267`) and are already read together
downstream (`tools/redteam_ingest.py:169`). Any average power derived as
`consumed_energy_wh / active_heating_s` reads ~3.4% high for a cycle containing a
restart.

The field's own comment is internally contradictory exactly here — "accumulated
powered time only (**pauses on suspend**)" — so this is a definition question, not
an obvious coding error:

- **Option A** — `active_heating_s` means *powered seconds*: accumulate it inside
  the SUSPEND branch when `p_fwd` is above threshold. Preserves hold/no-reset.
- **Option B** — it means *seconds in a non-suspended phase*: current behavior is
  correct; document the divergence so nobody derives average power from the pair.
- **Option C** — `S_Restart` is recovery-with-power and does not belong in
  `suspend_states` at all.

**Blocked on Gate 1.** `LifecycleConfig`'s docstring already says to "confirm the
sets and thresholds against the real sequencer," and the acceptance handoff states
the signed maps are **unsigned** — `source_op_state` is unratified. The open
question for controls is concrete: **does the real sequencer's `S_Restart` carry
forward power?** If it does, this gap reaches live data, not just the rehearsal.
No code was changed pending that answer.

---

## 3. Completed this session

**(a) Churn-guard and suspend-state regression tests** — `+6` in
`cloud_engine/tests/test_lifecycle_continuous.py`, bringing that file to 9 and the
suite to 73. The guard previously had **zero** coverage despite being the most
intricate branch in the module, and only `S_PowerInterrupted` was tested —
`S_Restart` and `S_SafeState` were both untested *even though `S_Restart` is what
the power-outage scenario actually emits*. Added, one guard term pinned per test:

- `test_reboot_renumbering_cycle_id_mid_batch_does_not_reset`
- `test_reboot_renumbering_across_power_interruption_does_not_reset`
- `test_restart_and_safe_state_hold_the_batch_without_resetting`
- `test_batch_identity_turnover_after_completion_resets`
- `test_new_cycle_id_on_cold_chamber_resets` (pins the `hot` term)
- `test_new_cycle_id_while_hot_without_a_load_is_suppressed_by_design`

The last one deliberately pins a **latent dependency**: with no LOAD/COMPLETE to
bracket it, a `cycle_id` turnover on a hot batch is read as churn, so analytics
carry across. That is correct *only while the sequencer always emits
`S_BatchLoad`* at a real boundary. If that ever stops being true, this is the test
that should fail and force the guard to be revisited.

**(b) Test-count references corrected, 67 → 73.** The pre-flight gate is "expect
55/67/70, any red: stop," so adding tests would have made a green run *look* like a
failed pre-flight. Updated the forward-looking expectations only:

- `CRIO_DESKTOP_DEPLOY_SESSION_PROMPT.md` (Step 1 expectation, §8 handback)
- `CRIO_GATEWAY_CUTOVER_RUNSHEET.md` (the live `REM expect 67` command annotation)
- `CRIO_INTEGRATION_ACCEPTANCE_HANDOFF.md`, `..._HANDOFF_2.md` (×3)

**SHA-stamped historical records were deliberately left at 55/67/70** — they record
what was true at `3608872` and rewriting them would falsify the evidence trail.

**(c) Deploy prompt Step 6 — loss-of-data corrected.** Step 6 listed the
loss-of-data check alongside the three working profiles as though it were runnable.
`start-rehearsal-scenario.ps1` has `ValidateSet("nominal","power-outage","lunar")`,
so an operator typing a fourth name gets a parameter-binding error. Step 6 now
states there are exactly three targets and gives the manual procedure (§4).

**(d) Deploy prompt §2 — Gate 3 checklist added to the read-first list.** Step 5
instructs the operator to file evidence as "Gate 3 checklist item 6.3," but the
read-first list never had them open that checklist.

---

## 4. Running the scenarios

**Three one-command targets, advisory-only, loopback-bound:**

```powershell
.\cloud_engine\windows\start-rehearsal-scenario.ps1 nominal        # 8177, earth_lab,     6x
.\cloud_engine\windows\start-rehearsal-scenario.ps1 power-outage   # 8178, earth_lab,    12x
.\cloud_engine\windows\start-rehearsal-scenario.ps1 lunar          # 8179, lunar_surface, 6x
```

Each refuses to start if its port already has a listener, prints its expected
behavior, and exposes `/health`, `/state`, `/history` on `127.0.0.1`. **Ports
8177–8179 must never be routed to production; `8078` is never touched.**

**The rehearsal plan wants four runs** (`NEXT_SESSION_CD_REHEARSAL_PLAN.md:164-168`)
— nominal ×2, power-outage ×1, lunar ×1, **loss-of-data ×1**. The fourth has **no
scenario target**; handoff §E.3 lists it as installer build scope. Until that
exists, run it by hand:

> Bring up any profile, confirm `/health` is advancing, then **stop the producer
> feed**. Confirm the rx counter stops advancing and `last_ack_age_s` /
> `last_success_age_s` climb — the stack must *report staleness*, not hold or
> fabricate a last-good value. On the gateway the same check runs against loopback
> `9080` (never tunnel it).

That freshness behavior is what Convene gates display on, so this check is the one
that protects against a stale value being read as live.

For each run retain: commit SHA, run ID, timestamps, expected vs observed,
screenshots, deviations. Keep synthetic services clearly labeled rehearsal data.

---

## 5. Still open

| # | Item | Owner | Blocking |
|---|---|---|---|
| 1 | `active_heating_s` / `S_Restart` semantics (§2) | engine + controls | Gate 1 signature |
| 2 | **Convene `gw_` binding not live** — code path exists (`ConvenePublisher`, mapping, tests) but `convene_enabled: false` in both configs; needs https endpoint + credentials on the gateway | gateway | Convene backend |
| 3 | Convene backend Firestore composite index over `machineId`/`status`/`createdAt` — heartbeat returns HTTP 500; `gw_` publish itself is unaffected | Convene backend | external |
| 4 | **27 raw `vars` names unconfirmed against a real cRIO frame** (GO_LIVE §9.5); Mod2 semantic aliases withheld pending the approved profile | controls | first live frame |
| 5 | **Signed maps UNSIGNED** — `cycle_id`, `source_op_state`, `active_chamber` and every raw channel are placeholder/unratified | controls | Gate 1 |
| 6 | Loss-of-data one-command target (§4) | installer scope §E.3 | — |
| 7 | `deploy\Install-ReclaimLiveTwin.ps1` does not exist; the runsheet path is what executes today | installer scope §E.3 | — |

**Gate status unchanged by this session:** 0 open · 1 open (worksheet unsigned) ·
2 done · 3 open (VI evidence + countersign owed) · 4 pending Phase B + explicit go ·
5 (fault/restart acceptance) pending Gate 4.

Note the coupling: §2, and items 4 and 5, are all the same root cause — **the cRIO
interface is not ratified.** The lifecycle FSM's state vocabulary, the channel
mapping, and the restart semantics all resolve together the moment Gate 1 is
signed against a real frame.

**Standing status: labeled engineering shadow — NO-GO for any production claim.**
