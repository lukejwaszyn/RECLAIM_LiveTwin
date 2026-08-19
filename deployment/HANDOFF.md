# RECLAIM Live Twin — Project State & Session Handoff

> **Stage:** cross-cutting (current pickup point) · **Status:** LIVING — authoritative
> project story. Start here. See `deployment/README.md` for the stage-sorted index.

**Written:** 2026-08-15 · **Updated:** 2026-08-17 · **Purpose:** clean pickup for
the next working sessions. The immediate priority is the **RT-03/RT-05 backend
remediation and 72-hour demo**, followed by the cloud VM predictive-engine
session. This is the "full story" document; the detailed punch list lives in
`deployment/GATEWAY_GO_LIVE.md` and is referenced throughout.

---

## 1. One-paragraph status

The **laptop edge gateway** is staged and proven healthy in isolation, but the
system is **NO-GO for live data** — there is no cRIO link, no cloud engine
endpoint, and no tokens yet. Remote administration of this laptop is **outbound-
only** (the box's WDAC policy blocks inbound SSH/RDP listeners), and that
constraint shapes the whole architecture. The one piece that is **live and
persistent right now** is the **Convene connected-machine agent**, which runs as
SYSTEM from boot — see §4, because it is the architectural base for the
ingress/egress work still to come.

### Immediate 72-hour pickup

The Git repository, private GitHub remote, and hosted CI baseline now exist. The
RT-03/RT-05 transaction and structural-validation remediation is implemented on
the current integration branch, and the locked local suite is green. Review and
hosted CI must still verify the exact deployment SHA. Work in this order:

1. Review the completed `deployment/RECLAIM_BACKEND_REMEDIATION_HANDOFF.md`
   implementation and require green CI on the exact deployment SHA.
2. Preserve a guaranteed, loopback-only synthetic nominal demo and rehearse the
   power-outage and lunar-surface scenarios using
   `deployment/RECLAIM_72_HOUR_DEMO_DEPLOYMENT_STRATEGY.md`.
3. Treat live nominal deployment as a stretch path only. It remains NO-GO unless
   the backend safety gate and every endpoint/operations gate are green by the
   strategy's `T+48h` decision point.

---

## 2. The stack, end to end

```
cRIO / LabVIEW ──(Ethernet 192.168.50.x, INGRESS)──► Laptop edge gateway
   (physical plant)                                     (reclaim_edge, this box)
                                                           │
                                                           │ authenticated HTTPS (EGRESS)
                                                           ▼
                                                  Cloudflare Tunnel ──► Windows Server 2025 VM
                                                                          │ dual engine on loopback
                                                                          │ Windows state bridge
                                                                          ▼
                                                                   installed VM Convene agent
                                                                          │ sim_ + native .stp view

   Parallel audit tap:  Laptop gateway ──(/machine/publish, gw_ only)──►  Convene
```

- **Ingress** = data *in* from the cRIO to the gateway (physical Ethernet link).
- **Egress** = data *out* from the gateway to the cloud engine (HTTPS over a
  Cloudflare Tunnel). **Both are deferred** — see §5.
- The **cloud engine** is the single writer of the Convene `sim_` set. The
  **laptop** is the `gw_` audit machine only (byte-for-byte V&V tap), never a
  second `sim_` writer.
- The VM is a **Windows Server 2025 guest in Kubernetes-managed cloud
  infrastructure**. Kubernetes is the outer hosting layer; VM operations use
  PowerShell, Windows services, NTFS paths, and ACLs. There is no Linux host or
  Raspberry Pi in the live pipeline. See `DEPLOYMENT_TOPOLOGY.md`.

---

## 3. What exists right now (verified)

### On the gateway laptop (`desktop-tampamr`, user `latitude4`, Win 10 Education 22H2)

- **Claude Code** installed native + signed in (Pro/Max).
- **Tailscale** up: this laptop `100.103.166.57`, MacBook `lukes-macbook-air`
  `100.75.32.16`; a `reclaim-pi` node exists but is **offline** (retired Pi plan —
  disposition open, `GATEWAY_GO_LIVE.md` §9.7).
- **Edge gateway staged** at `C:\RECLAIM\pi_gateway`: venv (**Python 3.13.0**),
  `pyyaml 6.0.3` / `requests 2.34.2` / `paho-mqtt 1.6.1` (held `<2.0` per fix M6),
  `config.windows.yaml` (cloud values are **PLACEHOLDERS**), `config.console.yaml`,
  empty `queue.db`. Console shakedown passed; binds `127.0.0.1:9070`/`9080` only.
  The **boot task is deliberately NOT installed** (`GATEWAY_GO_LIVE.md` §5) — with
  no cRIO IP and a placeholder URL it would crash-loop.
- **Convene agent running as SYSTEM at boot** — see §4.
- Docs reconciled to the Windows 10 laptop gateway and Windows Server 2025 VM;
  the preflight is `RECLAIM_Remote_Gateway_Preflight.md`.

### Access model (settled this project)

Inbound listeners are blocked by an enforced **WDAC code-integrity policy**
(OpenSSH server crash-loops; the RDP listener returns Access Denied). **Do not
attempt SSH/RDP servers on this box.** Administration is **outbound-only**:
**TeamViewer** for hands-on, **Tailscale** for the private network, and the
**Convene agent** for a programmatic outbound control/telemetry plane. This is
not a limitation to work around later — it is the architecture. Preflight §1 and
`GATEWAY_GO_LIVE.md` §9.1 now record this model.

### Not yet built

Cloud engine (VM), Cloudflare Tunnel, tokens, cRIO physical link, gateway boot
task, the six contract gates, and the three-column V&V. Full list and ordering:
`deployment/GATEWAY_GO_LIVE.md` §2–§8.

---

## 4. Architectural base — the Convene agent is always-on at boot

**This is the foundation the ingress/egress development builds on, so it is stated
first-class here.**

The Convene connected-machine agent (machine ID `6xaiDIfauON8lGDVy2s1`) is
registered as the Windows Scheduled Task **`Convene-Agent`**: `AtStartup`, runs as
`NT AUTHORITY\SYSTEM` at highest run level, restarts every minute on failure, no
execution-time limit, starts on battery. It launches
`C:\Users\latitude4\.convene\run-agent.cmd`, reads credentials from the SYSTEM
profile (`C:\Windows\System32\config\systemprofile\.convene_agent.json`), and
appends to `C:\Users\latitude4\.convene\agent.log`. It heartbeats every 30 s.

**Why this is the architectural base:**

- It establishes a **persistent, outbound-initiated control/telemetry plane** that
  survives reboots with zero manual startup — exactly the pattern the WDAC box
  permits, and the pattern the egress (gateway→cloud) will follow.
- Its desktop machine credential is reused by the gateway's independent
  **`gw_` audit tap**. After each canonical frame is durably queued for the VM,
  a nonblocking one-slot worker submits the `gw_` set directly to Convene's
  `/machine/publish` endpoint (`deployment/CONVENE_GW_MAPPING.md`).
- It gives us a working **remote-execution path onto the gateway** without any
  inbound listener, which the ingress/egress bring-up can lean on for adjustments.

**Consciously accept, don't skip** (`GATEWAY_GO_LIVE.md` §9.9): by design the agent
polls the Convene backend every 2 s and executes returned shell commands — as
SYSTEM, that is a full **admin remote shell** through your Convene control plane.
It's your platform, so this is likely intended, but two decisions should be
recorded: (a) the team accepts a SYSTEM-level remote shell on the gateway, and
(b) who on the Convene side may issue commands. **Never run the agent with
`--desktop`** on this machine — that path enables passwordless VNC on a public
quick-tunnel (the launcher comment says so).

---

## 5. Ingress / egress — deferred, but scoped

We are intentionally **not** building these yet; this section is the plan of
record so the next session starts clean.

### Ingress (cRIO → gateway)

- Direct Ethernet link, laptop `192.168.50.1/24`, cRIO `192.168.50.10/24`, **no
  default gateway** on either direct-link interface (Wi-Fi stays the Internet
  route). cRIO TCP target `192.168.50.1:9070`.
- Windows Firewall inbound TCP **9070**, **Private profile only**, bound to the
  direct-link interface (`GATEWAY_GO_LIVE.md` §4). Never expose 9080.
- Currently the Ethernet is `192.168.1.1/24` and `192.168.50.1` is unassigned, so
  the gateway can't bind the live listener yet (`GATEWAY_GO_LIVE.md` §2).

### Egress (gateway → cloud)

- The cloud dual engine runs on the VM bound **loopback**; **cloudflared** fronts
  it and forwards `POST /ingest` + the GET routes. The gateway does authenticated
  **outbound** HTTPS to that hostname — consistent with the outbound-only base in
  §4.
- **Tunnel choice (per this session's decision):** start with **Cloudflare quick
  tunnels** (`trycloudflare.com`, no domain needed). Caveat to plan around: a quick
  tunnel's hostname is **ephemeral — it changes every restart**, so the gateway's
  `cloud_url` would need re-entry each time, and there is **no Cloudflare Access
  policy** in front of it. For stable ingress + an Access policy, **add a domain
  and use a named tunnel** — worth doing once interoperability matters. Record the
  decision wherever §9.1's access model is finalized.

---

## 6. NO-GO blockers (summary — detail in `GATEWAY_GO_LIVE.md`)

1. **cRIO link** not connected; static IPs not set (§2).
2. **Cloud endpoint** not provisioned; **tokens** don't exist (§3).
3. **Gateway boot task** deliberately withheld until 1 & 2 are done (§5).
4. Downstream and strictly ordered: firewall (§4) → contract gates (§5/§6) →
   three-column V&V (§7). Critical path diagram in §8.

---

## 7. Open decisions carried forward (`GATEWAY_GO_LIVE.md` §9)

- §9.1 outbound-only access and §9.2 Python 3.13 support are resolved. §9.3
  Exercise the graceful-stop (Ctrl+C → exit 0) path. §9.4 Status server has no auth — never
  tunnel 9080 without carrying auth. §9.5 Verify the 27 raw `vars` names against
  the first real frame. §9.7 Dispose of the offline `reclaim-pi` node. §9.9
  Accept/record the SYSTEM remote-shell posture (see §4).

---

## 8. Next session — cloud VM predictive engine

See `deployment/VM_ENGINE_SESSION_BRIEF.md` for the turnkey checklist. In short:
deploy `push_ingest_dual.py --production` on the Windows Server 2025 VM
(loopback), create the ACL-protected secret and persistent state files under
`C:\ProgramData\RECLAIM`, install the reviewed WinSW service, stand up Windows
cloudflared, verify `/health`, then **hand the ingress hostname + ingest token
back** so the gateway's `config.windows.yaml` can be finalized and ACL-locked.
Next, install the independent Windows state bridge and bind its output through
the VM Convene agent installed during bootstrap. Only then do the §5 contract gates and §6 V&V
become runnable.

---

## 9. Document index

| File | What it is |
|---|---|
| `deployment/README.md` | **Stage-sorted index** of every deployment doc (start here for orientation) |
| `deployment/HANDOFF.md` | **This doc** — full story + pickup pointers |
| `deployment/DEPLOYMENT_TOPOLOGY.md` | Authoritative Windows VM/gateway topology and responsibility boundary |
| `deployment/RECLAIM_72_HOUR_DEMO_DEPLOYMENT_STRATEGY.md` | Immediate demo critical path, scenario run sheet, endpoint gates, and fallback |
| `deployment/RECLAIM_BACKEND_REMEDIATION_HANDOFF.md` | RT-03/RT-05 implementation contract and acceptance gates |
| `deployment/NewChat_Cloud_Pipeline_Convene_Fix_Prompt.md` | Primary fresh-chat prompt for backend fixes, cloud proof, and Convene reintegration |
| `deployment/ClaudeCode_Backend_Remediation_Prompt.md` | Turnkey prompt for the backend implementation session |
| `deployment/GATEWAY_GO_LIVE.md` | Living go/no-go punch list (authoritative status) |
| `deployment/VM_ENGINE_HANDOFF.md` | **Stage 1 — read-first** full story + guardrails + acceptance gates for the VM session |
| `deployment/VM_ENGINE_SESSION_BRIEF.md` | Stage 1 — turnkey brief for the cloud VM engine session |
| `deployment/NewChat_Windows_VM_Predictive_Engine_Integration_Prompt.md` | Fresh VM Codex prompt for Tuesday ingress-to-Convene integration and rehearsal profiles |
| `deployment/VM_ENGINE_RUNBOOK.md` | Stage 1 — executable step-by-step VM deployment (quick tunnel) |
| `docs/RECLAIM_Predictive_Engine_Lifecycle_Memo.md` | Engine fault/fix analysis + autonomous-lifecycle design of record |
| `deployment/CONVENE_GW_MAPPING.md` | `gw_` audit variables → `/latest` jsonPaths (36 vars) |
| `deployment/SSH_Tailscale_ClaudeCode_Setup.md` | Access setup as run (SSH parts now superseded — see §9.1) |
| `deployment/convene-setup-2.ps1` | Headless-by-default Windows VM Convene agent bootstrap; pairs, registers the startup task, and carries `sim_vars.json` as heartbeat `simVars` |
| `deployment/START_HERE.md`, `ClaudeCode_*_Prompts.md` | Historical Stage-0 session records (see `deployment/README.md`) |
| `docs/RECLAIM_Remote_Gateway_Preflight.md` | The canonical deployment preflight |
| `docs/RECLAIM_Live_Telemetry_Architecture.md` | Schemas, validation, single-writer contract |
| `convene/RECLAIM_Convene_Live_Binding.md` | `sim_` binding set + Convene-native `.stp` visualization spec |
| `CODE_REVIEW.md` / `FIXES.md` | Hardening review and its implemented fixes |
