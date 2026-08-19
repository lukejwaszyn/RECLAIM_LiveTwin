# RECLAIM LiveTwin Convene Integration and Mission-Operations Recap

> **Evidence window:** 2026-08-18 through 2026-08-19 UTC
> **VM registration:** `reclaim-engine-2`
> **Status:** VM ingestion-to-Convene sensing path proven; platform-ID binding and visible dashboard configuration remain

## Executive outcome

The Windows Server 2025 VM now runs the RECLAIM production ingestion engine and
the independent Convene state bridge as persistent `LocalService` services. The
VM-specific Convene agent runs headlessly as a `SYSTEM` startup task and includes
the bridge's atomically written `C:\ConveneAgent\sim_vars.json` object in its
heartbeat. Convene has sensed the resulting variables.

The correlated acceptance run proved all of the following:

- authenticated public telemetry entered through the Cloudflare HTTPS origin and
  production `POST /ingest`;
- the engine accepted monotonically sequenced live frames and exposed the same
  `run_id`, `source_id`, and final `seq` through authenticated loopback `/state`;
- the bridge published a flat, scalar-only object with no pre-existing `sim_`
  prefix;
- Convene added the expected single `sim_` namespace and sensed the variables;
- the bridge asserted `data_live=true` only while state was fresh; and
- after the source stopped, the same identity and sequence transitioned to
  `bridge_status=stale`, `STATE_STALE`, and `data_live=false` with an immediately
  expired lease.

This is a large integration milestone, but it is not the end of operator
acceptance. The sensed variables must still be bound by their Convene-generated
IDs, the visible displays must implement the full live-data predicate, and the
three isolated rehearsal profiles must be captured.

## Deployed provenance

| Component | Proven value |
|---|---|
| Engine source | `726804b012279a0f3c675c4d9d3e76b16cf18d46` |
| Bridge source | `1d7512346806d994cd95a1b485f4f500f650286d` |
| Engine service | `RECLAIMIngestEngine`, `NT AUTHORITY\LocalService`, Automatic |
| Bridge service | `RECLAIMStateBridge`, `NT AUTHORITY\LocalService`, Automatic |
| Convene task | `ConveneAgent`, `SYSTEM`, ServiceAccount, Running |
| Engine listener | `127.0.0.1:8078` only |
| WinSW | `3.0.0+a6ba41681d84d84d95eb7a377c369d709e32225b`, net461 asset |
| WinSW SHA-256 | `91BCE26B4FA3A7534E7967C1804D7417737B7169014435E5B3B31924BF19F3EE` |
| Python | CPython `3.13.15` |
| uv | `0.11.21` |
| Cloudflare route | Quick tunnel to loopback `8078`; hostname is ephemeral and not a durable production DNS decision |
| Desktop streaming | Disabled |

The scalar-state release deployment also proved that the engine credential,
durable identity state, and bridge read credential hashes remained unchanged.
The engine restored its active run identity after service re-registration.

## Acceptance evidence

### Public engine harness

The public red-team harness reported `20/20 checks passed`.

| Boundary | Correlated evidence |
|---|---|
| Post-harness state | `2026-08-18T17:57:38.0412939Z` |
| Run | `acc-7f2060d1` |
| Source | `cRIO-accept` |
| Sequence | `29` |
| Mode/status | `live` / `accepted` |
| State age | `583 ms` |

Restart persistence was independently proven with run
`persistence-232830f27a2d4c0ebd1b75256c1de250`, source
`vm-persistence-proof`, and sequence `900001`: the first frame was accepted, the
same frame was a duplicate after restart, the active run was restored, and the
state-file hash was stable.

### Final engine-to-Convene live proof

| Field | Live boundary |
|---|---|
| Timestamp | `2026-08-19T01:09:53.3872841Z` |
| Run | `convene-live-b7856411f837` |
| Source | `vm-convene-bridge-proof` |
| Engine sequence | `50` |
| Bridge sequence | `50` |
| Engine state age | `960 ms` |
| Bridge status | `ok` |
| Data live | `true` |
| Bridge lease | valid through `2026-08-19T01:09:58.124Z` |
| File contract | flat scalars only; zero pre-existing `sim_` prefixes |

### Fail-closed expiry proof

| Field | Expired boundary |
|---|---|
| Timestamp | `2026-08-19T01:10:09.5481142Z` |
| Run/source/sequence | same correlated identity, sequence `50` |
| Bridge status | `stale` |
| Error code | `STATE_STALE` |
| Data live | `false` |
| Observed/valid-until | both `2026-08-19T01:10:08.187Z` |
| Services/task | engine Running; bridge Running; Convene agent Running |

## Root causes closed during deployment

