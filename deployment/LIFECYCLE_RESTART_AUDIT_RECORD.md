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
| `cloud_engine` | 74 | pass (was 67; +6 churn-guard tests, +1 stalled-status regression, §3) |
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

## 2. RESOLVED — `active_heating_s` now measured from forward power

**Was:** `active_heating_s` excluded 20 s / 19.4 Wh of genuinely powered time in
`power_outage_scenario`, because `S_Restart` is a member of `suspend_states` and
the SUSPEND branch returned before the powered check — while `consumed_energy_wh`
counted those same seconds. Two published fields disagreeing about the same 20 s,
with any derived average power reading ~3.4% high.

**Resolved by changing the signal, not the state table.** Powered time is now
measured physically, from forward power alone (`lifecycle.py` step 0):

```python
if powered:                      # p_fwd > cfg.power_on_w
    self.active_heating_s += dt
```

This runs before the SUSPEND early-return, so it is independent of what the
sequencer calls the phase. Phase labelling (IDLE / ACTIVE / SUSPENDED) still uses
`op_state` — that is what a sequencer is for — but *duration accounting* no longer
does.

**Why this beats waiting for Gate 1.** The state vocabulary is unratified and, in
at least one case, actively misleading: `S_Restart` is classified as a suspend
state while the coupler delivers full power. Keying the field to the measured
input makes it mean what its name says, puts it in agreement with
`consumed_energy_wh` (which already integrated power regardless of phase), and
**removes the dependency on the signed-map worksheet entirely.** The open Gate 1
question is no longer blocking this metric.

**Why NOT thermocouple temperature.** Temperature is a lagging, integrating
signal — the bed stays hot through an outage and a cooldown, which is exactly the
"thermal coast" the power-outage scenario exists to show. Measured over that
scenario:

| Gating signal | Counted | vs true 600 s |
|---|---:|---|
| **Forward power (implemented)** | **600 s** | exact |
| Temperature (`hot`) | 900 s | **+300 s phantom, 50% overcount** |

Temperature would have booked the entire 300 s outage as heating. It remains the
right signal for a different question — "is a batch physically present" — which is
what the churn guard uses `hot` for. Power for *is it heating*, temperature for
*is something in there*.

**Verified:** the scenario that exposed the gap now reports 600 s counted of 600 s
true, 0 uncounted. Regression tests
`test_active_heating_counts_powered_time_even_in_a_suspend_state` and
`test_active_heating_ignores_a_hot_but_unpowered_chamber` pin both halves
(cloud_engine 74 → 76). All pre-existing tests passed unchanged.

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

## 3b. Bug found and FIXED — stalled stream kept reporting `status: running`

**Found by** building the `loss-of-data` rehearsal. **Fixed** in
`cloud_engine/reclaim_predictive_engine/service.py`.

`TwinStateService.update()` set `status = "running"` on every frame and nothing
ever cleared it. When the driver finished — a `--no-loop` run, or an exhausted
replay — the daemon driver thread simply returned while `serve_forever()` kept
the HTTP surface up. `/health` and `/state` then advertised **`status: running`
over a record that could no longer change**, alongside a reassuring
`advisory_message: "All residuals within bounds"`. A consumer could not tell a
live stream from a dead one, which is precisely the failure the loss-of-data
check exists to expose.

**Fix.** Added `TwinStateService.mark_stopped()` and wrapped both drivers so that
whichever one runs flags the stream on return:

- `status` flips `running` → `stopped`; the frozen values stay readable.
- The latest view is **copied before mutation**, so the history entry keeps the
  status it actually had while live — history is not retroactively rewritten.
- Idempotent, and a later `update()` revives it to `running` (so a looping
  scenario is unaffected).

**Verified** end to end: a `--no-loop` cycle reported `status: running, t_sim:
304.0` mid-run and `status: stopped, t_sim: 400.0` after completion, on both
`/health` and `/state`. Regression test:
`test_stopped_stream_does_not_keep_reporting_running` (cloud_engine 73 → 74).

**Still true, and not a bug:** `/state` carries no wall-clock timestamp and no age
field, so the engine can answer "not advancing" but never "how stale." Real
freshness gating lives in the bridge (`convene_bridge/contract.py`), which
requires `state_age_ms` and `mode: live` and therefore only accepts the
production dual-ingest path. Rehearsal exercises the engine, not that gating.

---

