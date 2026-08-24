# Windows VM Convene State Bridge — Implementation Handoff

> **Stage:** Convene VM publication infrastructure
> **Status:** APPROVED ARCHITECTURE / IMPLEMENTATION NOT STARTED
> **Platform:** cloud-hosted Windows Server 2025 VM, in Kubernetes-managed
> infrastructure, registered in Convene as `reclaim-engine-2`
> **Purpose:** publish the predictive engine's normalized `/state` record through
> this VM's independent Convene heartbeat.

## 1. Scope boundary

This handoff applies only to the Convene agent running on the Windows predictive-
engine VM. Other Convene agents run on separate devices and send their own
independent heartbeats. Their implementation, state, scheduling, credentials, and
variable-writing behavior are not inputs to this design and must not be reused,
modified, or treated as a shared runtime.

Kubernetes is the outer cloud hosting boundary. The guest is not a Linux host or
Linux container: operate it with PowerShell, Windows services, NTFS paths, and
ACLs as recorded in `DEPLOYMENT_TOPOLOGY.md`.

The VM agent installed during the clean-host bootstrap knows how to include the
JSON object stored at:

```text
C:\ConveneAgent\sim_vars.json
```

in its own heartbeat. It does **not** fetch the predictive engine's `/state`
endpoint. The missing component is a local, read-only state bridge that creates and
maintains that file.

The VM agent and bridge have separate responsibilities:

- the predictive engine owns normalized/predictive state;
- the state bridge validates that state and performs the atomic file handoff; and
- the VM Convene agent installed during bootstrap owns only its heartbeat transport to Convene.

## 2. Approved architecture

```text
External telemetry producer
                 |
                 | authenticated POST /ingest through Cloudflare Tunnel
                 v
Predictive engine on 127.0.0.1:8078
                 |
                 | authenticated GET /state
                 v
RECLAIM state bridge (independent Windows service)
                 |
                 | atomic same-volume replacement
                 v
C:\ConveneAgent\sim_vars.json
                 |
                 | read by installed VM agent
                 v
Convene heartbeat for machine reclaim-engine-2
```

The VM engine continues to receive authenticated `POST /ingest` traffic through
the Cloudflare Tunnel. That inbound telemetry route is required and is outside the
state bridge's responsibility.

The bridge itself talks to the engine over loopback and therefore does not need the
public Cloudflare route or ingest credential. Its only engine operation is
authenticated `GET /state`. It does not call `POST /ingest`, connect directly to a
telemetry producer, or reach a cRIO, PLC, LabVIEW process, HMI control, or actuator.

The engine's existing `/command` surface is preserved but deliberately not consumed
by this bridge. Command publication or consumption is deferred future scope requiring
a separate design, safety review, authorization model, expiry/freshness contract, and
hardware-authority gate.

## 3. Repository deliverables

Implement a focused package with a layout similar to:

```text
convene_bridge/
  __init__.py
  state_bridge.py
  config.py
  contract.py
  writer.py
  config.example.yaml
  windows/
    reclaim-state-bridge.xml
    install-state-bridge.ps1
    uninstall-state-bridge.ps1
  tests/
    test_contract.py
    test_writer.py
    test_bridge_integration.py
```

The precise module split may follow repository conventions, but keep engine HTTP
access, contract validation, liveness evaluation, and atomic writing independently
testable.

Also add operator documentation covering installation, configuration, health,
upgrade, and rollback. Do not copy the external Convene agent credential or any
live endpoint/token into the repository.

## 4. Bridge input contract

Default source:

```text
http://127.0.0.1:8078/state
```

The request uses the engine **read** credential as a bearer token. The credential
must come from an ACL-protected secret source and must never appear in source,
command-line arguments, process listings, logs, test fixtures, or output JSON.

For the demonstration deployment, an ACL-protected file under
`C:\ProgramData\RECLAIM\convene-bridge\` is acceptable. Windows Credential
Manager or DPAPI may be added later, but production-grade secret infrastructure is
not required for this event.

A response is eligible for publication as live only when all of the following are
true:

- HTTP status is 200;
- the response is a JSON object;
- `schema_version == "reclaim.state.v1"`;
- `mode == "live"`;
- `ingest_status == "accepted"`;
- `state_age_ms` is a non-negative integer no greater than the configured limit;
- required identity fields have valid scalar types; and
- sequence has not regressed for the same `(run_id, source_id)` identity.

A new `run_id` is a normal gateway/run-supersession event, not automatically an
error. Reset the bridge's sequence comparison when the run/source identity changes,
log the transition without secrets, and continue if the new record is otherwise
valid.

Required identity fields:

```text
run_id
source_id
cycle_id
seq
ts_source
ts_engine
active_chamber
source_op_state
op_state
```

The bridge must preserve scalar `/state` values without silently converting numeric,
boolean, string, or null semantics.

## 5. Output contract

The bridge enriches the engine record with VM-publication metadata:

```text
data_live              boolean
bridge_status          ok | starting | engine_unavailable | unauthorized |
                       invalid_json | schema_mismatch | stale |
                       identity_invalid | sequence_regression | write_failed
