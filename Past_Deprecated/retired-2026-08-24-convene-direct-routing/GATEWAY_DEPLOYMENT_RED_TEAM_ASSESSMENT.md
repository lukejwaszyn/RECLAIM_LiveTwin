# Gateway Deployment Red-Team Assessment

**Date:** 2026-08-16  
**Scope:** `pi_gateway/`, deployment scripts/runbooks, the cloud-returned command relay, and documented laptop-host security boundary.  
**Method:** Static source/configuration review plus narrow local behavior checks. No implementation files were modified.

## Executive conclusion

The gateway has good foundations—durable local queuing, per-frame cloud acknowledgements, sequence persistence for pinned runs, and an explicit deployment checklist—but it is **not ready to be treated as a trusted control gateway**.

The decisive risks are at the deployment boundary:

1. the same laptop is documented to run a SYSTEM-level remote-command agent;
2. the gateway accepts unauthenticated, unbounded plaintext data from the cRIO-side TCP socket;
3. cloud-returned commands are relayed without a local validity, schema, or authority check; and
4. outage recovery can process stale FIFO backlog for a long period rather than prioritize recovery to current telemetry.

For a telemetry-only, supervised demonstration this can be managed with network isolation and manual controls. For a gateway whose returned command can influence microwave power or safe state, the P0/P1 findings are release blockers.

## Severity model

- **P0:** A credible compromise or failure can command/disable a control boundary, expose the control host, or prevent safe recovery. Do not deploy in a control-connected role.
- **P1:** A credible remote/local fault can cause sustained telemetry loss, unsafe stale command use, or silent loss/corruption of operational data. Fix before live operational trial.
- **P2:** Important hardening/reliability deficit. Fix before scale-up or after compensating controls are demonstrated.

## Findings

### GW-01 — SYSTEM-level remote command agent shares the gateway host

**Severity:** P0 — deployment release blocker if the documented agent remains enabled.

The deployment document says the Convene agent runs as `SYSTEM` at boot and polls its backend for commands that it executes using a shell:

