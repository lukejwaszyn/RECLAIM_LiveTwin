# RECLAIM Gateway — Go / No-Go Punch List

> **Stage:** cross-cutting (Stages 0–4 tracker) · **Status:** LIVING — authoritative
> go/no-go status. Update as items close; do not archive at cutover.

**Living document.** Started 2026-08-14 during the offline staging session
(cRIO disconnected, cloud endpoint not provisioned). Update it as items close;
do not archive it at cutover — §6 and §8 remain permanent fixtures.

**Scope:** everything between "the gateway code exists" and "live cRIO data is
flowing to the cloud and verified in Convene." Cross-references are to
`docs/RECLAIM_Remote_Gateway_Preflight.md` unless stated otherwise.

**Authoritative topology (2026-08-17):** the gateway is a Windows 10 laptop.
The cloud predictive-engine guest is Windows Server 2025 in Kubernetes-managed
infrastructure. There is no Linux host or Raspberry Pi in the live path. See
`DEPLOYMENT_TOPOLOGY.md`.

## How to read this

| Marker | Meaning |
|---|---|
| **DONE** | Completed and evidenced. Evidence cited inline. |
| **BLOCKED** | Cannot be done yet. The blocker is named. |
| **NOT DONE — DELIBERATE** | Achievable now, intentionally withheld. The reason is a safety constraint, not a scheduling one. Do not "helpfully" complete these. |

**Current overall status: NO-GO for live data.** Four independent blockers:
no cRIO link, no cloud endpoint, no tokens, no boot task. The gateway itself is
staged and proven healthy on this laptop.

---

## 1. DONE — staging session 2026-08-14

| # | Item | Evidence |
|---|---|---|
| 1.1 | Repo intact; gateway test suite green on this box | `10 passed in 1.52s` (`pi_gateway`, `PYTHONPATH=.`). Covers the C1/H3 dead-letter contract, M7 seq high-water, M5 warn-once, §4.4 command relay, and three H7 config fail-fast cases. `cloud_engine` suite deliberately skipped (needs scipy; not gateway staging). |
| 1.2 | Gateway staged to its deployment location | `C:\RECLAIM\pi_gateway` — robocopy `14 files copied, 0 FAILED`, caches and `.DS_Store` excluded. Source repo untouched. |
| 1.3 | Deployment venv + runtime deps | `C:\RECLAIM\pi_gateway\.venv` (Python **3.13.0**). Installed: `pyyaml 6.0.3`, `requests 2.34.2`, `paho-mqtt 1.6.1` (correctly held `<2.0` by the M6 pin). |
| 1.4 | Package imports from the staged tree | `import reclaim_edge, reclaim_edge.main` → OK, resolved from `C:\RECLAIM\pi_gateway\reclaim_edge\__init__.py`, version `0.1.0`. |
| 1.5 | Durable buffer directory | `C:\ProgramData\RECLAIM` created. `queue.db` since created by the shakedown; inspected — tables `q`, `dl`, `meta`, `sqlite_sequence`, **all 0 rows**. No run/seq state carries into the live run. |
| 1.6 | `config.windows.yaml` built from preflight §4.2 | `C:\RECLAIM\pi_gateway\config.windows.yaml`, every field commented. All §4.2 values verbatim. `cloud_url` and `auth_token` are marked PLACEHOLDER — see §3. Loader parse confirmed; fail-fast guards proven by mutation (see §1.7). |
| 1.7 | Config fail-fast verified empirically, not just cited | Throwaway mutated copies raised as designed: missing explicit path → `FileNotFoundError`; `listen_prot` typo → `ValueError: unknown config key(s)`; `transport: htps` → `ValueError`; empty `auth_token` with live+https → `ValueError`. Code path `config.py:104-136` (review fix H7). |
| 1.8 | Local console shakedown — process healthy without hardware or cloud | `config.console.yaml` (differs from `config.windows.yaml` on exactly two lines: `transport: console`, `listen_host: 127.0.0.1`). Ran 30 s. Clean start, no traceback. `/health`, `/latest`, `/command`, `/` all answered. `uptime_s` 5.0 → 15.2 → 26.9 with the supervisor loop polling worker liveness every 0.5 s throughout — no silent thread death (`main.py:56-66`). Health lines logged on the configured 10 s cadence. |
| 1.9 | Loopback-only binding confirmed at the OS level | `netstat`: `127.0.0.1:9070` and `127.0.0.1:9080` LISTENING, same PID — never `0.0.0.0`. No inbound exposure created. Ports released on stop. |
| 1.10 | Convene `gw_` audit mapping derived | `deployment/CONVENE_GW_MAPPING.md` — 36 variables (9 envelope + 27 raw channels), each with jsonPath into `http://127.0.0.1:9080/latest`, type, `sim_` counterpart, unit conversion, and code citation. Derived statically from `status.py`, `framer.py`, `receiver.py`, `labview_map.py`. |

