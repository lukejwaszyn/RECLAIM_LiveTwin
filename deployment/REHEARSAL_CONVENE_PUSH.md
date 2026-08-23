# Rehearsal Scenarios → Convene (push path)

> **Status:** gateway leg and the synthetic cRIO both implemented and proven
> locally 2026-08-23. What remains for the cloud leg is **VM-side configuration,
> not code** (§4).
> **Standing status unchanged: labeled engineering shadow — NO-GO for any
> production claim.**

## 1. Why this exists

Convene is designed to read the rehearsal services by *polling* them through
collectors delivered in the heartbeat response. That path is dead: the backend
lacks its `machineCommands` composite index, every heartbeat returns HTTP 500,
no `autoVars` are ever returned, and the agent therefore polls nothing. See
`CONVENE_FIRESTORE_INDEX_HANDOVER.md`.

Rather than wait on a backend fix we do not own, this inverts the direction and
**pushes** — the same direct `POST /machine/publish` technique the gateway's
`gw_` audit tap already proves under sustained load (450 frames, 0 failed). It
uses no collector, so the missing index cannot block it.

This is the technique borrowed from `gw_`, **not** the `gw_` namespace.

## 2. Isolation contract compliance

Rehearsal data is synthetic and must never be mistakable for live state. Per the
contract in `CONVENE_REINTEGRATION_HANDOFF.md`, each profile publishes under its
own non-live identity and prefix:

| Profile | Identity | Prefix | Source |
|---|---|---|---|
| `nominal` | `reclaim-rehearsal-nominal` | `rehearsal_nominal_` | `127.0.0.1:8177` |
| `power-outage` | `reclaim-rehearsal-outage` | `rehearsal_outage_` | `127.0.0.1:8178` |
| `lunar` | `reclaim-rehearsal-lunar` | `rehearsal_lunar_` | `127.0.0.1:8179` |

Enforced in code, as hard failures rather than warnings
(`cloud_engine/rehearsal_convene.py`):

- a prefix outside the `rehearsal_` namespace is rejected;
- any emitted name starting `sim_` or `gw_` raises, as defense in depth;
- the production gateway credential is refused by path;
- nulls, nested objects and non-finite floats are dropped, never coerced — a
  frozen loss-of-data rehearsal must read as stale, not as a last-good value.

**`loss-of-data` (port 8181) is deliberately refused.** The contract grants it no
identity or prefix, and inventing one nobody reviewed would defeat the point. Add
it to the contract table and to `PROFILES` before publishing it.

## 3. Running it

Start a scenario, then publish alongside it:

```powershell
.\cloud_engine\windows\start-rehearsal-scenario.ps1 nominal
.\cloud_engine\windows\start-rehearsal-convene-publisher.ps1 nominal -DryRun
```

`-DryRun` exercises the whole fetch → flatten → prefix path and prints the
variables while publishing nothing — it needs no credential and mutates nothing.
Use it to prove the mapping before any external Convene change.

To publish for real:

```powershell
.\cloud_engine\windows\start-rehearsal-convene-publisher.ps1 nominal `
    -Api https://<backend>/api `
    -Credential C:\ProgramData\RECLAIM\rehearsal\nominal.convene_agent.json
```

Proven locally 2026-08-23 against a live `nominal` scenario: 41 variables, all
`rehearsal_nominal_`-prefixed, 0 in a live namespace.

### Still required before real publishing

Creating the three rehearsal machines is an **external Convene mutation**, which
the reintegration handoff says must not be performed without explicit
authorization in-session. It has not been done. Each identity needs its own agent
credential, holding only its matching `rehearsal_*` prefix and loopback source —
never a production ingest/read token or tunnel route.

## 4. The cloud/VM leg — how it should be done

The intent is for rehearsal telemetry to also traverse the cloud the way live
telemetry does: gateway → VM `/ingest` → cloud engine → `/state` → bridge →
Convene. **The pipeline already supports this by design.**

Live telemetry enters at `pi_gateway/reclaim_edge/receiver.py`: a plain TCP
server that accepts the cRIO's connection and reads line-delimited JSON frames.
Nothing downstream of that socket — framer, buffer, publisher, VM `/ingest`,
dual engine, `/state`, bridge — knows or cares what produced the bytes.

So driving synthetic telemetry through the *identical* path needs exactly one new
component: a **synthetic cRIO** that connects to the gateway's listen port and
writes canonical frames. It requires no change to the scenario services, no new
seam in the engine, and no second copy of the pipeline.

Two things the design already handles, which is the strongest evidence this is
the intended route:

- **`mode: "harness"` is a first-class frame value.** `push_ingest_dual.py:457`
  accepts `live`, `harness`, `replay`, `legacy`. Synthetic input was anticipated.
- **Contamination is already fail-closed.** An engine started `--production`
  rejects any frame whose mode is not `live` (`push_ingest_dual.py:455`,
  `mode_rejected`). A synthetic `harness` frame therefore *cannot* enter the
  production engine or reach `sim_`, even by misconfiguration.

### The synthetic cRIO — built

`tools/synthetic_crio.py` drives `TruthPlant` and writes raw LabVIEW frames to
the gateway's TCP receiver, in the cRIO's own schema and units (degC/Torr, which
`labview_map` converts back to K/kPa). It sets **no** identity of its own: the
gateway assigns `run_id`, `seq` and `mode`, exactly as it does for real hardware.

```powershell
# Print frames without opening a socket:
.venv\Scripts\python.exe tools\synthetic_crio.py --dry-run --max-frames 5

# Drive a gateway configured mode: harness
.venv\Scripts\python.exe tools\synthetic_crio.py --scenario nominal --port 9070 --speed 2
```

Proven by `tools/tests/test_synthetic_crio.py` (8 tests) against the real
components, not restated copies of them:

- units round-trip through the actual `labview_map.normalize()`, with the
  four-TC mean recovering the true bed temperature;
- frames traverse a real `Receiver` over a real socket, and come out canonical
  with the gateway's own `mode: harness` stamp;
- a **non-production** `DualPushEngine` accepts a harness frame;
- a **`--production`** `DualPushEngine` refuses it — synthetic data provably
  cannot reach the live `sim_` namespace.

### What remains — VM-side configuration, owned by the engine owner

No further code is required. `cloud_engine` is the VM's software and is
**read-only from the gateway desktop**, so these are the owner's actions:

1. **A non-production engine instance** — its own port and `--state-file`,
   started *without* `--production`. Production `8078` is not a valid target,
   and the mode gate above enforces that independently of configuration.
2. **A second gateway instance configured `mode: harness`**, pointed at that
   engine's `/ingest`. The mode value already exists in `config.py:44`; nothing
   needs adding.
3. **A rehearsal bridge instance** reading that engine and publishing under the
   same `rehearsal_*` identities, so the cloud leg and the gateway leg agree.

Note this is *complementary to*, not a replacement for, §1-3. The scenario
services on 8177-8181 run their own estimator in-process and are consumed
directly by the push publisher. The synthetic cRIO is a second route that
exercises the real end-to-end pipeline instead of short-cutting it.

## 5. Files

| Path | Role |
|---|---|
| `cloud_engine/rehearsal_convene.py` | publisher, profile table, namespace guards |
| `cloud_engine/tests/test_rehearsal_convene_publisher.py` | 9 tests, all guards covered |
| `cloud_engine/windows/start-rehearsal-convene-publisher.ps1` | launcher |