- [Archived `GATEWAY_GO_LIVE.md`](Past_Deprecated/deployment/retired-2026-08-24-convene-routing/GATEWAY_GO_LIVE.md#L367-L392).

That host stores the cloud ingest token, receives cRIO telemetry, maintains the durable queue, and exposes the local command relay. Compromise of the third-party control plane, its credentials, or an authorized operator account becomes full administrator compromise of the control gateway.

**Impact:** An attacker can alter the gateway configuration, replace code, read the ingest token, manipulate/delete the queue, inject or suppress telemetry, and influence the local command/HMI boundary. Cloudflare tunnel and ingress-token protections do not compensate for an already privileged process on the gateway itself.

**Required remediation:** Do not colocate a general remote-shell agent with a safety-relevant gateway. Use a separate, least-privileged host or remove arbitrary-command/shell-collector capability. If remote administration is required, use an allowlisted, audited management plane with strong identity, approval, code signing, and no access to gateway secrets or actuator interfaces.

### GW-02 — Cloud command is replayed locally without local validation or fail-closed expiry

**Severity:** P0 for any control-connected HMI/actuator; P1 for advisory-only use.

The HTTPS transport copies any JSON object in the cloud response into `last_command`:

- [`publisher.py`](pi_gateway/reclaim_edge/publisher.py#L89-L110).

The local status server then returns that object verbatim, only adding an informational age value:

- [`status.py`](pi_gateway/reclaim_edge/status.py#L41-L49).

The gateway does not enforce a command schema, command ID, source-frame/run/sequence correlation, maximum power, allowed mode transition, local sensor health, timestamp expiry, or signature. The documented design delegates stale-command invalidation to the HMI:

- [Archived `RECLAIM_Remote_Gateway_Preflight.md`](Past_Deprecated/docs/retired-2026-08-24-convene-routing/RECLAIM_Remote_Gateway_Preflight.md#L212-L217).

**Impact:** A malformed, stale, replayed, or compromised cloud response becomes a locally available control command. Safety rests on every HMI/control-hub client correctly implementing an undocumented fail-closed policy.

**Required remediation:** Treat the cloud output as an advisory, not an actuator command, until there is a local safety governor. The gateway/control hub must validate an authenticated command envelope containing command ID, issued/expires timestamps, source run/sequence, allowed chamber, setpoint bounds, and safe-state semantics. It must fail closed after a short deadline and must not use a command whose matching telemetry is missing, stale, or unhealthy.

### GW-03 — The cRIO receiver is unauthenticated, unbounded, and single-client

**Severity:** P1 — operational availability/integrity blocker on the trusted-LAN boundary.

The receiver accepts plaintext TCP on a configurable host/port:

- [`receiver.py`](pi_gateway/reclaim_edge/receiver.py#L34-L48).

It services one connection synchronously (`listen(1)` followed by `_serve`) and appends received data to `buf` until a newline occurs, without a maximum line length or receive-buffer bound:

- [`receiver.py`](pi_gateway/reclaim_edge/receiver.py#L71-L90).

No peer authentication, IP allowlist, source identity binding, or message authentication is implemented. The deployment plan relies on a direct isolated link and a firewall rule, which is a useful compensating control but does not protect against a compromised/misconfigured cRIO or a device on that segment.

**Impact:** One client can hold the sole connection open and continuously send non-newline bytes, consuming memory and preventing cRIO reconnection. A sender can inject frames if it reaches the port. An invalid JSON type can crash the receiver (see GW-04).

**Required remediation:** Bind only to the dedicated interface; enforce a host firewall remote-address allowlist; add source authentication or a message MAC; limit concurrent/single-client behavior explicitly; set hard maximum frame and buffered-byte limits; reject/close slow or malformed senders; and expose receiver rejection/oversize metrics.

### GW-04 — Valid JSON with the wrong top-level type crashes the receiver thread

**Severity:** P1 — trivial denial of service from the cRIO-side network.

`parse_line()` accepts any JSON value:

- [`framer.py`](pi_gateway/reclaim_edge/framer.py#L103-L115).

`Framer.build()` assumes the result is a mapping and calls `.get()` outside the receiver’s parse-error handler:

- [`framer.py`](pi_gateway/reclaim_edge/framer.py#L49-L56), [`receiver.py`](pi_gateway/reclaim_edge/receiver.py#L92-L108).

**Observed local check:** `Framer(Config()).build(parse_line('[]'))` raises `AttributeError: 'list' object has no attribute 'get'`. The main process detects the dead receiver thread and restarts, but a continuing malformed sender causes repeated restart/denial of service.

**Required remediation:** Require a JSON object at the parser boundary; validate the complete frame shape and value types before calling `Framer.build`; catch framing/enqueue errors per frame; rate-limit error logs; and add regression tests for arrays, scalars, nested values, overlong lines, invalid UTF-8, and connection-flood behavior.

### GW-05 — Live transport permits plaintext URL and disabled TLS verification

**Severity:** P1 — confidentiality/integrity failure for the cloud seam.

Live HTTPS configuration checks only that the token is non-empty:

- [`config.py`](pi_gateway/reclaim_edge/config.py#L126-L136).

It does not require an `https://` URL, approved hostname, or `verify_tls=True`; disabled verification only logs a warning. The HTTPS transport passes the configuration directly to `requests`:

- [`publisher.py`](pi_gateway/reclaim_edge/publisher.py#L71-L77).

**Observed local check:** a `Config` with `transport='https'`, `mode='live'`, `cloud_url='http://…'`, and `verify_tls=False` is constructible.

**Impact:** Misconfiguration can send telemetry and bearer credentials over plaintext or allow a man-in-the-middle to read/modify telemetry and inject a returned command.

**Required remediation:** In live mode require `https`, TLS verification, a non-placeholder approved hostname, and an explicit CA/pinning policy. Make insecure transport a hard error, not a warning. Prefer mTLS or a short-lived workload credential over a static bearer token.

### GW-06 — FIFO outage recovery can prolong stale data and delay recovery

**Severity:** P1 — live operational availability blocker.

Frames are stored FIFO and the publisher always drains the oldest batch:

- [`buffer.py`](pi_gateway/reclaim_edge/buffer.py#L78-L83), [`publisher.py`](pi_gateway/reclaim_edge/publisher.py#L178-L217).

The cloud rejects stale frames finally; the gateway then dead-letters them. This avoids permanent head-of-line blocking per batch, but it does not prioritize current data. With a `500,000`-frame queue, batches of `50`, and a normal 0.5 s interval, a long outage can require an extended stale-drain period before current frames reach the cloud. New frames continue joining the tail during that period.

**Impact:** The pipeline can remain operationally blind after connectivity returns. A large stale backlog also creates dead-letter churn and destroys the assumption that store-and-forward restores useful live telemetry.

**Required remediation:** Set a bounded offline-retention policy aligned to the cloud freshness window; discard/dead-letter locally expired frames before upload; offer a recovery mode that retains only the newest usable sample per chamber/stream (while preserving a separate audit log); publish an explicit `BACKLOGGED / DATA_NOT_LIVE` condition; and test outage/recovery at maximum expected telemetry rate.

### GW-07 — A permissive or malformed 2xx response can acknowledge and delete a batch

**Severity:** P1 — silent data-loss risk.

When the HTTPS response has status 2xx but does not include a `results` list of the expected length, the publisher assumes an old server and acknowledges every payload:

- [`publisher.py`](pi_gateway/reclaim_edge/publisher.py#L89-L100).

This also accepts a malformed JSON response, an HTML/body rewriting proxy response, or an unexpected compatible-looking endpoint as a full successful ingest.

**Impact:** Frames can be deleted from the durable queue without proof the intended cloud engine processed them.

**Required remediation:** In production require schema version, batch/correlation ID, response content type, exact result indices, and a validated disposition for every sent frame. Legacy compatibility must be an explicit non-production feature flag, not an implicit fallback.

### GW-08 — Live raw-schema passthrough accepts unvalidated fields and values

**Severity:** P1 — data integrity risk; directly compounds predictive-engine faults.

`strict_fields` is deliberately false in the live deployment configuration so raw LabVIEW fields survive to cloud-side normalization:

- [Archived `RECLAIM_Remote_Gateway_Preflight.md`](Past_Deprecated/docs/retired-2026-08-24-convene-routing/RECLAIM_Remote_Gateway_Preflight.md#L162-L185).

In this mode unknown fields are retained and only warned once:

- [`framer.py`](pi_gateway/reclaim_edge/framer.py#L58-L80).

The gateway performs no validation of field type, finiteness, units, range, timestamp, sequencer state, or active-chamber value before persistence/upload.

**Impact:** Field-name drift, type drift, malformed/oversized values, or corrupt telemetry are delayed until cloud processing, where the current predictive engine also has incomplete numeric validation. This can become either silent loss of required channels or an estimator/control fault.

**Required remediation:** Capture and version the real cRIO schema before live use. Validate an allowlisted raw schema at the gateway, including finite numeric/range checks and message size. Keep raw archival separate from the strict safety telemetry envelope. Reject rather than merely warn on safety-critical field changes.

### GW-09 — The local status endpoint has no application authentication

**Severity:** P2 locally; P1 if exposed by an incorrectly configured tunnel.

Every endpoint on port 9080, including raw `/latest` telemetry and `/command`, is unauthenticated:

- [`status.py`](pi_gateway/reclaim_edge/status.py#L69-L86).

The service binds loopback, which is a sound default. However, the deployment plan separately routes this port through a Cloudflare Tunnel and relies on an external Access policy:

- [Archived `RECLAIM_Remote_Gateway_Preflight.md`](Past_Deprecated/docs/retired-2026-08-24-convene-routing/RECLAIM_Remote_Gateway_Preflight.md#L42-L68).

**Impact:** A tunnel misconfiguration, local malicious process, or future binding change exposes process telemetry and control advice without defense in depth.

**Required remediation:** Add application authentication/authorization and least-privilege endpoint separation. Disable `/command` remote exposure entirely unless it is needed. Do not treat a tunnel hostname or external dashboard configuration as the only access control.

### GW-10 — Buffer overflow and audit retention are lossy without durable alarm semantics

**Severity:** P2 — reliability/audit gap; P1 if decisions rely on uninterrupted history.

The queue drops oldest records at its cap:

- [`buffer.py`](pi_gateway/reclaim_edge/buffer.py#L67-L76).

Drop count is process-memory only and resets on restart. Dead-letter retention is capped at 2,000 records and silently deletes older audit items:

- [`buffer.py`](pi_gateway/reclaim_edge/buffer.py#L26-L27), [`buffer.py`](pi_gateway/reclaim_edge/buffer.py#L92-L110).

**Impact:** An extended outage can erase the evidence needed to reconstruct data loss or verify a safety-relevant episode. The currently documented health metrics do not provide a persistent, alarmed loss watermark.

**Required remediation:** Persist loss/audit counters and first/last dropped timestamps; alarm locally and upstream on any data loss; retain an immutable/exportable audit record sized for the required retention period; enforce a disk-space budget; and define whether dropping safety telemetry must trigger a safe/degraded system state.

## Additional deployment observations

- The go/no-go document correctly marks the project **NO-GO for live data** and records absent cRIO/cloud/tokens/boot-task prerequisites. That status should remain until these red-team findings and the predictive-engine blockers are closed.
- The documented Windows task runs as `SYSTEM`. This amplifies configuration-file ACL, code-integrity, Python environment, and remote-management risks. The current checklist notes ACL hardening as pending; it should be a prerequisite, not a follow-up.
- Configuration accepts placeholders and an invalid cloud URL until delivery time. This is documented as a human gate, but it should be enforced by the loader for live mode.
- MQTT QoS 1 confirms broker receipt, not cloud application processing. Do not treat the MQTT transport as equivalent to the HTTPS per-frame ingest-ack protocol without an application-level acknowledgement and deduplication design.

## Release recommendation

### Permitted only with compensating controls

Telemetry-only, read-only shadow operation may proceed only on a dedicated isolated direct link, without the SYSTEM remote-command agent, with the command endpoint unused by the HMI/actuator, and with manual monitoring of queue depth, loss, and freshness.

### Not permitted

Do not connect the returned command to microwave-power or safe-state control until GW-01 through GW-08 are remediated and independently tested end-to-end.

### Minimum exit criteria for a live pilot

1. Separate the gateway from arbitrary remote-shell capability and apply OS code/configuration integrity controls.
2. Add a local fail-closed command governor with strict envelope validation, expiry, and actuator-side limits.
3. Authenticate and bound the cRIO ingress; test malformed, oversized, slow, and competing clients.
4. Require secure HTTPS configuration and strict per-frame response correlation before queue acknowledgement.
5. Implement outage-recovery behavior that intentionally prioritizes fresh state and signals degraded operation.
6. Validate the exact cRIO schema and safety-critical field/range checks before the first live ingest.
7. Exercise failure scenarios: network loss/recovery, cloud restart, malformed ingress, disk-full, queue cap, endpoint/proxy response corruption, local status exposure, and command expiry.

## Verification note

Python bytecode compilation for `pi_gateway` completed successfully. The gateway pytest suite was not rerun in this review session. Two direct checks were performed: a top-level JSON array raises an uncaught `AttributeError` in `Framer.build`, and an insecure live HTTPS configuration can be constructed.
