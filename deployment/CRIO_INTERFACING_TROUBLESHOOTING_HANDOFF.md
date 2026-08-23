# cRIO Interfacing — Troubleshooting Handoff

> **Stage:** 3 → Gate 4 · **Use when:** the cRIO is physically connected and you are
> chasing why frames are not arriving, not validating, or not reaching the VM or
> Convene. · **Advisory path only — no command, return, or actuation path exists
> or may be added.**

Everything downstream of a frame **has already been proven end to end** with a real
frame through the real path (§1). So when something breaks after the cable goes in,
the fault is almost certainly upstream of the gateway or in the frame *contents* —
not in the transport. Work the ladder in §3 in order; each rung tells you which
side of the seam the problem is on.

---

## 1. Known-good baseline (proven 2026-08-23, commit `47c2ba3`)

Do not re-debug these. They were measured, not assumed:

| Thing | Evidence |
|---|---|
| Seam A: TCP → framer → durable queue | `received 0 → 1` on a live probe frame |
| Seam B: queue → Cloudflare → VM `/ingest` | `delivered 1`, `queue_depth 0`, `last_ack_age_s 18.23` (**the VM acked**) |
| Convene `gw_` audit tap | `machine_id BcryPSMP2iLbSRns5uhm`, `delivered 1`, `failed 0` |
| Validation / dead-lettering | `dead_lettered_session 0` on a well-formed frame |
| Gateway survives link-down | Ethernet `Disconnected`, `9070` still bound, `/health` serving |
| Graceful stop + restart | SIGTERM → drain → `buffer.close()`; seq high-water mark survives restart |
| **Sustained load, both seams** | **450 frames at 400 ms: received 450, VM-ingested 450, dead-letter delta 0, queue drained** |
| Convene tap under load | 270 delivered + 180 coalesced = 450; `failed` 0. Coalescing is by design, **not** loss |

**The `9070` listener survives an unplugged cable because the NIC address is
statically assigned** (`PrefixOrigin: Manual`). If anyone ever switches that
interface to DHCP, the address disappears on link-down and the bind breaks — that
would be a new failure mode, not a regression.

---

## 2. First-frame checklist (run in this order)

```powershell
# 1. Is the cRIO actually connected?
Get-NetTCPConnection -LocalPort 9070 -RemoteAddress 192.168.1.2 |
  Where-Object State -eq 'Established'

# 2. Is the gateway healthy and counting?
Invoke-RestMethod http://127.0.0.1:9080/health

# 3. What did the last frame actually look like?
Invoke-RestMethod http://127.0.0.1:9080/latest
```

Expected on a healthy link: an established connection from `192.168.1.2`;
`received` advancing at the source cadence (~0.38 s); `delivered` tracking
`received`; `queue_depth` near zero and draining; `dead_lettered_session` **staying
0**; `convene.delivered` advancing. Never tunnel `9080`.

---

## 3. Fault ladder — where is the problem?

### Rung 1 — No established connection on 9070

The gateway is listening but the cRIO is not connected.

- Confirm the adapter is up: `Get-NetAdapter` — `Ethernet` must not read
  `Disconnected`. A disconnected adapter is the single most common cause of
  "nothing is arriving," and the gateway looks perfectly healthy while it happens.
- Confirm the gateway owns the port and only one process does:
  `Get-NetTCPConnection -State Listen -LocalPort 9070` → exactly one row, on
  `192.168.1.1`. Two gateway *processes* is normal (the scheduled task launches a
  thin single-threaded parent whose child does the work); two *listeners* is not.
- Confirm the firewall has not drifted: run
  `.\pi_gateway\windows\configure-crio-network-firewall.ps1` in **Audit** mode.
  Apply only if it reports drift.
- The cRIO reconnects on its own once the path is restored. Do not restart the
  gateway to "force" it.

### Rung 2 — Connected, but `received` never advances

The socket is up and the producer is silent, or the frames are unreadable.

- A half-open socket (cable pulled without a clean close) is detected by the
  receiver's idle timeout (15 s). If `received` is frozen but the connection still
  shows Established well past that, suspect the producer, not the gateway.
- Frames are **newline-delimited JSON**. A producer that omits the trailing newline
  will look exactly like silence — the receiver is still waiting for the delimiter.
- `max_line_bytes` is 8192. An oversized frame is a line-local failure, not a
  connection failure.

### Rung 3 — `received` advances but `dead_lettered_session` climbs

Frames are arriving and failing validation. **This is a producer/contract problem,
not a transport problem.** Read `/latest` and compare against
`CRIO_TELEMETRY_SOCKET_SETUP.md`.

`strict_fields` is `false`, so unknown fields are preserved and warned about once
(not per frame — the log will not flood). Missing or non-scalar *required* identity
fields are what actually reject.

### Rung 4 — Gateway accepts, cloud rejects every frame

**The known trap, and the most likely single failure you will hit.** If `PL_bottom2`
is quarantined without a complete-or-drop bank policy, frames pass the gateway but
the cloud rejects each one *whole* (`telemetry_invalid`) — and MT/MW values are lost
with it, so it looks like a total outage rather than one bad channel.

