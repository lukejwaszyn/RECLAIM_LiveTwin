# cRIO Telemetry Socket — Setup and Configuration

**Scope.** How to set up and configure the single TCP socket that carries the RECLAIM
telemetry shadow stream from the cRIO to the Windows edge gateway. This is the
offline→live interface: it specifies both ends of the wire so that a cRIO producer
built to this document mates with the existing gateway receiver without surprises.

**Boundary (unchanged).** Building or deploying the cRIO producer is gated (Gate 3+)
and controls-authorized; this document is the spec you build to, not permission to
deploy. The link is plaintext by design — it lives entirely on the isolated OT LAN, and
TLS is applied only on the gateway's WAN side by the publisher. Do not add TLS,
authentication, or any return/command channel to this socket.

## 1. Endpoints and roles

| Property | cRIO (producer) | Gateway (consumer) |
|---|---|---|
| Device | cRIO-9024, VxWorks/PowerPC, LabVIEW 2019 | Windows 10 edge gateway |
| Address | `192.168.1.2/24` | `192.168.1.1/24` |
| Socket role | **TCP client** — opens the connection | **TCP server** — listens on `9070` |
| Direction | write-only (never reads frames back) | read-only (never sends — verified: no `send`/`sendall` in `receiver.py`) |
| Concurrency | exactly one connection | serves one connection at a time (`listen(1)`) |

The gateway never initiates and never transmits on this socket. The cRIO is the sole
client; a second client would sit in the backlog until the first is dropped.

## 2. Wire framing (the contract both ends enforce)

One frame is one UTF-8 JSON object followed by exactly one LF (`0x0A`):

```
{"source_id":"reclaim-crio-rt-01","ts":"2026-08-20T15:42:10.250Z","cycle_id":"…","source_op_state":"S_MicrowaveHeating","active_chamber":"PL","vars":{…}}\n
```

Rules the producer must honor, all enforced by `parse_line`/the framer on receipt:

- **UTF-8, ASCII in practice.** All field names and numbers are ASCII; there are no
  multibyte characters, so on the cRIO a plain byte string is correct. Emit JSON
  booleans as lowercase `true`/`false` — *not* the USB record's `TRUE`/`FALSE` text —
  and finite JSON numbers only (no `NaN`/`Infinity`; omit an invalid channel instead).
- **One line per frame.** Serialize compact (no pretty-printing) so the JSON contains
  no embedded newline, then append a single `0x0A`. Emit LF only, not CRLF; a stray
  `\r` is tolerated (the receiver strips it) but should not be sent.
- **Size bound: 8192 bytes including the LF.** Measured real frames run ~200–1319 B, so
  this is comfortable, but the producer must treat a would-be oversize frame as a
  contract error, never truncate it. The receiver drops any line that reaches 8192
  bytes before an LF.
- **Whole frames only.** Never send a partial frame; one source snapshot produces one
  complete line.

`crio_source_record/frame_builder.py` is the executable reference for this framing —
its byte output is exactly what the receiver accepts.

## 3. Gateway (server) socket configuration

The receiver is already built; these are the knobs on `reclaim_edge.config.Config`
(set via the YAML selected by `RECLAIM_EDGE_CONFIG` on the Windows gateway). It sets
`SO_REUSEADDR`, enables `SO_KEEPALIVE`, and on Linux tunes `TCP_KEEPIDLE/INTVL/CNT`;
the Windows host applies its own keepalive defaults.

| Setting | Recommended | Meaning / effect |
|---|---|---|
| `listen_host` | `192.168.1.1` | Bind to the OT NIC specifically on the dual-homed gateway, rather than `0.0.0.0`, so `9070` is never offered on the WAN interface. |
| `listen_port` | `9070` | The telemetry ingress port. |
| `max_line_bytes` | `8192` | Pre-LF line bound; must equal the producer's cap. |
| `conn_idle_timeout_s` | `10`–`30` | A connection silent this long is dropped so a reconnect can be served (half-open defense). Keep it above several telemetry periods so normal jitter never drops a live link; lower it toward 10 s for faster recovery after an ungraceful cRIO drop (see §5). `0` disables the drop — not recommended. |
| `strict_fields` | `false` | Preserve the raw LabVIEW field names for cloud normalization. Do not set `true` until the full raw manifest is maintained at the gateway. |
| `buffer_path` / `buffer_max_frames` | site path / `500000` | Durable store-and-forward queue; drop-oldest beyond the cap. |

## 4. cRIO (client) socket configuration

Build the producer's socket with finite timeouts everywhere and no blocking call that
can stall a control loop.