bridge_observed_at     UTC ISO-8601 timestamp
bridge_error_code      stable non-secret code or NONE
bridge_instance_id     configured non-secret VM bridge identity
environment            configured engine environment, initially earth_lab
engine_source_sha      exact deployed engine revision
freshness_limit_ms     configured threshold, initially 15000
```

`data_live` is the single fail-closed predicate delivered to Convene. It is true
only when the complete input contract passes. The Convene view must still evaluate
the underlying `mode`, `ingest_status`, and `state_age_ms`; `data_live` is an
additional explicit guard, not a replacement for source evidence.

On startup or any read/validation failure, write a current heartbeat payload with
`data_live=false`, a stable `bridge_status`, and a fresh `bridge_observed_at`.
Last-known measurements may remain for diagnosis, but must never be presented as
live. Do not fabricate replacement process values.

The engine does not currently publish its configured environment or deployment SHA,
so these are static, reviewed bridge configuration values.

## 6. Prefix policy

The installed VM agent sends the object from `sim_vars.json` as `simVars`. Whether
Convene prefixes those keys automatically must be proven against the registered
`reclaim-engine-2` machine before final binding.

Support a configuration option with two explicit modes:

```text
prefix_mode: passthrough
prefix_mode: sim
```

- `passthrough` writes engine keys unchanged;
- `sim` writes them with one `sim_` prefix; and
- the bridge must reject unknown modes and must never double-prefix an existing
  `sim_` key.

Default to `passthrough` until a harmless canary field proves the Convene behavior.
Only one prefix mode may be active for a run.

## 7. Atomic file and single-writer requirements

The bridge is the sole writer of `C:\ConveneAgent\sim_vars.json` on this VM.

For every update:

1. serialize a complete JSON object;
2. write it to a temporary file in `C:\ConveneAgent`;
3. flush and close the temporary file;
4. replace `sim_vars.json` atomically with `os.replace`; and
5. on a Windows sharing violation, retry for a short bounded interval while leaving
   the last complete file intact.

Never truncate or edit the destination in place. Prevent two bridge instances from
running simultaneously with a Windows-compatible singleton lock. The installer must
apply explicit ACLs so only the bridge service identity, `SYSTEM`, and administrators
can write the file or read bridge secrets.

## 8. Configuration

Use a non-secret YAML or JSON configuration plus a separate secret source. Suggested
settings:

```yaml
engine_state_url: http://127.0.0.1:8078/state
poll_interval_s: 1.0
request_timeout_s: 3.0
freshness_limit_ms: 15000
publisher_heartbeat_ms: 30000
lease_duration_ms: 45000
output_path: C:\ConveneAgent\sim_vars.json
prefix_mode: passthrough
environment: earth_lab
engine_source_sha: REPLACE_WITH_FULL_SHA
bridge_instance_id: reclaim-engine-2-state-bridge
```

Validate configuration before entering the polling loop. Refuse non-loopback source
URLs by default; require an explicit reviewed override for any remote source. Refuse
placeholder deployment SHAs and missing read credentials in live mode.

## 9. Windows supervision and filesystem layout

Run the bridge independently from both the predictive engine and the existing
Convene agent. Preferred supervision is a WinSW-managed Windows service with a
dedicated, non-interactive, least-privilege account.

Suggested layout:

```text
C:\ProgramData\RECLAIM\convene-bridge\
  config\bridge.yaml
  secrets\bridge.env
  state\
  logs\
