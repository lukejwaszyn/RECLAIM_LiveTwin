# RECLAIM three-endpoint integration handoff

> **Status:** authoritative endpoint-boundary handoff
> **Effective:** 2026-08-24
> **Live gateway:** Windows 10 desktop
> **Scenario host:** this MacBook
> **Overall physical/live status:** **NO-GO** until `GATEWAY_GO_LIVE.md` passes

The local production-component three-path rehearsal has passed all nominal,
power-outage, and lunar profiles through HTTPS Cloudflare Quick Tunnels. See
`THREE_PATH_CLOUDFLARE_ACCEPTANCE.md`. Real VM and production Convene acceptance
remain separate mandatory gates.

## 1. The endpoints are distinct

| Endpoint | Platform | Owns | Convene namespace |
|---|---|---|---|
| 1 — Windows 10 desktop live gateway | Windows 10 | Real cRIO/LabVIEW live-data interface | live source fields |
| 2 — MacBook scenario host | macOS | Local synthetic/file scenarios and Convene scenario publication | exact scenario names |
| 3 — Predictive-engine VM | Windows Server 2025 | Predictive algorithms, state bridge, VM publisher | `sim_` |
| 4 — Convene | external service/UI | Scenario routing and predictive views | consumes scenario + `sim_` |

Do not merge credentials, machine identities, namespaces, services, or rollback
procedures.

```text
cRIO / LabVIEW -> Windows 10 desktop live gateway -> production live path

MacBook scenario source -> 127.0.0.1:9070
  -> best-effort /machine/publish -> Convene exact-name scenario variables
  -> separately owned Convene-to-VM scenario pipe

VM state bridge -> Convene sim_*
MacBook scenario status: 127.0.0.1:9080 only
```

## 2. Authority rules

- The cRIO is the authoritative live source; the Windows gateway fabricates no sensor,
  state, chamber, cycle, quality, or timestamp values.
- The MacBook writes only labeled scenario variables and has no live-data or
  direct-cloud responsibility.
- The VM is the sole `sim_*` writer.
- VM delivery is durable; the MacBook Convene audit path is best effort and may
  coalesce to the newest frame.
- Convene is a consumer. `/command` remains advisory and disconnected from all
  hardware authority.
- A new gateway `run_id` is a transport identity, not a physical batch boundary.
  Physical resets are governed by `cycle_id`.

## 3. Endpoint 2 — MacBook scenario host

Authoritative files:

- `pi_gateway/config.macbook.example.yaml`
- `pi_gateway/macos/README.md`
- `deployment/CRIO_GATEWAY_CUTOVER_RUNSHEET.md`
- `deployment/GATEWAY_GO_LIVE.md`

Bind `9070` and `9080` only to `127.0.0.1`. Never assign the MacBook a cRIO
listener address and never expose its scenario receiver on LAN/WAN.

For each valid source line the gateway:

1. Parses and constructs the canonical frame.
2. Persists it and its sequence high-water mark in SQLite.
3. Exposes the latest frame locally.
4. Offers the same frame to the nonblocking raw gateway worker.
5. Publishes the newest scenario value to the MacBook Convene machine.

The MacBook Convene credential must be user-readable only. The MacBook receives
no VM ingest or read token.

## 4. Endpoint 2 — Windows predictive-engine VM

The VM remains Windows Server 2025. It runs one production `DualPushEngine` on
`127.0.0.1:8078`, fronted by Cloudflare, with durable ingest identity. The state
bridge reads authenticated `/state`, applies freshness/lease rules, writes
`C:\ConveneAgent\sim_vars.json`, and feeds the VM Convene agent.

VM live and scenario ingestion is prepared separately. The MacBook receives no
VM token and has no direct cloud-acceptance gate.

## 5. Endpoint 3 — Convene

The MacBook and VM use separate machine identities and credentials. Acceptance
requires visible, advancing, correlated provenance in both views:

- `run_id`, `source_id`, `seq` from the MacBook;
- `sim_run_id`, `sim_source_id`, `sim_seq` from the VM;
- matching source identity for the same stream;
- DATA NOT LIVE after freshness/lease expiry.

Retained values from older frames must not appear current when the present frame
omits a field.

## 6. Acceptance sequence

1. Freeze one exact repository SHA across MacBook and VM.
2. Accept the VM engine/state bridge independently.
3. Accept the MacBook foreground lifecycle, listener/status binding, queue, and TLS.
4. Send a bounded labeled synthetic stream through the MacBook and production VM.
5. Correlate MacBook, VM, state bridge, raw gateway, and `sim_` evidence.
6. Prove stale expiry and restart recovery.
7. Only then connect exactly one controls-approved cRIO producer.
8. Retain first-frame, five-minute, fault, restart, and rollback evidence.

Earlier Windows-gateway evidence remains useful historical software evidence but
does not constitute MacBook acceptance.

## 7. Stop conditions

Stop if the SHA differs, the OT address is not reserved, an unknown process owns
`9070`/`9080`, `9070` is exposed on WAN, `9080` is exposed beyond loopback,
secrets are visible, the queue grows without acknowledgement, dead letters rise,
the engine does not adopt the MacBook run, another writer produces `sim_*`, or
any advisory output is connected to hardware.
