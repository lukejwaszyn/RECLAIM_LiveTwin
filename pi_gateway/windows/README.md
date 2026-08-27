# Windows 10 live gateway

The Windows 10 desktop is the sole live cRIO gateway. The current physical live
contract is authoritative `active_chamber` followed by the exact 34-field LabVIEW
source record. It is not required to contain run/source IDs, sequence, timestamps,
cycle identity, mode, or source operating state. Convene publishes the exact raw
names and routes the record to the cloud engine's common `/ingest` endpoint.

```text
cRIO / LabVIEW -> Windows gateway TCP 9070 -> Convene live machine
Convene internal route -> cloud stochastic engine -> Convene sim_*
```

The gateway must use `transport: console`, an empty direct-ingest token,
`convene_enabled: true`, and exact source names with no manufactured `gw_`
prefix. It must never emit `sim_*`. Start from
`pi_gateway/config.crio-live.example.yaml`, the root `README.md`, and
`deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

The receiver binds only the dedicated cRIO-facing interface after controls and
network approval. Status port `9080` remains loopback-only. The engine generates
receipt-owned mode/run/source/sequence/timestamp/cycle metadata when those fields
are absent. `active_chamber` is authoritative and must be routed unchanged. The
engine's process-based chamber inference exists only for backward compatibility
with older retained 34-field captures.

## Current checks

```powershell
Invoke-RestMethod http://127.0.0.1:9080/health
Invoke-RestMethod http://127.0.0.1:9080/latest
```

Acceptance requires a correlated fresh raw update in Convene, an accepted engine
receipt sequence/timestamp, and the corresponding `sim_*` result back in Convene.
Source values that are absent or `NaN` are unavailable and must not be displayed
or inferred as retained fresh measurements.

## Removed competing paths

The former direct gateway-to-VM finalizer and commissioning senders were removed
from the final tree. No active Windows script puts a VM ingest URL/token on the
live gateway.

All predictive output remains advisory and disconnected from actuation.