## 3c. Convene `gw_` audit tap — PROVEN on the live gateway

The `gw_` tap was never broken. It had never been **exercised**: the gateway had
`received: 0`, and the publisher loads its credential lazily on first delivery,
so `machine_id` was null and nothing had ever been attempted. Convene showed the
machine as connected because the *agent* heartbeat updates presence before it
500s — presence is not telemetry.

One labeled synthetic frame (`COMMISSIONING-NOT-CRIO-20260823T203214Z`) sent into
`192.168.1.1:9070` settled it. Both seams delivered:

```
received: 0 -> 1        delivered: 1        queue_depth: 0
last_ack_age_s: 18.23   dead_lettered_session: 0
convene: machine_id BcryPSMP2iLbSRns5uhm, delivered 1, failed 0, last_success_age_s 18.48
```

So Seam A (cRIO-style TCP -> framer -> durable queue), Seam B (Cloudflare -> VM
`/ingest`, **acked**), and the independent Convene `gw_` tap all work on the
current build. The remaining Convene defect is unrelated and backend-owned: the
agent's heartbeat/command plane still returns HTTP 500 for want of the Firestore
composite `machineCommands` index (2622 occurrences in `agent.log`).

**Doc correction:** the live desktop identity is `BcryPSMP2iLbSRns5uhm`, and the
SYSTEM profile and user profile now hold the *same* credential. The three machine
IDs named in `GATEWAY_GO_LIVE.md` §9.8 (`6xai…` revoked, `NziS…`, `2rIt…`) are all
historical; the 2026-08-19 SYSTEM/user divergence is resolved.

---

## 3d. Bug found and FIXED (pre-existing) — runner unparseable in Windows PowerShell 5.1

`start-rehearsal-scenario.ps1` was saved as UTF-8 **without a BOM** while containing
non-ASCII em dashes. Windows PowerShell 5.1 decodes a BOM-less `.ps1` as ANSI, so
`—` (`E2 80 94`) became `a-euro-"` in CP1252 — and that trailing `0x94` is a
smart closing quote, which terminated the string early and cascaded into
`The string is missing the terminator: "`. The script would not run **at all** under
the very shell the deploy prompt mandates ("run elevated Windows PowerShell 5.1").

**Pre-existing, not introduced by this session's rewrite:** the same failure
reproduces on the original at `9e8e898^`. It went unnoticed because a syntax check
run under **pwsh 7** parses the file fine — pwsh assumes UTF-8. Anything validating
these scripts must do so under 5.1, or the check is worthless.

**Fix.** The runner is now pure ASCII (`assert` on write). Verified: parses OK under
5.1, and a full one-command run bootstrapped the locked environment and served
`/health` on 8177.

**Blast radius checked:** only two `.ps1` files in the repo contain non-ASCII. The
other, `deployment/convene-setup-2.ps1`, parses fine under 5.1 (its degree sign and
box-drawing characters do not mojibake into a quote). **Every cutover script**
(`configure-crio-network-firewall`, `finalize-gateway-config`, `install-gateway-task`,
`send-commissioning-*`, `repair-convene-desktop-agent`) is ASCII-clean and unaffected.

**Convention going forward:** keep `.ps1` files ASCII-only. It removes the encoding
dependency entirely rather than relying on a BOM surviving future edits.

**Second, separate gotcha (documented, not a code bug):** execution policy blocks
these scripts on a default Windows install. The repo convention already used
elsewhere is `powershell -NoProfile -ExecutionPolicy Bypass -File <script>`; the
root README now uses that form for the scenarios.

---

## 3e. Sustained stream — PASSED (450 frames, both seams, 2026-08-23)

One frame proved the path existed; this proves it **sustains**.
`send-commissioning-stream.ps1`, 180 s at 400 ms (approximating the real ~0.38 s
source cadence), through the real ingress with nothing stubbed:

```
FramesSent            450        GatewayReceivedDelta  450
VmIngestedDelta       450        DeadLetterDelta         0
ConveneDeliveredDelta 270        ConveneFailedDelta      0
ConveneCoalescedDelta 180        QueueDepth              0
LatestSequence        451        Passed               true
VmActiveRunId == LatestRunId  (e61a982f-…)
```

**Zero loss on the durable path:** every one of 450 frames was received, queued,
delivered and ingested by the VM, the queue fully drained, and the retained
dead-letter count did not move. Run identity matched end to end.

