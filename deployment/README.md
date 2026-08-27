# RECLAIM deployment records

The project is closed. There is no active handoff document in this directory.
The root `README.md` is the final project-level source of truth; this directory
retains only durable architecture, source-record, controls-review, and VM audit
materials.

## Final topology and ownership

- `DEPLOYMENT_TOPOLOGY.md` — host platforms and the Convene-routed data path.
- `LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md` — Windows owns live telemetry;
  MacBook owns loopback scenarios.

## cRIO source record and producer

- `CRIO_SOURCE_RECORD_DECISION_RECORD.md` — selected acquisition path and
  decision evidence.
- `CRIO_SOURCE_RECORD_RUNBOOK.md` — source-record verification and bench replay.
- `CRIO_SOURCE_RECORD_SIGNED_MAPS.md` — controls-signoff channel maps.
- `CRIO_ACQUISITION_OPTIONS_TRADE_STUDY.md` — retained acquisition trade study.
- `CRIO_TELEMETRY_WRITE_PATH_AUDIT.md` — deterministic LabVIEW write-path audit.
- `CRIO_TELEMETRY_SOCKET_SETUP.md` — bounded producer/socket implementation.
- `CRIO_GATE3_PRODUCER_REVIEW_CHECKLIST.md` — supervised producer review gate.

## Cloud VM

- `windows-vm/README.md` — VM audit and contract-test procedure.
- `windows-vm/Audit-ConveneRoutedEngine.ps1` — read-only deployed-state audit.
- `windows-vm/Test-ConveneRoutedEngineContract.ps1` — source tests and optional
  supervised endpoint exercise.

Deprecated handoffs, prompts, direct-routing bridges, and superseded tunnel
procedures were removed at project closure. They are available only through Git
history and must not be treated as current operating instructions.
