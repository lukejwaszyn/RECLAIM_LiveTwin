# Windows Cloud VM Predictive-Engine Session — Turnkey Brief

> **Stage:** Windows VM engine, tunnel, bridge, and Convene publication
> **Status:** CURRENT

Read `DEPLOYMENT_TOPOLOGY.md`, then follow `VM_ENGINE_RUNBOOK.md` and
`WINDOWS_VM_CONVENE_STATE_BRIDGE_RUNBOOK.md`.

## Platform truth

- The predictive-engine target is a cloud-hosted Windows Server 2025 VM inside
  Kubernetes-managed infrastructure.
- The edge gateway is a Windows 10 laptop.
- There is no Linux or Raspberry Pi runtime in the live pipeline.
- Kubernetes owns the outer hosting lifecycle; Windows services and NTFS paths
  own the guest applications and durable identity files.

## Objective

Run the reviewed dual predictive engine on `127.0.0.1:8078`, expose its required
authenticated `/ingest` route through Cloudflare, install and pair the headless VM
Convene agent, publish authenticated loopback `/state` through the independent
Windows state bridge and that agent, then hand the ingest URL and ingest token to
the Windows 10 gateway owner.

## Ordered session

1. Select and record the exact reviewed source SHA.
2. Confirm the intentionally clean baseline. Missing Python, `uv`, application
   directories, services, cloudflared, and Convene are expected—not blockers.
3. Bootstrap Python 3.13, pinned `uv`, cloudflared, reviewed WinSW, and the Windows
   directory/ACL structure.
4. Install and pair the repository's headless VM Convene agent as `Convene-Agent`;
   confirm `C:\ConveneAgent\sim_vars.json` is carried as heartbeat `simVars`.
5. Stage the exact revision under
   `C:\ProgramData\RECLAIM\releases\<SHA>` and run locked tests/imports.
6. Configure distinct ingest/read tokens in an ACL-protected Windows secret file;
   never place them in XML, commands, logs, screenshots, or GitHub.
7. Install or reconcile the `RECLAIMIngestEngine` WinSW service, loopback-only,
   production mode, with durable identity under `C:\ProgramData\RECLAIM\engine`.
8. Install/configure Windows cloudflared or start a temporary
   Windows quick tunnel to loopback 8078.
9. Run the 20-check acceptance harness using environment-provided credentials and
   prove restart/deduplication persistence.
10. Install the separate `RECLAIMStateBridge` service with the read token only.
11. Bind Convene first to bridge health and lease fields, determine prefix behavior,
   then bind process fields and prove fail-closed lease expiration.
12. Privately hand the Windows 10 gateway owner only the `/ingest` URL, ingest
    credential, selected SHA, freshness limit, and availability window.

## Tuesday exit gate

Synthetic authenticated telemetry must complete this path:

```text
POST /ingest -> Windows engine -> loopback /state -> state bridge
-> C:\ConveneAgent\sim_vars.json -> installed VM agent -> Convene
```

Tuesday integration is `PASS` only when synthetic live-shaped telemetry traverses
the same public Cloudflare `/ingest` route the gateway will use, the engine's
correlated `/state` advances, the bridge writes it, and the installed VM agent
delivers the correlated run/sequence into bound Convene `sim_` fields. Convene
must then show `DATA NOT LIVE` for stale state, invalid authentication, stopped
engine, stopped bridge, and expired `bridge_valid_until`. Ingress or local
`/state` without Convene evidence is `PARTIAL`; a value merely appearing and then
freezing in Convene is not acceptance.

Use `NewChat_Windows_VM_Predictive_Engine_Integration_Prompt.md` as the turnkey
prompt for the Codex session running on the VM.

## Wednesday dependency

Do not start full cRIO/gateway integration until Tuesday's engine, bridge, prefix,
single-writer, and lease gates are green. The Windows 10 gateway then completes the
separate `gw_` audit path and three-column V&V.