1. **WinSW service re-registration.** Finalized XML was changed after initial
   WinSW installation. WinSW's restricted-account refresh path then failed to
   reopen its own service with `Access is denied`. Re-registering the service
   from the finalized XML resolved the problem without elevating the runtime
   identity.
2. **Writable log paths.** Both wrappers now declare dedicated log directories
   writable by `LocalService` rather than relying on protected service folders.
3. **Convene scalar contract.** `/state` leaked the structured `events` array even
   though the documented surface is flat. Release `726804b...` keeps event arrays
   in `/history` and publishes only scalar/null `/state` values; scalar
   `event_count` and `last_event` remain available.
4. **Optional nulls.** The bridge omits optional null values rather than sending
   values Convene cannot ingest.
5. **Windows atomic reads.** Tests now accept the real, transient Windows
   sharing/not-found race while still requiring every successful read to be a
   complete JSON document.

## Mission-operations display decision

Use progressive disclosure. Do not place every sensed variable on one screen.
The top-level view should answer four questions immediately:

1. Is this data live and trustworthy right now?
2. What state and chamber are active?
3. Are measured temperatures, power, and pressure behaving safely?
4. Is the advisory engine asking for operator attention?

### Screen 1: mission overview — always visible

These are the highest-value variables for mission leadership and the primary
operator. Bind all of them by Convene variable ID.

| Variable | Type | Recommended presentation | Operational value |
|---|---|---|---|
| `sim_data_live` | boolean | dominant green/gray-red status lamp | Primary bridge assertion; never sufficient by itself |
| `sim_bridge_status` | string | status badge | Distinguishes `ok`, `stale`, schema, identity, auth, and write failures |
| `sim_bridge_error_code` | string | compact fault text | Stable diagnostic classification |
| `sim_state_age_ms` | number | age counter with threshold color | Immediate freshness evidence |
| `sim_bridge_valid_until` | string/UTC timestamp | lease countdown or expiry badge | Independent protection against a frozen last-good file |
| `sim_mode` | string | small badge; require `live` | Prevents rehearsal/synthetic data from appearing live |
| `sim_ingest_status` | string | small badge; require `accepted` | Prevents rejected/duplicate state from appearing current |
| `sim_op_state` | string | large state label | Authoritative source operational state |
| `sim_active_chamber` | string | PL/MT/NONE selector | Directs operator attention to the active chamber |
| `sim_PL_advisory_severity` | string | PL severity badge | Advisory escalation summary |
| `sim_MT_advisory_severity` | string | MT severity badge | Advisory escalation summary |
| `sim_cmd_mode` | string | advisory command-mode label | Shows `TRACK`, `LIMIT`, or safe-state recommendation; no hardware authority |
| `sim_cmd_power_setpoint_W` | number | recommended-power readout | Transparent advisory output |
| `sim_cmd_safe_state_armed` | boolean | amber/red advisory lamp | Predictive-engine recommendation only; not the physical interlock |
| `sim_last_event` | string | latest-event banner | Compact causal context without a nested event array |

The overview's displayed **DATA IS LIVE** state must be a derived predicate:

```text
sim_data_live == true
AND sim_bridge_status == "ok"
AND sim_mode == "live"
AND sim_ingest_status == "accepted"
AND sim_state_age_ms <= sim_freshness_limit_ms
AND current_utc <= sim_bridge_valid_until
```

If Convene cannot compare its own current UTC time with the lease timestamp, the
dashboard must remain labeled `DATA NOT LIVE` until that capability is supplied.

### Screen 2: chamber operations — one card for PL and one for MT

Bind the following suffixes for both `sim_PL_*` and `sim_MT_*`. The active card
should be visually emphasized, but the inactive card remains visible because
cross-chamber sensing and estimator state are mission-relevant.

| Suffix | Type | Presentation | Why it belongs on the operator screen |
|---|---|---|---|
| `op_state` | string | state label | Chamber-local state |
| `sensor_valid` | boolean | validity lamp | Prevents estimates from being read without sensor context |
| `T_bed_meas` | number, K | value + trend | Primary measured process temperature |
| `T_bed_est` | number, K | value + trend overlaid with measurement | Core twin estimate |
| `T_bed_sigma` | number, K | uncertainty band | Communicates estimator confidence |
| `T_wall_meas` | number, K | value + trend | Measured chamber-wall condition |
| `T_wall_est` | number, K | value + trend | Wall-state estimate |
| `P_fwd` | number, W | value + trend | Applied microwave power |
| `P_refl` | number, W | value + trend or reflected/forward ratio | Coupling and reflected-power awareness |
| `P_chamber` | number, kPa | value + trend | Canonical chamber pressure |
| `thermal_margin_K` | number, K | margin gauge | Bed-temperature margin to configured limit |
| `wall_margin_K` | number, K | margin gauge | Wall-temperature margin to material limit |
| `advisory_action` | string | operator-action text | Direct recommendation, explicitly advisory |
| `advisory_message` | string | expandable rationale | Why the severity/action was selected |

