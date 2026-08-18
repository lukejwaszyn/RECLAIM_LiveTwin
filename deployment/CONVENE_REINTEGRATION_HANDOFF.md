# Convene Reintegration — Repository Proof and Operator Checkpoint

**Date:** 2026-08-17
**Status:** repository side proven; no external Convene mutation performed

The live predictive-engine guest is Windows Server 2025 in Kubernetes-managed
cloud infrastructure. Its independent Windows state bridge writes
`C:\ConveneAgent\sim_vars.json` for the existing VM Convene agent. The Windows 10
gateway laptop remains the separate `gw_` audit source.

## Proven repository contract

The cloud dual engine is the future single writer of the live `sim_` set. Its
read surface is `GET /state`; the gateway laptop remains a separate, read-only
audit machine whose local `GET /latest` frame is published only as `gw_`.

Automated coverage in `cloud_engine/tests/test_convene_binding_contract.py` and
`pi_gateway/tests/test_framer_contract.py` proves:

- typed schema, mode, accepted status, run/source identity, source timestamp,
  sequence, active chamber, system/chamber state, ingest freshness, advisory,
  and command-representation fields;
- `state_age_ms` is declared by the manifest and calculated when `/state` is
  read, rather than frozen at ingest time;
- the gateway frame preserves the raw LabVIEW values and never creates `sim_`
  keys;
- cloud normalization converts °C→K and mbar→kPa; and
- shared SSMG forward/reflected power is attributed only to the declared active
  chamber.

The current `/state` contract publishes the plastics bed bank as the aggregate
`PL_T_bed_meas`. It does not publish individual `PL_T_bed_tc1..4` fields. The
gateway mapping has therefore been corrected: the audit view must compare the
converted mean of `gw_PL_bottom1..4` to `sim_PL_T_bed_meas`.

## Rehearsal isolation contract

Use three separate non-live identities and prefixes:

| Experience | Identity | Allowed prefix | Source |
|---|---|---|---|
| Nominal Earth-lab | `reclaim-rehearsal-nominal` | `rehearsal_nominal_` | `127.0.0.1:8177` |
| Power-outage Earth-lab | `reclaim-rehearsal-outage` | `rehearsal_outage_` | `127.0.0.1:8178` |
| Nominal lunar-surface | `reclaim-rehearsal-lunar` | `rehearsal_lunar_` | `127.0.0.1:8179` |

These identities may read only their listed loopback synthetic service. They
must not receive a production ingest/read token, tunnel route, `sim_` binding,
or `gw_` binding. Synthetic services implement GET-only demonstration routes
and do not expose `POST /ingest`.

The future live topology remains exactly one `sim_` publisher reading the
production cloud `/state`, plus one separate `gw_` audit machine reading the
gateway `/latest`. Never run a rehearsal, legacy publisher, CSV importer, or
second bridge against either set.

## Required display rule

The binding/view must compute one fail-closed display predicate:

```text
DATA IS LIVE only when
  sim_data_live == true
  AND current_utc <= sim_bridge_valid_until
  AND sim_mode == "live"
  AND sim_ingest_status == "accepted"
  AND sim_state_age_ms <= APPROVED_FRESHNESS_LIMIT_MS
otherwise show "DATA NOT LIVE"
```

`APPROVED_FRESHNESS_LIMIT_MS` remains an operator/controls decision and is not
invented here. The lease comparison is mandatory: `sim_data_live` alone is not
sufficient because the last complete JSON file may remain readable if a bridge
write fails. `cmd_*` and `/command` remain advisory representations only. No
gateway, PLC, cRIO, Convene action, or actuator may consume them as authority.

## Known field and geometry gaps

- The actual cRIO `vars` key set is still unverified; confirm it from the first
  real `/latest` frame before enabling strict field mapping.
- The plastics individual TC values have no one-to-one cloud `/state` fields;
  only the normalized bank aggregate is available today.
- No proprietary Convene export/schema exists in this repository, so no import
  artifact has been invented.
- The `.stp` model and variable-to-element mapping evidence are absent. The 3D
  view remains a read-only future consumer and is not claimed complete.
- The live cloud hostname, ingest/read tokens, external rehearsal machines,
  agent permissions, and approved freshness limit are not repository-owned.

## External operator checkpoint — explicit approval required

Do not perform this checkpoint until the user authorizes external Convene
mutation in the current session.

1. Create the three rehearsal machines/identities above with only their matching
   `rehearsal_*` prefix and loopback source.
2. Build three visibly labeled rehearsal views and implement the fail-closed
   display predicate above.
3. Confirm no rehearsal field begins with `sim_` or `gw_`, and no rehearsal
   collector has a production token or URL.
4. Capture: machine IDs, exported field lists, screenshots of each label and
   `DATA NOT LIVE` behavior, collector URLs with credentials redacted, and the
   single-writer list for `sim_` and `gw_`.

Expected result: three isolated rehearsal views receive only synthetic GET data;
the live `sim_` namespace and gateway `gw_` audit machine are unchanged.

Rollback: disable/delete only the new rehearsal collectors and bindings, verify
their fields stop advancing, and re-capture the unchanged `sim_`/`gw_` writer
list. Do not alter the live publisher, gateway agent, tunnel, tokens, or hardware.
