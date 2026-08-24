# Windows 10 live gateway

The Windows 10 desktop is the sole live cRIO gateway. It receives the exact
LabVIEW source record and publishes the canonical envelope plus raw source
variables to its Convene machine. Convene's internal routing owns the cloud
engine request and computed-state return.

```text
cRIO / LabVIEW -> Windows gateway TCP 9070 -> Convene live machine
Convene internal route -> cloud stochastic engine -> Convene sim_*
```

The gateway must use `transport: console`, an empty direct-ingest token,
`convene_enabled: true`, and exact source names with no manufactured `gw_`
prefix. It must never emit `sim_*`. Start from
`pi_gateway/config.crio-live.example.yaml` and the sole current pickup document,
`deployment/CURRENT_CONVENE_ROUTED_SYSTEM_HANDOFF.md`.

The receiver binds only the dedicated cRIO-facing interface after controls and
network approval. Status port `9080` remains loopback-only. The production
source must publish `mode=live`, authoritative run/cycle/sequence/timestamp,
`source_op_state`, `active_chamber`, and the approved raw variables.

## Current checks

```powershell
Invoke-RestMethod http://127.0.0.1:9080/health
Invoke-RestMethod http://127.0.0.1:9080/latest
```

Acceptance requires a correlated fresh source update in Convene, an accepted
engine frame with the same identity, and the corresponding `sim_*` result back
in Convene. Source values that are absent or `NaN` are unavailable and must not
be displayed or inferred as retained fresh measurements.

## Retained legacy scripts

Some PowerShell files in this directory still implement the former direct
gateway-to-VM HTTPS/Cloudflare commissioning route. They are retained as code
history and are not authorized by the current topology. Do not run
`finalize-gateway-config.ps1`, direct-VM commissioning scripts, or any step that
puts a VM ingest URL/token on this gateway unless the architecture is formally
changed in the current handoff.

All predictive output remains advisory and disconnected from actuation.
