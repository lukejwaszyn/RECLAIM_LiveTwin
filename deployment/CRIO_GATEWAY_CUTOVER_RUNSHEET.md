# Gateway Cutover Runsheet — bench reader → production listener

**Date:** 2026-08-23
**Scope:** desktop/gateway side only (handoff §B). No cRIO edit, redeploy, or
re-addressing. Run on the Windows 10 edge gateway (`192.168.1.1`). Each step is
copy-pasteable; stop at any ✋ if the check fails.

Context going in (per `GATEWAY_GO_LIVE.md` §§3–5, evidence 2026-08-19): the scoped
firewall rule is already applied and verified, and the `RECLAIM-EdgeGateway` SYSTEM
task has previously owned `192.168.1.1:9070` + loopback `9080`. This runsheet
re-verifies rather than re-creates that state, and hands the port from the LabVIEW
bench reader back to the production gateway.

## 0. Pre-checks (read-only)

```powershell
# Who owns 9070 and 9080 right now?
Get-NetTCPConnection -State Listen | Where-Object {$_.LocalPort -in 9070,9080} |
  Select LocalAddress,LocalPort,OwningProcess,@{n='Proc';e={(Get-Process -Id $_.OwningProcess).ProcessName}}
# Gateway task state
Get-ScheduledTask -TaskName 'RECLAIM-EdgeGateway' | Select TaskName,State
```

✋ If anything other than LabVIEW or the gateway owns 9070, stop and identify it.

## 1. Firewall audit (no changes expected)

```powershell
# Elevated. Audit only — prints JSON, changes nothing.
.\pi_gateway\windows\configure-crio-network-firewall.ps1
```

Confirm in the output: OT adapter (`InterfaceAlias` matches the real cRIO-link
adapter — default `Ethernet`; pass `-InterfaceAlias` if the site differs), IPv4
`192.168.1.1/24` present, `NetworkCategory: Private`, `EthernetDefaultRoutes: []`
(**no default route on the OT NIC**), `ReclaimRulePresent: true`,
`ExplicitInbound9080AllowRules: []`. ✋ Any deviation: fix with
`-Mode Apply` (elevated) only after understanding why the state drifted; 9080 rules
must be removed, never allowed.

## 2. Config check

Production config at `C:/RECLAIM/pi_gateway/config.windows.yaml` (ACL: SYSTEM +
Administrators only), per `pi_gateway/config.crio-live.example.yaml`:

- Seam A: `listen_host: 192.168.1.1`, `listen_port: 9070`,
  `conn_idle_timeout_s: 15.0`, `max_line_bytes: 8192`, `strict_fields: false`.
- Seam B: per `GATEWAY_GO_LIVE.md` §3 — current tunnel `/ingest` hostname and token.
  Quick Tunnel hostnames are ephemeral: re-verify the hostname is current **today**
  (`curl` the public `/health` from the gateway) before cutover. `verify_tls: true`.
- `mode: live`, `run_id: ""` (fresh run identity at start), buffer path/cap unchanged.

## 3. Pre-flight the software (green = go-signal)

From the repo root on the gateway (matching versions of this branch):

```
cd pi_gateway          && PYTHONPATH=%CD% python -m pytest tests -q   REM expect 55
cd ..\cloud_engine     && PYTHONPATH=%CD% python -m pytest tests -q   REM expect 74
cd ..\crio_source_record && PYTHONPATH=..  python -m pytest tests -q  REM expect 70
cd .. && set PYTHONPATH=pi_gateway;cloud_engine;%CD% && python -m crio_source_record.bench_replay
```

Bench replay must end `{'accepted': 3, ..., 'rejected': 0, 'sent': 3}`.
(Re-verified 2026-08-23 on the integration workstation: 55/67/70 + bench replay
green on this branch at commit `3608872`.)

✋ Any red: stop; do not point the cRIO at a failing gateway build.

## 4. Hand the port over

1. **Stop the LabVIEW bench reader** (close the bench VI / its listener). Verify
   9070 is free: re-run the §0 listener query — no 9070 row.
2. **Start the production gateway:**
   ```powershell
   Start-ScheduledTask -TaskName 'RECLAIM-EdgeGateway'
   ```
3. Verify the SYSTEM gateway now owns both listeners: §0 query shows
   `192.168.1.1:9070` and `127.0.0.1:9080`, owning process the gateway venv Python
   running as SYSTEM.

The cRIO keeps pointing at `192.168.1.1:9070` — no producer-side change. Its
bounded backoff will connect on its own once the listener is up.

## 5. Watch it (engineering shadow — no production claim)

On the gateway, loopback only (never tunnel 9080):

```powershell
curl http://127.0.0.1:9080/health
curl http://127.0.0.1:9080/latest
```

Watch for: connection accepted from `192.168.1.2`; frames received counter
advancing at the source cadence (~0.38 s); validation accepting (framer warnings
"unknown field preserved" are expected with `strict_fields: false`); buffer depth
stable/draining; Seam B delivering to the VM; VM freshness inside the 15 s window;
Convene tap (if enabled) publishing `gw_` variables only.

## 6. Live frame capture for conformance (handoff §A.2)

Once frames flow, capture a few hundred to a file (from the buffer/receiver log or
a capture tap — do **not** insert anything between the cRIO and the listener), then:

```
python -m crio_source_record.conformance --cloud --refresh-ts capture.ndjson
```

Expect 0 gateway fails and 0 cloud rejections. **Known trap, verified 2026-08-23:**
if the producer quarantines `PL_bottom2` but still sends `PL_bottom1/3/4`, every
frame passes the gateway and is rejected whole by the cloud (`telemetry_invalid`,
partial bed bank). A capture showing that pattern means the producer's bank policy
is wrong (Gate 3 checklist item 6.3) — record it, do not "fix" it downstream.

## 7. Exit state

The stream is a labeled engineering shadow. Gates 0/1/3 remain open; nothing in
this runsheet closes them. Gate 4/5 acceptance needs the explicit go + named
controls/onsite owners per the acceptance handoff §C.