**The 270/180 Convene split is correct, not loss.** The `gw_` tap is deliberately a
nonblocking one-frame queue that *replaces* an older pending frame rather than
blocking the receiver — 270 delivered + 180 coalesced = 450 accounted for. Coalescing
is the audit tap protecting the durable path, exactly as designed; it never
participates in VM acking. This is the first exercise of that behavior
(`coalesced` had been 0 since deployment).

---

## 4. Running the scenarios

**Three one-command targets, advisory-only, loopback-bound:**

```powershell
.\cloud_engine\windows\start-rehearsal-scenario.ps1 nominal        # 8177, earth_lab,     2x -> ~3m20s
.\cloud_engine\windows\start-rehearsal-scenario.ps1 power-outage   # 8178, earth_lab,     4x -> ~3m45s
.\cloud_engine\windows\start-rehearsal-scenario.ps1 lunar          # 8179, lunar_surface, 2x -> ~3m20s
.\cloud_engine\windows\start-rehearsal-scenario.ps1 loss-of-data   # 8181, earth_lab,     2x -> one cycle, then stale
```

Each refuses to start if its port already has a listener, prints its expected
behavior, and exposes `/health`, `/state`, `/history` on `127.0.0.1`. **Ports
8177–8181 must never be routed to production; `8078` is never touched.**

**The rehearsal plan wants four runs** (`NEXT_SESSION_CD_REHEARSAL_PLAN.md:164-168`)
— nominal ×2, power-outage ×1, lunar ×1, **loss-of-data ×1**. All four are now
one-command targets (`loss-of-data` added on 8181, running one cycle with
`--no-loop` so the endpoints keep serving while the data stops advancing). The
equivalent check on the gateway is still manual:

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

## 4b. DEFERRED until the cRIO link is live — physics-derived identity

**Decision (2026-08-23, owner):** do not design against the current channel list.
The VI will supply different semantics; `cycle_id`, `source_op_state`, and
`active_chamber` get resolved once the cRIO link is established and working.
Recorded here only so the reasoning is not re-derived later.

**The method transfers even though the names will not.** `lifecycle.py` and
`engine.py` contain **zero** raw channel references — they consume normalized
values (`p_fwd`, `z`, `op_state`). Raw names live only at the translation
boundary (`labview_map.py`, `push_ingest_dual.py`, `crio_source_record/*`). A VI
semantics change therefore lands in the mapping layer, not the physics, and the
`active_heating_s` fix in §2 survives any renaming because "forward power" is a
concept that exists under any naming.

**What was established before deferring** (re-check against the real VI):

- *`active_chamber`* — derive from **per-chamber forward power**, not hot/cold.
  Thermal lag means a chamber that finished minutes ago is still the hottest, so
  "hottest = active" points at the wrong chamber through every cooldown. Rule:
  active = chamber with `P_fwd` over threshold; if neither is powered, **latch the
  last powered one** rather than falling back to hottest.
- *`op_state`* — asymmetric between chambers on the current list. PL carries
  boolean phase flags (`PL_preprocess` / `PL_process` / `PL_postprocess`) plus
  pumps and pressure, so evacuate / seal-check / heat / cooldown are all
  observable without the state string. MT has two thermocouples and power only —
  heating / cooling / idle are inferable, evacuation and product handling are not.