```

The WinSW executable is an external prerequisite; do not commit an unreviewed binary.
The installer must discover existing services/files first, preserve unexpected
deployments, and install side-by-side or stop for operator direction. It must not
modify, replace, or unregister the installed VM Convene agent task.

The uninstall/rollback script removes or disables only the bridge service created by
this package. It must preserve `sim_vars.json` unless the operator explicitly chooses
to archive it.

## 10. Observability

Produce rotating, secret-free logs containing:

- service start and exact bridge/engine source revisions;
- configuration paths, never secret contents;
- last successful poll time;
- last published `(run_id, source_id, seq)`;
- identity transitions;
- consecutive failure count;
- validation/freshness failure code; and
- atomic-write failures.

Also maintain a local bridge health record or loopback-only health endpoint with the
same non-secret status. Errors must not be silently swallowed.

## 11. Required tests

Automated tests must cover:

- a valid `reclaim.state.v1` response;
- unauthorized response;
- timeout/connection refusal;
- malformed JSON and non-object JSON;
- wrong or missing schema;
- wrong identity-field types;
- `state_age_ms` at, below, and above 15000 ms;
- mode/status failures;
- sequence monotonicity within one run/source;
- valid sequence reset on a new run/source identity;
- passthrough and `sim` prefix modes, including double-prefix rejection;
- atomic replacement while a reader polls repeatedly;
- bounded retry on a simulated Windows sharing violation;
- singleton writer behavior;
- startup and every failure state publishing `data_live=false`;
- recovery from failure to live and live to failure; and
- proof that the bridge client performs only authenticated `GET /state` and has no
  command, ingest-write, or hardware-control call.

Use a fake loopback HTTP server for integration tests. Tests must not contact the
real engine, Convene backend, VM, tunnel, or any external service.

## 12. VM acceptance sequence

Do not install on the VM until repository review and tests pass.

1. Rotate the VM Convene agent credential that appeared in the supplied installer.
2. Discover existing `C:\ConveneAgent`, services, tasks, ACLs, and files without
   changing them.
3. Confirm the engine is healthy on loopback and `/state` requires the read token.
4. Install the bridge side-by-side under `C:\ProgramData\RECLAIM`.
5. Start with `data_live=false` and a canary field to prove prefix behavior.
6. Select and record the correct prefix mode.
7. Run a valid synthetic nominal feed and verify expected variables in Convene.
8. Stop telemetry and prove `data_live=false` within 15 seconds and `DATA NOT LIVE`
   in the view.
9. Exercise invalid auth, malformed state, engine restart, and bridge restart.
10. Confirm the installed VM Convene agent still owns its heartbeat and no other
    device or heartbeat was altered.

## 13. Stop conditions

Stop rather than improvising if:

- the source is not loopback or resolves unexpectedly;
- `/state` is unauthenticated in the intended live configuration;
- the schema or prefix behavior is ambiguous;
- more than one process writes `sim_vars.json`;
- the file remains apparently live after the engine becomes stale;
- an installer would overwrite an unexpected existing service/task/file;
- a secret would appear in source, logs, process arguments, or heartbeat data; or
- the bridge attempts to consume `/command`, write `/ingest`, connect directly to a
  telemetry producer, or reach cRIO, LabVIEW, HMI control, PLC, or an actuator.

## 14. Definition of done

- The bridge is repository-owned, tested, and deployable as an independent Windows
  service.
- It reads only authenticated loopback `/state`.
- `sim_vars.json` is always complete JSON and has exactly one writer.
- Convene receives the required predictive variables under the proven prefix policy.
- Source, environment, run, sequence, freshness, process state, model trust, and
  advisory state are visible.
- Stale, unavailable, mismatched, or invalid data always yields `data_live=false`.
- No other Convene machine or heartbeat is changed.
- The engine's existing ingest route remains operational through Cloudflare.
- The bridge introduces no command or hardware-control authority; `/command`
  integration remains separately gated future scope.

## 15. Implementation decision: downstream-enforced publication lease

The repository implementation adds `bridge_valid_until` to every publication.
Convene must compare its own current UTC clock to this deadline as part of the
effective live-data predicate. Fail-closed payloads expire immediately. The
installed publisher heartbeats every 30 seconds, so successful live payloads
use a 45-second lease; a shorter lease could expire healthy data before the next
publisher read. The bridge still fails closed on the independent
`freshness_limit_ms: 15000` engine-state threshold. The 45-second lease does not
make state older than 15 seconds live.

This resolves the Windows sharing-violation edge case: if `os.replace` ultimately
cannot replace a previously live file, the last complete destination remains intact
but becomes non-live when its independently evaluated lease expires. The installed VM
Convene agent remains unchanged. Acceptance must prove the lease expires in the
Convene view; without that proof, fail-closed acceptance is not complete.
