# Claude Code — Gateway Staging Prompt Pack (cRIO offline)

> **Archived platform notice (2026-08-23):** the authoritative edge gateway is now the MacBook. Any Windows, Linux, Raspberry Pi, desktop-gateway, address, service, or task instructions below are historical evidence only and must not be used for the competition deployment. Use `deployment/DEPLOYMENT_TOPOLOGY.md` and `pi_gateway/macos/README.md`.

> **Stage:** 0 — Offline staging · **Status:** HISTORICAL — one-off session prompt
> pack, already executed. Kept as a record of how the gateway was staged.

Paste these into Claude Code **in order**, running from the repo root in an
**elevated** session:

```powershell
cd C:\Users\latitude4\Downloads\RECLAIM_LiveTwin
claude
```

Goal for this session: stage the edge gateway so it's **ready-and-waiting** for
the moment the cRIO is connected, prove the process is healthy on *this* laptop
without any live hardware or cloud, and pre-wire the Convene `gw_` audit mapping.
Nothing here posts to a live cloud, installs a boot service, or touches the
Convene `sim_` set.

---

## Prompt 0 — Context priming (paste first, once)

> You are staging the RECLAIM edge gateway on a Windows 10 laptop. Read
> `README.md`, `CODE_REVIEW.md`, `FIXES.md`, `docs/RECLAIM_Live_Telemetry_Architecture.md`,
> and `docs/RECLAIM_Remote_Gateway_Preflight.md` before acting.
>
> Environment facts (do not re-derive, and respect them):
> - Host `desktop-tampamr`, user `latitude4`, Windows 10 Education 22H2.
> - This box enforces a **WDAC code-integrity policy** and **blocks inbound
>   listener services** (OpenSSH server crash-looped, RDP listener = Access
>   Denied). **Outbound works fine.** Do not propose SSH/RDP servers or inbound
>   exposure as solutions.
> - National Instruments / LabVIEW is installed (it injects DLLs into PATH).
> - Python 3.12 is installed; the gateway is stdlib + `requests` and targets 3.10+.
> - Repo is here: `C:\Users\latitude4\Downloads\RECLAIM_LiveTwin`.
> - Deployment target for the gateway is `C:\RECLAIM\pi_gateway` (this is what
>   `pi_gateway/windows/install-gateway-task.ps1` expects).
> - Tailscale is up (this laptop `100.103.166.57`; a `reclaim-pi` node exists but
>   is offline). A Convene "connected machine" agent is already paired and
>   heartbeating from `%USERPROFILE%\.convene`.
> - **The cRIO is NOT currently connected**, and the cloud engine endpoint is not
>   yet confirmed. So: staging + a local console shakedown only.
>
> Doctrine / hard guardrails:
> - Live-only, side-by-side, **never overwrite a running stack in place**.
> - The cloud engine is the single writer of the Convene `sim_` set. This laptop
>   is the **`gw_` audit machine only** — never publish `sim_*`.
> - **No synthetic emitter** feeds any live/production path or the Convene `sim_`
>   namespace.
> - Do NOT install the `RECLAIM-EdgeGateway` boot task, do NOT open inbound
>   firewall for the cRIO, do NOT POST to any live cloud, do NOT touch Convene
>   `sim_` — not in this session.
> - Work in small steps: for each task show me a plan + the exact commands/diff
>   and wait for my approval before writing files or executing.
>
> Acknowledge you've read the above and list the files you reviewed, then stop.

---

## Prompt 1 — Verify repo + gateway tests green on this box