---

## 2. BLOCKED — §4.1 cRIO physical link and static IPs

**Current blocker: the physical link is proven, but the approved Private profile,
scoped firewall rule, listener, and reverse-direction verification are not yet
complete.**

- [x] cRIO connected directly to the laptop Ethernet port
- [x] Laptop Ethernet retains the verified laboratory address `192.168.1.1/24`
- [x] cRIO Ethernet confirmed at `192.168.1.2/24`
- [ ] **No default gateway on either direct-link interface** — Wi-Fi remains
      Windows' default Internet route
- [ ] cRIO TCP target confirmed as `192.168.1.1:9070`
- [ ] Link verified (ping both directions) before starting the gateway

**Recorded state on 2026-08-14:** Ethernet is `192.168.1.1/24`; `192.168.50.1`
is **not assigned** to any interface. Wi-Fi `104.39.44.203`, Tailscale
`100.103.166.57`, plus Hyper-V vSwitch `192.168.96.1` and link-local addresses.

**Onsite evidence 2026-08-19:** the direct cable negotiated **1 Gbps**. Windows
reported laptop `192.168.1.1/24` (manual) and resolved `192.168.1.2` to peer MAC
`00-80-2F-13-C9-10`; three laptop-to-cRIO probes succeeded in 0–2 ms. Wi-Fi
remained the only IPv4 default route and was associated over 802.11ac on channel
124 (5 GHz). The operator confirmed `192.168.1.2` is the cRIO and approved
preserving this working lab subnet instead of renumbering it to the originally
planned `192.168.50.0/24`. Ethernet was still **Public**, no process listened on
9070/9080, and no RECLAIM firewall rule existed. The reviewed, rollback-capable
script `pi_gateway/windows/configure-crio-network-firewall.ps1` was created but
has now been run from an elevated PowerShell session. It recorded the pre-change
state at `C:\ProgramData\RECLAIM\crio-network-firewall-before.json`, changed only
the Ethernet category from Public to Private, and made no address or route change.
Post-change laptop-to-cRIO probes again passed in 0–1 ms. The cRIO-side default
gateway and reverse-direction ping remain unverified.

**Consequence while unassigned:** `receiver.py:37` does a bare
`srv.bind((listen_host, listen_port))`. Binding an unassigned address raises
`WinError 10049`, the receiver thread dies, and M6 supervision exits the process
non-zero within 0.5 s. This is why the shakedown used `127.0.0.1` in a separate
console config — and why the boot task must not be installed yet (§6).

---

## 3. BLOCKED — cloud ingress and tokens

**Blocker: the cloud engine endpoint is not provisioned and no tokens exist.**

- [ ] Cloud dual engine deployed, bound **loopback only**, behind the
      Cloudflare Tunnel (preflight §3)
- [ ] Ingress hostname confirmed → set `cloud_url: https://<host>/ingest`
- [ ] `RECLAIM_INGEST_TOKEN` generated (long, random) in the VM's
      ACL-protected secret file → same value into gateway `auth_token`
- [ ] `RECLAIM_READ_TOKEN` generated, distinct, for the GET routes
      (`/state`, `/manifest`, `/history`, `/command`) used by the Convene
      publisher and its native `.stp` visualization. `/health` stays open for probes
- [ ] `RECLAIM_INGEST_STATE` configured (required under `--production`, so
      run/seq identity survives a cloud restart — fix C4)
- [ ] `curl https://<ingress>/health` reachable **from this laptop**, round-trip
      times recorded

### Current placeholder values — replace both

```yaml
cloud_url: PLACEHOLDER_CLOUD_INGRESS_NOT_PROVISIONED
auth_token: PLACEHOLDER_RECLAIM_INGEST_TOKEN_NOT_PROVISIONED
```