**Do not "fix" this downstream.** The producer must send each bed bank complete or
entirely absent. Record it as **Gate 3 checklist item 6.3** evidence.

Confirm with a capture (insert nothing between the cRIO and the listener):

```powershell
python -m crio_source_record.conformance --cloud --refresh-ts capture.ndjson
```

Expect 0 gateway fails and 0 cloud rejections.

### Rung 5 — Everything flows but Convene shows nothing

**Machine presence is not telemetry.** Convene will show the machine as connected
purely from the agent heartbeat, with zero variables arriving. Check
`convene.delivered` in `/health`, not the Convene machine list.

- `convene.machine_id` is `null` until the **first delivery** — the credential loads
  lazily. A null machine_id with `received: 0` means "never exercised," not "broken."
- `convene.failed` climbing is the real failure signal. A 401 means the credential
  is revoked; the SYSTEM profile
  (`C:\Windows\System32\config\systemprofile\.convene_agent.json`) and the user
  profile must hold the *same* identity — they diverged once before.
- **Ignore the agent's HTTP 500 heartbeat spam.** That is a separate, backend-owned
  Convene defect (a missing Firestore composite `machineCommands` index). It breaks
  heartbeat-returned `autoVars` and the command plane. It does **not** affect
  `/machine/publish`, which is how `gw_` variables actually travel.

---

## 4. Reproducing without the cRIO

Both senders drive the **real** ingress path, read no credential, refuse to inject
while a real cRIO peer is connected, and label every frame as synthetic. Use them
to prove the gateway is innocent before blaming it.

```powershell
# one frame
.\pi_gateway\windows\send-commissioning-frame.ps1  -VmBaseUrl https://<vm-host>

# sustained (60-1800 s), at approximately the real source cadence
.\pi_gateway\windows\send-commissioning-stream.ps1 -VmBaseUrl https://<vm-host> `
    -DurationSeconds 180 -FrameIntervalMilliseconds 400
```

The VM host is in the gateway's runtime config (`cloud_url` in
`C:\RECLAIM\pi_gateway\config.windows.yaml`) — read it programmatically rather than
pasting it onto a command line, and never into a log, commit, or screenshot.

The stream enforces its own invariant: **retained dead letters must not increase**
during the run.

---

## 5. Things that look like bugs and are not

- **`status: running` on a rehearsal engine after data stops** — fixed; it now
  reports `status: stopped`. If you see `running` over frozen `t_sim`, you are on a
  build older than `01643df`.
- **Two `python -m reclaim_edge.main` processes** — normal. The scheduled task
  launches a thin parent (single thread, no TCP endpoints) whose child owns the
  ports. Only one listener exists.
- **159 persisted dead letters** — historical, accepted by the owner. Only
  `dead_lettered_session` matters during a run.
- **A `.ps1` that will not parse under Windows PowerShell 5.1** — check for
  non-ASCII characters in a BOM-less file. 5.1 decodes BOM-less `.ps1` as ANSI, and
  an em dash becomes a smart quote that terminates a string early. Keep `.ps1`
  files ASCII-only. **Validating with `pwsh` 7 will not catch this** — pwsh assumes
  UTF-8 and parses the broken file happily.
- **Scripts refusing to run at all** — execution policy. Use
  `powershell -NoProfile -ExecutionPolicy Bypass -File <script>`.

---

## 6. Hard boundaries while troubleshooting

- No cRIO edit, VI run, redeploy, or network re-addressing. Producer faults get
  **recorded and handed to controls**, never patched downstream.
- Never expose `9080` through a tunnel; no default route on the OT-facing NIC.
- No secret on a command line, in a commit, log, or screenshot.
- Do not overwrite the runtime baseline `C:\RECLAIM\pi_gateway`, its
  `config.windows.yaml`, `queue.db`, or state. When unsure whether a folder is
  runtime or a stray source copy, **rename it aside and report — do not delete.**
- Gates 0/1/3 are controls/onsite-owned. Do not self-sign or claim them.

---

## 7. Still-open items that will shape what you see

- **Signed maps are UNSIGNED (Gate 1).** `cycle_id`, `source_op_state`,
  `active_chamber` and every raw channel are placeholder/unratified. Expect the VI
  to supply different semantics; that resolution is deliberately deferred until the
  link is live.
- **`cycle_id` may not exist at all.** Accepted for now: the engine is rebuilt per
  batch (the rehearsal harness already does this per cycle), so no reset edge is
  required. This only bites on **live continuous operation across multiple batches
  in one persistent engine**, where charge mass would decay without ever recharging
  and energy would become a lifetime total. If that becomes the operating mode, the
  fix is a derived cold-dwell-then-reheat boundary in the **engine** (never in the
  gateway, which must not fabricate values).
- **27 raw `vars` names unconfirmed** against a real frame (GO_LIVE §9.5).

**Standing status: labeled engineering shadow — NO-GO for any production claim.**