> Confirm the repo is intact and the **gateway** test suite passes here. Create a
> throwaway venv if needed, then run `cd pi_gateway; $env:PYTHONPATH="."; python -m
> pytest tests -q`. Report the pass count (expected ~10) and paste any failure
> verbatim. Do not modify code yet. (Skip the cloud_engine suite for now — it
> needs scipy and isn't part of gateway staging.)

---

## Prompt 2 — Stage the deployment directory

> Stage the gateway into its deployment location without disturbing the repo:
> copy `pi_gateway\` to `C:\RECLAIM\pi_gateway`, create a Python 3.10+ venv there
> (`py -3.12 -m venv .venv` is fine — the gateway is stdlib + requests), activate
> it, and `pip install -r requirements.txt`. Then verify the package imports
> (`python -c "import reclaim_edge, reclaim_edge.main"`). Show me the command plan
> first; after running, paste the pip summary and the import check. Also create
> `C:\ProgramData\RECLAIM` for the durable buffer.

---

## Prompt 3 — Build `config.windows.yaml` (placeholders for cloud)

> Create `C:\RECLAIM\pi_gateway\config.windows.yaml` from
> `pi_gateway\config.example.yaml` using the preflight §4.2 values:
> `src: reclaim-crio-laptop-01`, `listen_host: 192.168.50.1`, `listen_port: 9070`,
> `transport: https`, `mode: live`, `run_id: ""`, `schema_version:
> reclaim.telemetry.v1`, `strict_fields: false`,
> `buffer_path: C:/ProgramData/RECLAIM/queue.db`, `status_port: 9080`.
> Leave `cloud_url` and `auth_token` as clearly-marked **PLACEHOLDER** values — the
> cloud endpoint and `RECLAIM_INGEST_TOKEN` aren't provisioned yet. Comment every
> field. Confirm the loader fails fast on a missing/typo'd key (cite the code path).
> Show the file for my approval; do not start anything.

---

## Prompt 4 — Local console shakedown (no cRIO, no cloud)

> Prove the gateway process is healthy on this laptop without hardware or cloud.
> Make a copy `config.console.yaml` identical to `config.windows.yaml` but with
> `transport: console`. Set `$env:RECLAIM_EDGE_CONFIG` to it and run
> `python -m reclaim_edge.main` for ~30 seconds. Confirm: it starts without
> crashing, the status server answers on loopback — `curl http://127.0.0.1:9080/health`,
> `/latest`, `/command` — and worker threads stay alive (no silent thread death).
> Paste the `/health` JSON. Then stop it (Ctrl+C). Note: with no cRIO connected,
> `/latest` will be empty and the warn-once field logging won't trigger yet —
> that's expected. Do NOT install the scheduled task.

---

## Prompt 5 — Derive the `/latest` schema → Convene `gw_` mapping

> Statically (from the code — `pi_gateway/reclaim_edge/status.py`, `framer.py`,
> `main.py`, and `cloud_engine/labview_map.py` for field names), document the exact
> JSON shape the gateway serves at `GET /latest`. Produce
> `deployment/CONVENE_GW_MAPPING.md`: a table of Convene `gw_*` variables → the
> HTTP-collector `jsonPath` into `http://127.0.0.1:9080/latest`, covering at least
> `gw_seq`, `gw_ts`, `gw_run_id`, `gw_source_op_state`, `gw_active_chamber`, and the
> raw channels (`gw_MW_power`, `gw_PL_bottom1`, …). This is what I'll enter in
> Convene's Variables tab so the `gw_` audit set lines up field-for-field with the
> cloud's `sim_` set. Derive from code, don't invent fields.

---

## Prompt 6 — Readiness punch-list

> Write `deployment/GATEWAY_GO_LIVE.md`: a go/no-go checklist of what's staged vs
> what remains before live data can flow — cRIO physical connect + static IPs
> (§4.1), cloud ingress URL + `RECLAIM_INGEST_TOKEN` + `RECLAIM_READ_TOKEN`,
> Windows Firewall inbound TCP 9070 on the **Private** profile, `RECLAIM-EdgeGateway`
> boot task install, the six §5 contract gates, and the §6 three-column `gw_`/`sim_`
> V&V. Mark clearly which items are done from this staging session. Keep it a
> living list.

---

## Optional — Prompt 7 — Reconcile the Pi-vs-laptop naming drift

> Docs/comments only (no runtime changes): reconcile the "Raspberry Pi 3B+" vs
> "Windows laptop gateway" naming drift across `README.md`, `FIXES.md`, the
> architecture doc, and the preflight filename, per `CODE_REVIEW.md` H6. Show a
> per-file diff for approval.

---

### Guardrail reminder
If Claude Code ever proposes: installing the boot task, opening inbound firewall,
POSTing to a live cloud, publishing `sim_*`, or running a synthetic emitter into
anything live — **stop it.** None of that belongs in this offline staging session.