| Setting | Recommended | Rationale |
|---|---|---|
| Connect target | `192.168.1.1:9070` | The gateway listener; TCP Open Connection with a finite timeout. |
| Connect timeout | ~2 s | Fail fast and retry with backoff rather than hang. |
| Write timeout | < one cadence (e.g. 0.5–1 s) | A write that can't complete promptly means the peer is gone; drop and reconnect. |
| Nagle / `TCP_NODELAY` | not exposed in base LabVIEW TCP | Not required here — each frame is one bounded write ending in LF, so coalescing latency is a non-issue. Only relevant if a lower-level socket config is ever added. |
| `SO_KEEPALIVE` | enabled | Secondary detection of a dead gateway between frames. |
| Encoding | UTF-8/ASCII bytes + `0x0A` | See §2. Build the JSON as a byte string; append one LF. |
| Cadence | source-driven (~0.38 s observed) | One frame per source snapshot. Per-frame `ts` (not a fixed 1 Hz clock) is what keeps frames inside the cloud freshness window. |
| Connections | exactly one, long-lived | Open once, reuse; do not open a socket per frame. |

The producer must **not** open a listener, read commands, write a shared variable back
to the gateway, or hold any output/setpoint/deploy reference. The socket is telemetry
egress only.

## 5. Reliability behavior

- **Latest-wins, drop-on-stall.** The control/sequencer path writes its latest
  immutable snapshot into a depth-one, lossy handoff (an RT FIFO of size one, or a
  single-element tag with overwrite). The telemetry loop reads the latest, serializes,
  and writes it. If the socket write can't keep up, the unsent frame is discarded — the
  telemetry loop never waits, and never applies backpressure to control.
- **No replay.** After a disconnect, discard any unsent frame. Do not queue history on
  the cRIO; the gateway's durable buffer owns store-and-forward, and the cloud dedupes
  by `run_id`+`seq` and rejects stale timestamps.
- **Reconnect with bounded backoff.** On connect/write failure, close, wait a bounded
  backoff (e.g. 1 s, capped at 5–10 s), and retry. Expect a delay after an *ungraceful*
  cRIO drop: because the gateway serves one connection and holds the half-open one until
  `conn_idle_timeout_s`, the reconnect is only accepted once that timer frees the
  listener. Size the producer's backoff and the gateway's idle timeout together so
  recovery is prompt but a live link is never dropped on jitter.
- **Half-open peers.** Both ends enable keepalive; the gateway additionally drops an
  idle connection. The producer's write timeout is the primary, fastest detector of a
  vanished gateway.

## 6. RT-safety placement on the cRIO (LabVIEW)

Run the socket work in a **separate, lower-priority loop**, fully decoupled from the
deterministic control loop by the depth-one lossy handoff above. TCP Open, TCP Write,
and TCP Close all carry finite timeouts; on any error the loop closes the connection
and enters the reconnect backoff. Nothing in the telemetry loop — serialization,
connect, or write — may sit on the control loop's timing, interlocks, watchdogs, or the
USB logger. Telemetry loss must be invisible to the process.

### 6.1 Worked producer sketch (LabVIEW RT)

Two loops share one size-one RT FIFO. The control loop writes the latest snapshot and
never blocks; the telemetry loop reads the latest, serializes, connects, and writes.
RT FIFO elements must be **fixed-size**, so the snapshot carries scalars and enums only
— the operating state as a signed code, the chamber as an enum, `cycle_id` as a
fixed-width id, `ts` as a timestamp — and the string mapping plus JSON build happen in
the low-priority loop, off the control path. This is a mechanism sketch, not deployable
code; every value the telemetry loop fills from a code or enum is a signed-map
dependency.

```text
Shared:  SNAP = RT FIFO "telemetry_snap", size 1, element = SnapshotCluster
         (all fixed-size: the ~34 DBL/bool channels, op_state as U16 code,
          chamber enum {PL,MT,NONE}, cycle_id U64, ts timestamp).
         RT FIFOs overwrite when full -> depth-one, latest-wins, never blocks.

Control / sequencer loop  (time-critical, deterministic — timing unchanged):
    after the existing record is assembled each iteration:
        RT FIFO Write(SNAP, snapshot)         # non-blocking; overwrites any unread value
    # no TCP, no serialization, no wait here — telemetry can never stall this loop

Telemetry loop  (normal / low priority; its own loop, decoupled by SNAP):
    conn    = <not connected>                 # shift register
    backoff = 1000 ms                         # shift register, cap 10000
    loop:
        if conn == <not connected>:
            conn, err = TCP Open Connection(addr="192.168.1.1", port=9070, timeout=2000ms)
            if err:  Wait(backoff); backoff = min(backoff*2, 10000); next
            backoff = 1000
        val, timed_out = RT FIFO Read(SNAP, timeout=0ms)     # latest only; empty -> skip
        if timed_out:  Wait(20ms); next                      # no new snapshot yet
        json = build_frame(val)              # map op_state code->signed string, chamber enum
                                             # ->PL/MT/NONE, assemble compact JSON;
                                             # assert byte_length + 1 <= 8192
        n, err = TCP Write(conn, json + LF(0x0A), timeout=500ms)
        if err:
            TCP Close Connection(conn); conn = <not connected>   # discard frame, NO replay
            Wait(backoff); backoff = min(backoff*2, 10000)
    on stop:  TCP Close Connection(conn)
```