**These placeholders will not stop the gateway from starting.** `config.py:131`
checks only that `auth_token` is **non-empty**; any string passes. `cloud_url` is
not validated at all. So a gateway started with these values loads cleanly and
then fails every POST against a nonexistent host. **Replacing them is a human
gate, not an enforced one** — treat it as a hard checklist item.

- [ ] After entering real secrets, **restrict the ACL on
      `C:\RECLAIM\pi_gateway\config.windows.yaml`** — it holds the ingest token
      in cleartext; use an explicit restricted NTFS ACL.
      Suggested: break inheritance, grant SYSTEM and Administrators only.

---

## 4. NOT DONE — DELIBERATE — Windows Firewall inbound TCP 9070

Withheld for this session by explicit guardrail. Required before the cRIO can
connect, and **only** on the Private profile bound to the direct-link interface.

Command for the day it is authorized (do not run before §2 is complete):

```powershell
New-NetFirewallRule -DisplayName "RECLAIM cRIO telemetry (9070)" `
    -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9070 `
    -Profile Private -InterfaceAlias Ethernet `
    -LocalAddress 192.168.1.1 -RemoteAddress 192.168.1.2
```

- [x] Rule created, Private profile only
- [x] Verified the Ethernet interface is classified **Private**, not Public
- [ ] Verified from the cRIO that 9070 is reachable
- [x] Confirmed the rule is restricted to interface alias `Ethernet`, so it does
      **not** apply to Wi-Fi even though Wi-Fi is also currently Private

Note: 9080 (status endpoint) must **never** get an inbound rule. It binds
loopback by design (`status.py:84`) and has no authentication (§9.4).

**Rule evidence 2026-08-19:** enabled inbound TCP 9070, local
`192.168.1.1`, remote `192.168.1.2`, Private profile, interface alias
`Ethernet`; no explicit inbound 9080 rule and no 9070/9080 listener yet.
Rollback is `configure-crio-network-firewall.ps1 -Mode Rollback` from an elevated
PowerShell. Two pre-existing broad Private allow rules named `python.exe` target
the user Python at
`C:\Users\latitude4\AppData\Local\Programs\Python\Python313\python.exe`, which
is used by the SYSTEM Convene agent, **not** the staged gateway venv executable.
They do not broaden this gateway rule but compound the open GW-01 management-plane
risk and must be dispositioned before a control-connected role.

---

## 5. NOT DONE — DELIBERATE — `RECLAIM-EdgeGateway` boot task

Withheld for this session by explicit guardrail.

**Both installer preconditions are now satisfied** by this staging session:
`install-gateway-task.ps1:18` checks for `.venv\Scripts\python.exe` (exists) and
`:19` for `config.windows.yaml` (exists). The script does not merely register the
task — line 40 **starts** it immediately.

**If installed today it would enter a permanent crash loop.** The staged config
has `listen_host: 192.168.50.1`, which is unassigned (§2), so the receiver thread
dies on bind, the process exits non-zero, and the task's
`-RestartCount 999 -RestartInterval 1 minute` restarts it every minute forever,
as SYSTEM — while also attempting POSTs to a placeholder URL.

**Ordering rule: install only after §2 (cRIO IPs) AND §3 (real cloud values) are
both complete.** Not before, and not "just to test the registration."

- [ ] §2 complete and verified
- [ ] §3 complete and verified
- [ ] Manual console run against the real `config.windows.yaml` succeeds first
- [ ] `.\windows\install-gateway-task.ps1` run elevated
- [ ] Task starts at boot with no login; survives a reboot
- [ ] Failure restart verified (kill the process → returns within 1 min)
- [ ] Clean stop verified (`Stop-ScheduledTask` → stays stopped, no resurrection)

Side effect to be aware of: the installer sets `RECLAIM_EDGE_CONFIG` as a
**machine-level** environment variable (`:22`), which persists beyond the task.

---

## 6. BLOCKED — §5 contract gates (all six)

**Blocker: no cloud endpoint.** All six run from a trusted shell against the
authenticated ingress. None can be exercised locally.

- [ ] **Fresh frame** — one v1 frame → 1 accepted, 0 errors; `/state` shows
      `schema_version: reclaim.state.v1`, `mode: live`, `run_id`, `source_id`,
      `seq`, `ts_source`, `cycle_id`, `source_op_state`, singular `op_state`,
      `PL_op_state`, `MT_op_state`, `ingest_status: accepted`
- [ ] **Duplicate** — repost the same frame → `duplicate`, ingestion count does
      not increment
- [ ] **Harness reject** — post `mode: harness` → rejected. The live-only proof
- [ ] **Stale gate** — batch of one stale + one fresh frame → HTTP **200** with
      per-frame results: stale = `rejected/timestamp_stale/final`, fresh =
      `accepted`. On the laptop, confirm the stale frame lands in `/health`
      `dead_letter`, **not** back in the queue
- [ ] **Gateway-restart gate** — restart the gateway task; new `run_id` →
      cloud logs `RUN_SUPERSEDED`, keeps accepting, `active_run_id` updates,
      zero operator action
- [ ] **Cloud-restart gate** — restart the ingest service, repost the last
      accepted frame → `duplicate` (identity restored from
      `RECLAIM_INGEST_STATE`); `ingested_total` does not double-step
- [ ] **Freshness decay** — stop the feed, poll `/state`: `state_age_ms` grows
      and Convene flips to **DATA NOT LIVE** at the agreed limit

---

## 7. BLOCKED — §6 three-column V&V (the gateway audit machine)

**Blocker: needs both cRIO and cloud.** This is formal verification and
validation of the data itself, and every later model discussion (ADR-001,
ADR-002, estimator alternatives) inherits its basis.

- [ ] Gateway running against the real cloud endpoint, **no Convene binding
      changed yet**
- [ ] Laptop registered as its own Convene machine publishing the `gw_` set
      per `deployment/CONVENE_GW_MAPPING.md` — separate namespace, read-only
      tap, never in the delivery path, **never writes `sim_*`**
- [ ] Audit view built: three columns per signal (LabVIEW indicator, `gw_*`,
      `sim_*`), with `gw_seq − sim_seq` and `sim_ingest_age_ms` as the live
      lag readout
- [ ] **Confirm the 27 raw `vars` names against the first real frame** and
      correct the mapping table if the stream differs (see §9.5)
- [ ] Unit conversions applied in the view (°C→K, mbar→kPa) so unlike units do
      not read as mismatches (`CONVENE_GW_MAPPING.md` §4.1)
- [ ] One full controlled sequence
      `S_BatchLoad → S_Evacuate → S_MicrowaveHeating → S_CoolDown → S_Complete`
      with all three columns in agreement at each transition
- [ ] Lag bound agreed with the team and met
- [ ] §4.5 RF coexistence check: Wi-Fi pinned to 5 GHz, `last_ack_age_s` and
      `dead_letter` watched **during** `S_MicrowaveHeating`

Only after this passes does §7 Convene cutover begin (one publisher, legacy
writers disconnected).

---

## 8. Critical path

```
§2 cRIO link ─┐
              ├─→ §4 firewall ─→ §5 boot task ─→ §6 contract gates ─→ §7 V&V ─→ Convene cutover