- *`cycle_id`* — the weakest to derive, and the one to keep as a supplied ID if
  controls can produce any stable one. A batch boundary needs a **load/unload
  bracket**, not a power or thermal edge (a power edge cannot distinguish "batch
  finished" from "power cut mid-run" — the governing principle in `lifecycle.py`).
  PL has a real bracket: chamber pressure returning to atmosphere with pumps off
  means the chamber was opened and the charge changed. MT has no pressure or pump
  channel, so no physical batch signature. Note also that a derived counter is an
  ordinal local to an engine run — unlike a real ID it does not survive a restart,
  so it would need persisting.

---

## 4c. Accepted scope decisions (2026-08-23, owner)

**`cycle_id` may never exist — accepted, no code required.** The FSM does not need
an identifier, it needs a reset *edge*, and the planned operating mode supplies one
for free: each demo run is a single batch, and the rehearsal harness rebuilds the
engine on **every loop iteration** (`_build_engine` sits inside the driver's `while`
loop), so charge mass re-seeds, energy zeroes and `q_scale` resets automatically
with no ID involved.

Measured consequence **if** an engine ever persists across batches with no reset
edge (four consecutive batches, `cycle_id=None`, no reset firing):

| batch | charge_mass | energy_wh | active_heat_s |
|---|---:|---:|---:|
| 1 | 0.9958 | 32.8 | 60 |
| 2 | 0.9915 | 66.1 | 120 |
| 3 | 0.9871 | 99.4 | 180 |
| 4 | 0.9827 | 132.8 | 240 |

Charge mass decays monotonically and never recharges (`reset_cycle()` is what calls
`model.recharge()`), so the mass-flow model eventually believes there is no
feedstock; energy and heating time become lifetime totals and
`energy_efficiency_g_per_wh` trends to zero. **This bites only on live continuous
operation across multiple batches in one persistent engine** — not on any run
described above.

If that becomes the operating mode, the fix is a derived boundary — **cold dwell
then reheat**, which is robust against the case the design warns about (a power cut
does not cool the bed to ambient, an unloaded chamber does and stays there). It
belongs in the **engine**, never the gateway, whose stated invariant is that it
fabricates no values.

**Live → scenario switching does not require dropping the live feed.** The
rehearsal profiles are standalone engines on `8177`–`8181` with `--feed harness`;
they never touch the gateway, `9070`, or the live path, and bind separate labeled
Convene rehearsal identities. Run them alongside live data.

**Unplugging the Ethernet is safe, and is the right tool for demonstrating
loss-of-data on the live path.** Verified: with the adapter reading `Disconnected`,
`192.168.1.1:9070` stayed bound and `/health` kept serving — because the NIC address
is **static** (`PrefixOrigin: Manual`). It is an *ungraceful* drop (no FIN), caught
by half-open detection plus the 15 s idle timeout; queued frames stay durable and
the cRIO reconnects on its own. **If that interface is ever moved to DHCP this stops
being true** — the address would vanish on link-down and the bind would break.

Rejected alternatives: stopping the gateway task is the genuinely graceful shutdown
but makes `/health` vanish (connection refused rather than stale), which is the
opposite of the loss-of-data signature; a firewall block will not reliably tear down
an already-established connection and muddies the guarded firewall audit.

---

## 5. Still open

| # | Item | Owner | Blocking |
|---|---|---|---|
| 1 | ~~`active_heating_s` / `S_Restart` semantics~~ — **resolved** by measuring forward power instead of op_state (§2) | — | closed |
| 2 | ~~Convene `gw_` binding not live~~ — **PROVEN 2026-08-23** on the live gateway (§3c); runtime config already had `convene_enabled: true` (repo templates ship `false` by design) | — | closed |
| 3 | Convene backend Firestore composite index over `machineId`/`status`/`createdAt` — heartbeat returns HTTP 500; `gw_` publish itself is unaffected | Convene backend | external |
| 4 | **27 raw `vars` names unconfirmed against a real cRIO frame** (GO_LIVE §9.5); Mod2 semantic aliases withheld pending the approved profile | controls | first live frame |
| 5 | **Signed maps UNSIGNED** — `cycle_id`, `source_op_state`, `active_chamber` and every raw channel are placeholder/unratified | controls | Gate 1 |
| 5b | ~~159 persisted dead-lettered frames~~ — **accepted 2026-08-23**: old frames are not of interest provided new ones publish, and the live probe delivered clean (`delivered 1, failed 0, dead_lettered_session 0`). Data left in place rather than purged; purge is a separate explicit action | — | closed |
| 6 | ~~Loss-of-data one-command target~~ — **done**, `loss-of-data` profile on 8181 | — | closed |
| 7 | `deploy\Install-ReclaimLiveTwin.ps1` does not exist; the runsheet path is what executes today | installer scope §E.3 | — |

**Gate status unchanged by this session:** 0 open · 1 open (worksheet unsigned) ·
2 done · 3 open (VI evidence + countersign owed) · 4 pending Phase B + explicit go ·
5 (fault/restart acceptance) pending Gate 4.

Note the coupling: §2, and items 4 and 5, are all the same root cause — **the cRIO
interface is not ratified.** The lifecycle FSM's state vocabulary, the channel
mapping, and the restart semantics all resolve together the moment Gate 1 is
signed against a real frame.

**Standing status: labeled engineering shadow — NO-GO for any production claim.**
