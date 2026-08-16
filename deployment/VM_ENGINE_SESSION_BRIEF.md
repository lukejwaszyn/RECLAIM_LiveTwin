# Cloud VM Predictive-Engine Session — Turnkey Brief

> **Stage:** 1 — Cloud engine on VM + egress tunnel · **Status:** CURRENT (active).
> Paired with `VM_ENGINE_RUNBOOK.md` (the step-by-step commands).

**Read `deployment/HANDOFF.md` first** for the full project state. This is the
step list for the session that stands up the cloud dual engine and the egress
tunnel. Cross-references (§n) are to `docs/RECLAIM_Remote_Gateway_Preflight.md`.

## Objective

Get the cloud dual predictive engine running on the VM behind a Cloudflare Tunnel,
with tokens, so the laptop gateway can POST live frames to it — then hand the
ingress hostname + ingest token back to finalize the gateway. **Side-by-side,
never overwrite a running stack in place. `--production` accepts `mode: "live"`
only.**

## Starting point (what's already true)

- Gateway staged and healthy on the laptop; its `config.windows.yaml` has
  `cloud_url` / `auth_token` as **placeholders** waiting for this session's outputs.
- The Convene agent runs as SYSTEM at boot on the laptop (the persistent outbound
  plane; see `HANDOFF.md` §4). The `gw_` audit tap is mapped and ready
  (`CONVENE_GW_MAPPING.md`).
- Access to this box is outbound-only (WDAC); the same posture applies to the VM
  design — the engine binds **loopback**, cloudflared is the only path in.

## Steps

1. **Deploy the engine** to a fresh dir on the VM (e.g. `/opt/reclaim/engine`).
   Create a venv and install `cloud_engine/deploy/requirements-cloud.txt`.
   - **Known gap:** `reclaim_predictive_engine/anomaly.py` imports
     `scipy.stats.chi2`, but `scipy` is missing from `requirements-cloud.txt`.
     Add a pinned `scipy` (confirm numpy compatibility) or the service won't import.
2. **Secrets first** (§3). `sudo install -d -m 700 /etc/reclaim`, copy
   `cloud_engine/deploy/reclaim-ingest.env.example` to
   `/etc/reclaim/reclaim-ingest.env` (mode 600), and set a long random
   `RECLAIM_INGEST_TOKEN` and a **distinct** `RECLAIM_READ_TOKEN` (for `/state`,
   `/manifest`, `/history`, `/command`; `/health` stays open).
3. **Install the service** `cloud_engine/deploy/reclaim-ingest.service` — bind
   `127.0.0.1:8078`, `--production`, `EnvironmentFile` (required, no leading `-`),
   `StateDirectory=reclaim-ingest` + `RECLAIM_INGEST_STATE` so run/seq identity
   survives restarts (fix C4). Never pass the token on the command line. Set the
   real venv python + working-dir paths for the VM.
4. **Cloudflared (egress tunnel).** Start with a **quick tunnel** per this
   session's decision:
   `cloudflared tunnel --url http://localhost:8078` → note the `trycloudflare.com`
   hostname. Route both `POST /ingest` and the GET routes through it.
   - **Caveat:** the quick-tunnel hostname is **ephemeral (changes each restart)**
     and has **no Access policy**. For a stable `cloud_url` + an Access policy,
     add a domain and use a **named tunnel** (`cloudflared tunnel create` +
     `route dns` + a self-hosted Access app) — recommended once interop matters.
5. **Verify from the VM and from the laptop:**
   `curl https://<hostname>/health` (open), and with the read token
   `curl -H 'Authorization: Bearer <READ>' https://<hostname>/state`. Record
   round-trip time from the laptop (`GATEWAY_GO_LIVE.md` §3).

## Hand back to the gateway (closes the egress loop)

- Give the laptop: the **ingress hostname** → set
  `cloud_url: https://<hostname>/ingest` in `C:\RECLAIM\pi_gateway\config.windows.yaml`,
  and the **`RECLAIM_INGEST_TOKEN`** → `auth_token` (same value).
- Then **ACL-lock** that config (it now holds the token in cleartext): break
  inheritance, grant SYSTEM + Administrators only (`GATEWAY_GO_LIVE.md` §3).

## Then (still ordered, still gated)

- Only after ingress (§2, cRIO IPs) **and** egress (this session) are both real:
  install the gateway boot task (`GATEWAY_GO_LIVE.md` §5), then run the **six §5
  contract gates** (fresh / duplicate / harness-reject / stale / gateway-restart /
  cloud-restart + freshness decay), then the **§6 three-column V&V** with the
  `gw_` audit machine.

## The contract the engine must satisfy

`docs/RECLAIM_Live_Telemetry_Architecture.md` is authoritative: inbound
`reclaim.telemetry.v1` envelope + validation table (auth, schema, mode, timestamp
freshness, run identity/supersession, monotone seq, physics/sensor checks), the
v1.1 per-frame ack contract, and the flat `reclaim.state.v1` output with the
`op_state` / `PL_op_state` / `MT_op_state` authority model. The gateway already
speaks this; the engine must too.