§3 cloud+tokens ┘
```

§2 and §3 are independent and can proceed in parallel. Everything downstream is
strictly ordered. Nothing after §5 can start early.

---

## 9. Environment deviations found during staging

These are real findings from this laptop, not doc nitpicks. Each needs a
decision from someone.

### 9.1 Preflight §1 remote access — RESOLVED 2026-08-17

The original §1 specified an OpenSSH server and tunneled status endpoint. The
preflight now records the actual outbound-only model: TeamViewer for hands-on
administration, Tailscale for the approved private network, and the existing
Convene agent for its narrow heartbeat/audit role.

The machine enforces a WDAC code-integrity policy and blocks inbound listener
services. **Do not attempt to stand up SSH/RDP listeners on this box.**

Gateway status remains loopback-only. Do not expose port 9080 through a status
tunnel because the endpoint has no application authentication (§9.4).

- [x] Preflight §1 rewritten around the approved outbound-only access model

### 9.2 Python version drift

Preflight §4.3 says "install Python 3.10+" and shows `py -3.10`; the staging
prompt pack assumed 3.12. **This box has only Python 3.13.0.** The venv was
built with `py -3.13`. 3.13 satisfies the 3.10+ target and all 10 gateway tests
pass on it, but no one has stated 3.13 as a supported version.

- [x] Python 3.13 is a supported target in the locked project/CI matrix; retain
      the staged 3.13 venv and re-run the locked gateway suite before go-live

### 9.3 Graceful shutdown path untested

The shakedown was terminated by an external kill, which on Windows does not
deliver a POSIX SIGTERM to Python, so `main.py`'s `_sig` handler never ran — no
`shutdown requested` / `stopped` lines. Thread liveness was proven by other
means (§1.8), but the clean-stop path — handler → `stop.set()` → thread joins →
`buffer.close()` → exit 0 — has **not** been exercised.

This matters because §5's task behavior ("never restarts a clean operator stop")
depends on that path producing exit 0.

- [ ] Run `python -m reclaim_edge.main` in an interactive console, press
      **Ctrl+C**, confirm the last two log lines are `shutdown requested` then
      `stopped`, and that the exit code is 0

### 9.4 Status server has no authentication

`status.py:72-86` has no token check on any endpoint; `/latest` serves raw
process telemetry. Safe today only because it binds `127.0.0.1` and the Convene
agent is local. Never give 9080 an inbound firewall rule. If it is ever
tunnelled, the tunnel must carry the authentication.

- [ ] Decide and document the policy before any tunnel exposes 9080

### 9.5 The 27 raw channel names are unverified against a real stream

`CONVENE_GW_MAPPING.md` §3 lists the `vars` keys from the docx export
reproduced at `labview_map.py:206-216`. No live cRIO frame has confirmed them.
With `strict_fields: false` the gateway forwards whatever arrives, so a name
mismatch would not error — it would silently produce empty `gw_` variables and
absent `sim_` fields.

- [ ] Capture the first real frame from `/latest`, diff its `vars` keys against
      the mapping table, correct the table, and only then consider
      `strict_fields: true`

### 9.6 Historical Pi-vs-laptop naming drift (`CODE_REVIEW.md` H6) — CLOSED

`README.md`, `FIXES.md`, and the architecture doc described a "Raspberry Pi 3B+
gateway" while the deployment is a Windows laptop; the preflight filename still
said `Pi` though its title already said laptop.

- [x] Prose and diagrams reconciled across `README.md`, `FIXES.md`, and
      `docs/RECLAIM_Live_Telemetry_Architecture.md`
- [x] Preflight renamed to `docs/RECLAIM_Remote_Gateway_Preflight.md`; all
      references updated
- [x] `FIXES.md` carries a dated platform note, so a 2026-08-10 changelog is
      not silently rewritten. Pi-specific *rationale* is retained where it
      explains why a fix exists (M5 warn-once and the bounded dead-letter table
      were driven by SD-card wear)
- [x] The retired Linux service unit was removed; the live gateway uses the
      Windows Scheduled Task template.
- [x] The `pi_gateway/` directory name is retained as a repository compatibility
      name only. It does not identify the deployment platform.

### 9.7 Historical Tailscale `reclaim-pi` node is offline

A `reclaim-pi` node exists in the tailnet but is offline. If it is a retired
artifact of the earlier Pi plan, remove it so it cannot be confused for a live
gateway.

- [ ] Confirm disposition

---

### 9.8 Convene agent — RESOLVED 2026-08-15, now running as SYSTEM at boot

**Was:** not running at all. Checked 2026-08-15 12:27 — no agent process,
service, or scheduled task; no Python process running anywhere; no `Run`-key
entry. `%USERPROFILE%\.convene` held only `convene_agent.py`.

**Root cause:** the agent had paired successfully on 2026-08-14 16:19
(`C:\Users\latitude4\.convene_agent.json`, 119 B, machine ID
`6xaiDIfauON8lGDVy2s1`) but had **no persistence mechanism** — it ran from a
console and died with it. The briefing's "paired and heartbeating" was true of
the pairing, not of any ongoing heartbeat.

**Now:**

- [x] Agent started and confirmed heartbeating (30 s interval); saved
      credentials reused, so no duplicate machine was registered
- [x] Credentials copied to `C:\Windows\System32\config\systemprofile\` —
      required because the agent reads `~/.convene_agent.json`, and SYSTEM's
      `~` is the SYSTEM profile, not the user profile
- [x] Scheduled Task **`Convene-Agent`** registered: `AtStartup` trigger,
      SYSTEM / RunLevel Highest, restart every 1 min on failure, no execution
      time limit, starts on battery. Launches
      `C:\Users\latitude4\.convene\run-agent.cmd`
- [x] Verified: exactly one agent process, owner `NT AUTHORITY\SYSTEM`, three
      established HTTPS sessions to the backend; `agent.log` shows
      `OK Using saved credentials` + `Heartbeating every 30s`
- [ ] **Confirm it comes back after a real reboot** — the boot trigger is
      registered but has not yet survived an actual restart
- [ ] Confirm in Convene that the machine shows as connected

**Logging:** the task appends to `C:\Users\latitude4\.convene\agent.log`
(`python -u`, unbuffered). This did not exist before and is the only on-disk
evidence the agent is alive — it grows unbounded, so rotate or truncate it
periodically.

### 9.9 Security posture of the Convene agent — read before extending it

The agent is a **remote-management agent, not a metrics reporter**. Recorded
here because it materially changes this laptop's exposure:

- `command_loop` polls the Convene backend every 2 s and executes whatever
  shell commands it returns, posting stdout/stderr/exit code back
  (`run_terminal_cmd`). `collect_from` also supports a `shell` collector type
  that runs arbitrary commands each heartbeat.
- It now runs as **SYSTEM at boot** (chosen deliberately — see §9.8), so that
  remote shell has full administrative rights on this machine.
- This is an outbound-polling design, so it works despite the WDAC block on
  inbound listeners. Note the consequence: it delivers the remote-access
  capability preflight §1 could not (§9.1), but through a third-party control
  plane rather than an authenticated tunnel the team operates.

**Never run the agent with `--desktop` on this machine.** That path sets
TightVNC `UseVncAuthentication=0` and `AllowLoopback=1` — screen sharing with
the VNC password disabled — then publishes it via a random
`trycloudflare.com` quick tunnel whose hostname is the only secret. The
launcher `run-agent.cmd` carries a comment saying so.

- [ ] Confirm the team accepts a SYSTEM-level third-party remote shell on the
      gateway laptop, and record it wherever §9.1's access model is decided
- [ ] Decide who may issue commands from the Convene side, and whether that
      account set is access-controlled

## 10. Changelog

| Date | Change |
|---|---|
| 2026-08-19 | Onsite physical link established at 1 Gbps; laptop `192.168.1.1/24` and operator-confirmed cRIO `192.168.1.2/24` preserved as the approved lab subnet. Laptop-to-cRIO ping passed; Wi-Fi remained the only default route on 5 GHz. Applied the rollback-capable network script: Ethernet is Private and TCP 9070 is allowed only from the cRIO to the laptop on that interface; 9080 remains unopened. Listener, cRIO-side gateway/reverse-ping evidence, and cRIO-to-9070 reachability remain pending. |
| 2026-08-17 | Corrected the authoritative live topology to a cloud-hosted Windows Server 2025 VM in Kubernetes-managed infrastructure and a Windows 10 gateway laptop; retired Linux service units, rewrote VM/preflight procedures for Windows, and closed §9.1/§9.2 documentation decisions. |
| 2026-08-15 | Handoff docs authored — `deployment/HANDOFF.md` (full project story) and `deployment/VM_ENGINE_SESSION_BRIEF.md` (turnkey brief for the cloud VM session). The Convene agent's always-on-at-boot status (§9.8) is framed there as the **architectural base** for the deferred ingress/egress build. Egress tunnel decision recorded: Cloudflare **quick tunnels** first, named tunnel + domain when interoperability warrants. Ingress/egress bring-up deliberately deferred. |
| 2026-08-15 | Convene agent started and made boot-persistent as SYSTEM (task `Convene-Agent`); §9.8 closed, §9.9 added recording its remote-shell capability. |
| 2026-08-15 | §9.6 closed — Pi-vs-laptop naming reconciled across `README.md`, `FIXES.md`, the architecture doc, and the preflight filename (now `RECLAIM_Remote_Gateway_Preflight.md`); two sub-items left open. §9.8 added: Convene agent confirmed **not running**, blocking §7. |
| 2026-08-14 | Created. §1 populated from the offline staging session (repo verify, staging, config, console shakedown, `gw_` mapping). §2–§8 opened as blocked/deliberate. §9 findings recorded. |