### Screen 3: engineering diagnostics — bind, but do not lead with them

These fields are useful to thermal, controls, and data engineers. They should not
be presented as validated mission probabilities or independent safety signals.

| Per-chamber suffix | Type | Engineering use / caveat |
|---|---|---|
| `model_trust` | number, 0–1 | Model-consistency indicator; show beside any forecast |
| `nis` | number | Innovation-consistency diagnostic |
| `nis_anomaly` | boolean | Statistical inconsistency flag |
| `cusum` | number | Slow-drift indicator |
| `q_scale` | number | Adaptive process-noise behavior |
| `eta_obs` | number | Observed coupling/absorption diagnostic |
| `beta_est` | number | Estimated feedback coefficient |
| `unexplained_rate_Kps` | number | Model-independent heating-rate residual; timing assumptions require review |
| `t_star` / `t_star_sigma` | number, s | Forecast lead-time and uncertainty; advisory only |
| `t_wall_cross` | number, s | Wall-limit lead-time estimate; advisory only |
| `p_event` | number | **Uncalibrated ensemble-risk indicator; never label as probability** |
| `seal_residual` | number | Engineering-only until the documented pressure-unit/reset issue is closed |
| `semenov_margin` | number | Thermal-stability model diagnostic |
| `charge_mass_kg` | number, kg | Model mass state |
| `consumed_energy_wh` | number, Wh | Cycle energy accounting |
| `energy_efficiency_g_per_wh` | number | Efficiency trend |
| `mass_efficiency` | number | Recovery performance trend |

### Screen 4: provenance and audit

These values should be bound and retained even if most are collapsed in normal
operations:

- strings: `sim_run_id`, `sim_source_id`, `sim_cycle_id`, `sim_ts_source`,
  `sim_ts_engine`, `sim_schema_version`, `sim_engine_source_sha`,
  `sim_bridge_source_sha`, `sim_bridge_instance_id`, `sim_environment`;
- numbers: `sim_seq`, `sim_ingest_age_ms`, `sim_event_count`, `sim_gap_count`,
  `sim_freshness_limit_ms`; and
- string/UTC: `sim_bridge_observed_at` and `sim_bridge_valid_until`.

This screen is essential during anomaly review because it proves exactly which
source, run, sequence, engine build, and bridge build produced the displayed
state.

## Binding procedure and ID worksheet

Convene assigns platform-specific IDs to sensed variables. Names are not a safe
substitute for those IDs. Export or copy the sensed-variable list with both ID and
name, then populate an implementation worksheet with:

| Convene ID | Variable name | Type | Screen/widget | Bound element | Verified live | Verified stale |
|---|---|---|---|---|---|---|
| _pending_ | `sim_data_live` | boolean | Overview/live lamp | _pending_ | no | no |
| _pending_ | `sim_bridge_status` | string | Overview/status | _pending_ | no | no |
| _pending_ | `sim_state_age_ms` | number | Overview/age | _pending_ | no | no |
| _pending_ | `sim_bridge_valid_until` | timestamp string | Overview/lease | _pending_ | no | no |
| _pending_ | `sim_run_id` | string | Audit | _pending_ | no | no |
| _pending_ | `sim_source_id` | string | Audit | _pending_ | no | no |
| _pending_ | `sim_seq` | number | Audit | _pending_ | no | no |

After binding, rerun `windows-vm/Test-ConveneLiveExpiry.ps1` and capture the same
run/source/sequence on the visible overview. The final UI acceptance evidence must
show both `DATA IS LIVE` during the stream and `DATA NOT LIVE` after expiry.

## Remaining work and explicit limits

- Bind sensed variables by their Convene IDs and implement the four-screen layout.
- Capture visible Convene correlation and the full lease-aware live predicate.
- Replace the ephemeral quick tunnel with an approved named route/DNS decision for
  durable operations.
- Run and capture nominal (`8177`), power-outage (`8178`), and lunar (`8179`)
  isolated rehearsal profiles. Never route these ports into production bindings.
- Confirm VM-disk persistence across the outer Kubernetes/VM lifecycle.
- Keep all predictive outputs advisory. No script or Convene binding created here
  has physical interlock or hardware command authority.

## Published operator scripts

The proven, credential-safe PowerShell workflows are documented in
[`windows-vm/README.md`](windows-vm/README.md). No token-bearing Convene installer,
secret file, or failed exploratory script is committed.