Notes on the primitives:

- Keep variable-length data (strings, unbounded arrays) out of the RT FIFO — map codes
  to strings in the telemetry loop. A single-process shared variable with RT-FIFO
  buffering off, or a functional global, gives the same last-value-wins handoff if you
  prefer them to an explicit RT FIFO.
- Set finite timeouts on every TCP primitive: `TCP Open Connection` ~2000 ms,
  `TCP Write` ~500 ms (below one cadence). Branch on their error outputs; never wire a
  `-1` (infinite) timeout, which is what turns a dead peer into a wedged loop.
- Append the LF as a single byte (`0x0A`) to the compact JSON; do not use a
  line-writing function that could inject CRLF.
- On any write error, close and reconnect — do not retry the same frame. The gateway
  buffer and the cloud dedupe/staleness gates own recovery; the producer's job is only
  to deliver the freshest snapshot or nothing.

## 7. Network and firewall setup

1. Confirm static addressing on the isolated segment: cRIO `192.168.1.2/24`, gateway
   `192.168.1.1/24`, same subnet, direct cable or a dedicated switch with no other
   traffic.
2. On the gateway, allow **inbound TCP 9070 only from `192.168.1.2`** and only on the
   OT NIC. The repo's `pi_gateway/windows/configure-crio-network-firewall.ps1` is the
   intended helper for this rule; review it against the site before running.
3. Bind the gateway listener to `192.168.1.1` (§3) so the port is never exposed on the
   WAN NIC, and keep the loopback status port (`9080`) off any tunnel.
4. Do not open any path from this segment to the cloud; the gateway's WAN NIC and the
   TLS publisher handle egress separately.

## 8. Validation ladder

Prove the socket in this order; each step is a precondition for the next, and the live
steps remain gated on the controls owner.

1. **Loopback bench (no cRIO, available now).** `crio_source_record/bench_replay.py`
   streams sanitized fixtures over a real TCP socket into the real receiver, buffer, and
   cloud engine — this exercises the framing, the 8192-byte bound, reconnect, and
   duplicate/stale handling end to end without any cRIO.
2. **Supervised one-frame at the gateway (Gate 4).** With the process idle and baseline
   captured, have the producer send exactly one frame; confirm it appears at the gateway
   and matches the same-time LabVIEW indicators and USB record.
3. **Sustained shadow (Gate 4).** Run at least five minutes; verify cRIO load, loop
   timing, watchdogs, USB logging, gateway counters, and VM freshness are unaffected.
4. **Fault and restart (Gate 5).** Disconnect/reconnect the cable and restart the
   gateway; demonstrate bounded reconnect, latest-wins, no stale replay, and no control
   or logging disruption.

## 9. Do-not list

- No TLS, auth, or command/return channel on this socket.
- No listener, shared-variable write-back, output, setpoint, or deploy reference in the
  producer.
- No per-frame socket open/close; no on-cRIO replay queue.
- No blocking socket call on the control loop's path.
- No exposure of `9070` on the WAN NIC or of the loopback status port through a tunnel.
- No frame truncation to fit the byte bound — an oversize frame is a contract error.

## 10. Consolidated parameter reference

| Parameter | Value | Owner/where |
|---|---|---|
| Gateway endpoint | `192.168.1.1:9070` | fixed |
| cRIO source address | `192.168.1.2/24` | fixed |
| Line framing | UTF-8 JSON + single `0x0A` | contract (`frame_builder.py`) |
| Max line (incl. LF) | 8192 bytes | `max_line_bytes` / producer cap |
| Gateway listen bind | `192.168.1.1` | `listen_host` |
| Gateway idle drop | 10–30 s | `conn_idle_timeout_s` |
| Gateway strict fields | `false` | `strict_fields` |
| Connect timeout | ~2 s | producer |
| Write timeout | < one cadence | producer |
| Reconnect backoff | 1 s → 5–10 s cap | producer |
| Keepalive | enabled both ends | producer + `receiver.py` |
| Nagle | n/a in base LabVIEW TCP; not required | producer |
| Cadence | source-driven (~0.38 s) | producer |
| Firewall | inbound 9070 from `192.168.1.2` only | gateway OT NIC |
