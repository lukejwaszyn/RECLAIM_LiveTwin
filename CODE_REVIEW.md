# RECLAIM Live Twin — Engineering & DevOps Review

**Reviewed:** 2026-08-10 · full repo (pi_gateway, cloud_engine, docs, convene)
*(Editorial note 2026-08-15: the Unreal visualization path was dropped; consumer
references below now read as the Convene-native `.stp` visualization, which is
the single read-only consumer of `/state`.)*
**Method:** every file read; suspected defects reproduced by executing the actual code (both test suites pass; the confirmed bugs below are all in paths the tests don't cover).

---

## 1. What this codebase does well

**The architecture documents are the strongest part of the repo.** `docs/RECLAIM_Live_Telemetry_Architecture.md` is a real production contract: explicit schemas for inbound telemetry and outbound state, a validation table, an operational-state authority model (`op_state` vs `PL_op_state`/`MT_op_state`), single-writer publisher policy, migration gates, and rollback. The preflight doc's "reconnaissance first, side-by-side, shadow run, then cutover" sequence is exactly how you deploy against a live plant.

**Sound structural decisions:**

- Clean seam separation: cRIO → laptop gateway (trusted LAN) → cloud (TLS) → consumer, with the gateway as the OT/IT boundary and the Convene-native `.stp` visualization as a strictly read-only consumer of one `/state` record.
- `labview_map.py` isolates all real-world naming/unit translation (degC→K, mbar→kPa, shared-SSMG power attribution) in one auditable adapter, with honest inline REVIEW FLAGS (LV-1..LV-5) documenting known modeling gaps instead of hiding them.
- Durable store-and-forward on the Pi: SQLite persist-before-publish, ack-only-on-delivery, drop-oldest with a drops counter. Correct at-least-once shape.
- Provenance-tagged parameters (`Tagged` value/unit/source), CAD-derived geometry with the end-cap loss-area fix (F5), and a self-describing manifest with SysML entity IDs — genuinely good MBSE hygiene.
- The estimation stack is well reasoned: vendored auditable UKF, NIS/CUSUM consistency monitoring, a filter-independent "unexplained heating rate" residual specifically because adaptive Q could mask an exotherm, equal-weight sigma-point forecasting with a documented rationale for rejecting the degenerate UKF weights, and an advisor/interlock partition that keeps the model advisory-only.
- Docstrings throughout explain *why*, not just what. The systemd units include basic hardening (`NoNewPrivileges`, `ProtectSystem=strict`).

**Architecture detectability: high.** A new engineer can reconstruct the full topology from the README + architecture doc alone, and the code matches the documented layering (config→plant→estimator→forecaster→anomaly→engine→service). Two gaps: the docs never state that engine physics runs on a fixed 1 s step decoupled from real frame timestamps (you only learn this from `ChamberEngine.step`), and the README's claim that the release "excludes synthetic emitters" is contradicted by `service.py`/`harness.py` shipping inside the package (see D11).

---

## 2. Confirmed defects (reproduced by execution)

### Critical — will wedge or corrupt the live pipeline

**C1. Post-outage deadlock: stale buffered frames permanently block the queue.**
Pi buffers during a link outage (by design). Cloud production rejects any frame older than 15 s (`timestamp_stale`, `push_ingest_dual.py:264`). The batch response is HTTP 400 when *any* line is bad (`:398`); `HttpsTransport.deliver` treats non-2xx as total failure and never acks (`publisher.py:56`). After any outage >15 s the head of the queue is permanently stale → publisher retries the same batch forever → **no telemetry ever flows again** until a human intervenes. Reproduced: 60 s-old frame → `timestamp_stale`. The two subsystems' core design assumptions (buffer-and-retry vs freshness window) directly contradict each other. Fix: per-frame accept/reject in the response with the Pi acking rejected-as-final frames, or return 200 with per-line status; mark stale frames accepted-but-not-stepped, or drop them Pi-side before send.

**C2. Pi reboot bricks ingest: `run_conflict` with no recovery path.**
Cloud pins `active_run_id` to the first-seen run and rejects any other in production (`:287`), forever — there is no run-supersession rule, no admin endpoint, no TTL. The Pi generates a fresh `run_id` every service start. So any Pi restart/reboot → every subsequent frame rejected → combined with C1, the queue also wedges. Worse: leftover buffered frames from the *old* run deliver first after a cloud restart and re-pin the old run, locking the new run out. Reproduced. Fix: accept a new run_id that arrives with fresh timestamps (log a `RUN_SUPERSEDED` event), or add an authenticated run-reset control.

**C3. No sequence-ordering enforcement — the documented contract is not implemented.**
The architecture doc requires "reject older sequences, record gaps." The code only dedupes exact `(run_id, source_id, seq)` tuples in a 20 000-entry FIFO (`:296-304`). Reproduced: after seq 101, seq 50 was **accepted and published** — `/state` regressed to older data. Also: gaps are not recorded, and the 20 k dedup window means late retries beyond ~20 k frames re-step the estimator. Fix: track `last_seq` per (run, source); reject/flag regressions; emit a gap counter.

**C4. Dedup does not survive a cloud restart → estimator double-stepping.**
`_seen_sequences` is in-memory only. Cloud service restart + Pi at-least-once retry = the same frames re-step both estimators — precisely what the preflight's duplicate gate claims to prevent. Reproduced. Fix: persist (run_id, last_seq) or derive idempotency from C3's ordering check (monotone seq makes replay harmless).

**C5. Seal-leak detection is dead: kPa fed into a Pa model.**
`labview_map` converts chamber pressure to kPa (`PL_P_chamber ≈ 101.3`). `SealMonitor` expects Pa (`p0=101325`, `p_floor=80`, `resid_limit=500` — `anomaly.py:107`). Reproduced: residual ≈ **−94 694** during a simulated evacuation — meaningless, never breaches, and publishes garbage into `/state` (outside the manifest's declared −1000..10000 Pa range). Additionally `SealMonitor.t0` latches on the *first frame ever seen*, not at `S_Evacuate` entry, so the expected pump-down curve is phase-shifted even with correct units. The vacuum-integrity advisory (`WARNING: Inspect vacuum seals`) can never fire. Fix: convert units at the seal-monitor boundary, and reset `t0` on entry to `S_Evacuate`.

**C6. Fabricated 300 K measurements step the metals estimator.**
`_bed_temp`/`_wall_temp` (`push_ingest_dual.py:97-114`) fall back to **300.0 K defaults** when a chamber has no wired sensors. The current stream's MT thermocouples read 0.0 → dropped as unwired by `labview_map` → the MT engine is fed a fabricated 300 K "measurement" every frame and publishes `MT_T_bed_meas=300.0`, `MT_T_bed_est≈299.7` as if real. Reproduced. This directly violates the contract's "non-finite values are omitted, never replaced with a made-up number" and will paint false-nominal metals data on operator dashboards. Fix: skip the estimator update (predict-only) or publish null + `SENSOR_MISSING` event when a bank has no valid reading.

**C7. Explicit `active_chamber: NONE` from the sequencer is overridden to MT.**
The envelope value is injected as a *hint* (`raw["active"]`), but `labview_map.active_chamber` only honors hints in `("PL","MT")`; `NONE` falls through to inference, where a **missing `MW_RF` defaults to RF-on** (`labview_map.py:110`) → returns "MT". Then `combined["active_chamber"] = active or meta[...]` prefers the inference. Reproduced: sequencer says NONE, `/state` says MT. Violates operating rule "the cRIO sequencer is authoritative." Fix: honor `NONE` as authoritative; treat missing `MW_RF` as RF-off; keep inference as a logged plausibility check only.

### High — operational failures waiting to happen

**H1. Engine physics ignores real time: fixed dt = 1.0 s per frame.**
`ChamberEngine.t += 1.0` and `FilterConfig.dt=1.0`; frame timestamps are validated but never used for integration. If the cRIO streams at 2 Hz (or irregularly, or after buffered burst delivery at ~100 frames/s), the thermal model integrates at the wrong rate — temperatures ramp 2× too fast/slow, `t_star`/`t_wall_cross` lead times and the `unexplained_rate_Kps` slope (labeled K/s but actually K/frame) are all wrong. For a *live* twin this undermines every forecast. Fix: dt from successive `ts` deltas (bounded), and use it in `ukf.predict`, mass-flow advance, and the residual-window slope.

**H2. Half-open TCP from the cRIO permanently stalls the receiver.**
`Receiver` accepts one connection (`listen(1)`) and `_serve` loops on 1 s recv timeouts forever; a cRIO power-cycle that never sends FIN leaves the old socket half-open, so the loop never exits and the reconnecting cRIO waits in the backlog indefinitely. No TCP keepalive, no idle-connection timeout, no "no data in N s → drop connection" guard. Data silently stops until someone restarts the service. Fix: track last-data time and close after an idle limit; enable `SO_KEEPALIVE`.

**H3. Poison frame = head-of-line blocking on the Pi (no dead-letter path).**
Any frame the cloud permanently rejects (bad state string, malformed value) makes its whole batch fail 400 forever (same mechanics as C1, but triggered by a single bad frame in normal operation). The queue only clears once 500 000 frames accumulate and drop-oldest evicts it — at 1 Hz, ~5.8 *days* of outage. Fix: per-frame ack (C1) plus a bounded retry count → dead-letter table.

**H4. GET endpoints are unauthenticated and CORS-open; the docs contradict the code.**
The bearer token guards only `POST /ingest`. `/state`, `/history` (200 frames), `/manifest`, `/command` are world-readable with `Access-Control-Allow-Origin: *`. Meanwhile the preflight doc (a) curls GET endpoints *with* an Authorization header the server never checks, and (b) says to configure the proxy to "pass only `POST /ingest`" — which would break the Convene publisher and its `.stp` visualization, whose entire integration is `GET /state` through that ingress. Someone will "fix" this in the field ad-hoc. Decide and document: either token-protect GET or state explicitly that GET is network-restricted (Cloudflare Access/allowlist), and route consumers accordingly. Token comparison should also be constant-time (`hmac.compare_digest`).

**H5. Ingest token exposed on the process command line.**
`reclaim-ingest.service` passes `--ingest-token ${RECLAIM_INGEST_TOKEN}` in `ExecStart` — visible to every local user via `ps`/`/proc`, contradicting the env.example's own warning ("do not place it in a systemd unit"). The code already reads the env var; drop the CLI flag from the unit.

**H6. Pi systemd unit will crash-loop on first boot and points at the example config.**
(a) `Environment=...config.example.yaml` — the service runs the *example* file (transport=console → live telemetry printed to journal, never sent to cloud) while docs say to copy config to `/etc/reclaim-edge/`. (b) `ProtectSystem=strict` + `ReadWritePaths=/var/lib/reclaim-edge` but nothing creates that directory; `Buffer`'s `mkdir` of `/var/lib/reclaim-edge` is blocked by the sandbox → startup crash loop. Add `StateDirectory=reclaim-edge` and point `RECLAIM_EDGE_CONFIG` at the real config path. Also the docs reference `edge_gateway/config.example.yaml`; the folder is `pi_gateway/` (and the unit's WorkingDirectory says `edge_gateway`) — naming drift across three places.

**H7. Silent misconfiguration: missing config file falls back to defaults.**
`Config.load` returns all-defaults if the YAML path doesn't exist or pyyaml isn't installed (`config.py:80`). A typo'd path yields a healthy-looking gateway in `console` transport publishing nothing to the cloud. Production should fail fast when the configured file is absent. Same class of issue: `EnvironmentFile=-` (optional) on the cloud unit turns a missing secrets file into an argparse crash-loop instead of a clear error.

### Medium

**M1. `--feed replay` crashes: `service.py` imports `.ingest`, which doesn't exist in the package.** Latent `ImportError` on a documented CLI path.

**M2. Frame counters and `last_ingest` race under `ThreadingHTTPServer`.** Validation/dedup and estimator stepping happen under two separate lock acquisitions, and the handler reads shared `pe.last_ingest` after `ingest()` returns — concurrent POSTs can interleave (mis-counted duplicates, out-of-order stepping). Do dedup+step under one lock, and have `ingest()` return its own status instead of the handler reading shared state.

**M3. `except Exception: bad += 1` swallows engine errors invisibly** (`push_ingest_dual.py:392`) — no log, no error entry. A systematic engine crash looks identical to a malformed frame. Also note C4 interaction: a frame that *fails mid-step* was already recorded in `_seen_sequences`, so its retry is treated as a duplicate — the frame is silently lost.

**M4. Forecaster physics diverges from the plant it claims to mirror.** `_event_time` captures a constant `c_bed` and omits both the mass-flow capacity collapse (`c_bed_eff`) and the pyrolysis endotherm `q_rxn` — the two effects the massflow module says dominate late-cycle plastics behavior (C_b falls ~45 %). Runaway lead times for PL are biased late in exactly the regime that matters; `time_to_target` *does* use the live model, so the two forecasts are mutually inconsistent. The docstring's claimed "parity test" is not in this repo.

**M5. Log flood at telemetry rate.** With `strict_fields: false` (the documented starting configuration), `Framer.build` emits an "unknown field preserved" warning for *every raw LabVIEW field of every frame* (~27 warnings/frame; at 1 Hz ≈ 2.3 M log lines/day) — filling the Pi SD card and burying real warnings. Warn once per field name.

**M6. Receiver/publisher thread death is silent.** If `Receiver.run` throws (port in use) or `MqttsTransport.__init__` fails (broker down at boot — it connects in the constructor), the thread dies but main keeps printing health lines; the status endpoint stays green. Supervise thread liveness in the health loop. Also `paho-mqtt>=1.6` with `mqtt.Client()` breaks under paho 2.x (callback API version now required) — pin `<2.0` or update the call.

**M7. Pi restart with a fixed `run_id` resets `seq` to 1.** `Framer._seq = itertools.count(1)` is memory-only. The config explicitly supports resuming a controlled run (`run_id` set); after restart, seqs collide with already-seen tuples → frames eaten as duplicates (or, with C3 fixed, rejected as regressions). Persist the seq high-water mark next to the buffer, or forbid fixed run_id.

**M8. CSV fallback in `parse_line` produces all-string values** ("100.2", "true") with no coercion; downstream `float()` conversions partially save this, but booleans become truthy strings and `_temp_K("true")` → None silently. Either coerce types or drop the CSV path.

### Low / polish

- `manifest.model_ref` says `RECLAIM_MBSE_v4` (thread.py) while config docs say v5 — traceability drift.
- `_temp_K` treats exact 0.0 °C as unwired (documented LV-5) — acceptable for this lab, but it's also load-bearing for C6; note the coupling.
- `Handler` uses HTTP/1.0 (no `protocol_version = "HTTP/1.1"`) — a new connection per Pi batch POST.
- README says the release "intentionally excludes synthetic emitters," yet `service.py` ships a self-driving synthetic scenario server on 0.0.0.0:8077 with no auth — the exact hazard the single-writer policy warns about. If it must ship (push_ingest_dual imports `TwinStateService` from it), strip its `main()`/harness driver.
- `verify = cfg.tls_ca or cfg.verify_tls`: setting `verify_tls: false` while `tls_ca` is set silently keeps verification on (fine), but `verify_tls: false` alone disables TLS verification with no log warning.
- Pi status server binds 127.0.0.1 (good), but `/latest` re-serves raw frames through whatever tunnel is used — document that the tunnel must be authenticated (the doc mentions this only implicitly).
- Contract tests are thin vs. the doc's own gate list: no stale-timestamp test, no seq-regression test, no run-transition test, no auth test, no batch/HTTP-level test. C1–C7 all live in that gap.

---

## 3. Priority fix order

1. **C1 + H3** — per-frame ack contract between publisher and `/ingest` (this one change removes both wedge modes).
2. **C2** — run supersession rule (unblocks every Pi reboot).
3. **C3 + C4** — per-(run,source) monotone seq tracking, persisted; replaces the dedup dict.
4. **C6, C7, C5** — stop fabricated measurements, honor NONE, fix seal units (operator-facing correctness).
5. **H1** — real dt from timestamps (forecast validity).
6. **H2, H5, H6, H7** — deployment/ops hardening before the preflight is attempted.
7. Add contract tests for each of the above; the current suites pass while all seven critical/confirmed bugs are present.
