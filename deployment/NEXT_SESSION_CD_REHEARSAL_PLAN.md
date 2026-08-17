# RECLAIM Live Twin — 2026-08-17 CD Rehearsal Plan

> **Session objective:** establish a trustworthy three-host operating model and
> practice repeatable, reversible delivery to the VM and Windows gateway without
> activating live telemetry, hardware, tunnels, Convene namespaces, or command
> authority.
>
> **Starting status:** CI is implemented and the exact local branch commit is
> green from the last recorded GitHub run. CD is not production-ready. The VM is
> not a verified deployment target, the Windows gateway contains a manually
> staged baseline, and the new connector control paths have not yet been recorded
> as deployment trust boundaries.

## 1. Outcome for the morning

By lunch, produce five pieces of evidence:

1. A connector trust matrix for the MacBook, VM, and Windows gateway.
2. A read-only inventory of the VM's actual runtime layout.
3. A hashed, non-secret inventory of the code already staged on the gateway.
4. One agreed release-root and rollback convention for each target.
5. A written GO/NO-GO decision for an **install-only rehearsal** on each target.

The stretch outcome is to place the exact candidate side-by-side on one or both
targets and prove it starts on loopback with disposable state. It is not a goal
to switch a live service, install the gateway boot task, connect the cRIO, create
a tunnel, change firewall rules, publish to Convene, or merge the draft PR.

## 2. Fixed source and current caveats

Use this identity until deliberately superseded:

| Item | Starting value |
|---|---|
| Branch | `agent/rt03-rt05-convene-integrity` |
| Commit | `7a0a94166018762a81de6fb9dc329c189bc067d4` |
| Draft PR | `#1` |
| Last recorded CI | all required Python 3.11/3.13 and integrity checks green |
| Authority | `advisory` only |
| Live deployment | NO-GO |

The GitHub CLI credential was invalid when this plan was written. Repair and
verify authentication before relying on current PR or Actions state. The local
candidate manifest under `artifacts/` is also stale: it names source commit
`374c079...`, not the commit above. Do not put that artifact on either endpoint.

## 3. Operating model

The MacBook is the release-control workstation. The connector is transport for
an identified human operator; it is not a CI runner and does not confer release
approval.

```text
GitHub-hosted CI (no production credentials)
                  |
                  v
        exact candidate + digest
                  |
                  v
MacBook release-control workstation
          |                    |
          | connector session  | connector session
          v                    v
 VM fixed rehearsal       Windows fixed rehearsal
 command surface          command surface
```

Preferred control direction is MacBook-initiated access to each endpoint. If
either endpoint can initiate arbitrary remote commands on the MacBook, pause and
record why that direction is needed, which identity can use it, its privilege,
audit trail, and revocation mechanism. Do not use the SYSTEM-level Convene agent
as a general deployment runner.

## 4. Roles and control rules

One person may hold several roles, but say the role aloud before each gate:

| Role | Responsibility |
|---|---|
| Release conductor | Owns commit/digest, checklist, and final stop/go decision |
| Endpoint operator | Runs only the displayed command on the named host |
| Safety witness | Confirms no live plant, tunnel, namespace, or active authority is touched |
| Evidence recorder | Captures redacted output, timestamps, and deviations |

Rules for the whole session:

- One host and one named session at a time.
- Display `hostname` and current identity before every endpoint command block.
- Never paste or record token values, credential files, or environment contents.
- No generic remote shell may be handed to GitHub Actions.
- No in-place edits under an existing runtime directory.
- No service/task switch without a separately announced activation checkpoint.
- Any unexpected running writer or non-empty queue stops the rehearsal.

## 5. Time-boxed run sheet

### 08:00–08:20 — Freeze the source and restore observability

On the MacBook:

```bash
git status --short --branch
git rev-parse HEAD
gh auth login -h github.com
gh auth status
gh pr view 1 --json isDraft,headRefOid,mergeStateStatus,statusCheckRollup,url
```

Gate A passes only when:

- the worktree is understood and unrelated changes are preserved;
- PR head equals the intended commit;
- current required checks are visible and green; and
- the PR remains draft unless a separate review decides otherwise.

If authentication cannot be restored, continue with endpoint inventory but do
not create, download, approve, or deploy a candidate.

### 08:20–08:50 — Inventory the connector trust boundary

Fill one row for every permitted direction, including the new remote-control
paths:

| From | To | Initiator | Account | Effective privilege | Command scope | Audit location | Revoke method | Accepted? |
|---|---|---|---|---|---|---|---|---|
| MacBook | VM |  |  |  |  |  |  |  |
| MacBook | gateway |  |  |  |  |  |  |  |
| VM | MacBook |  |  |  |  |  |  |  |
| gateway | MacBook |  |  |  |  |  |  |  |
| Convene | gateway | outbound poll | Convene identity | SYSTEM | arbitrary shell today | agent/backend logs | account/task disable | unresolved |

For each path, perform only a harmless identity probe: hostname, OS, current
user, and timestamp. Confirm whether the operator must approve each session and
whether stdout/stderr are retained. Do not test privilege escalation.

Gate B fails if a path has unknown identity, silent/unbounded command execution,
no useful audit record, no revocation method, or endpoint-to-MacBook control that
cannot be justified. Restrict or disable that path before using the connector for
delivery.

### 08:50–09:25 — Read-only VM inventory

Record without exposing secrets:

- hostname, OS, Python version, disk space, and clock synchronization;
- whether `reclaim-ingest` or `cloudflared` exists or is running;
- service user, unit file, `ExecStart`, `WorkingDirectory`, and environment-file
  **path only**;
- listening address/port and process owner;
- existing release directories and the resolved `current` path, if present;
- persistent-state path, owner, mode, size, and schema/backup policy—never its
  contents;
- the exact code/version currently executing, if anything is running.

Proposed VM convention:

```text
/opt/reclaim/releases/<release-id>/   immutable code + release-local venv
/opt/reclaim/current                  atomic link to selected release
/etc/reclaim/                         configuration and secret references
/var/lib/reclaim-ingest/              persistent state
/var/log/reclaim/                     receipts and service logs
```

Do not create these paths during inventory. First reconcile the proposed layout
with the actual unit and filesystem.

### 09:25–10:05 — Preserve the Windows gateway baseline

Treat `C:\RECLAIM\pi_gateway` as a **legacy staged baseline**, not as a release
that CI can reproduce and not necessarily as a known-good production rollback.
Capture:

- hostname, Windows build, current user/privilege, Python 3.13 path and packages;
- a sorted SHA-256 inventory of source, scripts, and dependency declarations;
- config file path, ACL, and whether placeholders remain—do not display values;
- queue file path, schema/version if available, file size, and item counts—do not
  copy operational contents into Git;
- scheduled-task definitions and resolved executables for `Convene-Agent` and
  `RECLAIM-EdgeGateway` if present;
- listeners/process owners for 9070 and 9080;
- Convene agent owner, boot persistence, last heartbeat, log growth, and the
  account set allowed to issue commands;
- whether any gateway publisher or cRIO receiver is currently active.

Proposed Windows convention:

```text
C:\RECLAIM\releases\<release-id>\     immutable code + release-local venv
C:\RECLAIM\current\                   junction to selected release
C:\ProgramData\RECLAIM\config\        protected configuration
C:\ProgramData\RECLAIM\state\         queue and durable state
C:\ProgramData\RECLAIM\receipts\      non-secret deployment receipts
```

Do not overwrite, rename, delete, or `git pull` inside
`C:\RECLAIM\pi_gateway`. After hashing, label it with the capture date and leave
it untouched. A future migration can copy approved configuration and state by an
explicit compatibility procedure; code is deployed into a new release directory.

### 10:05–10:30 — Reconcile and make the first decision

Compare actual state to the proposed conventions. Write down:

- the selected release roots and runtime pointers;
- which existing unit/task files must eventually change to use `current`;
- state and queue schema compatibility requirements;
- what constitutes the previous rollback target on each host;
- connector risks that must be closed;
- whether the gateway baseline is only a forensic reference or can pass the
  console tests needed to become a rehearsal rollback candidate.

Decision 1 has only three valid results per endpoint:

| Result | Meaning |
|---|---|
| NO-GO | Inventory/trust/safety is incomplete; make no endpoint changes |
| GO: install only | Candidate may be placed in a new directory; nothing points to it |
| GO: isolated run | Install-only passed; candidate may run on loopback with disposable state and no external route |

There is no live-activation option in this session plan.

### 10:30–11:15 — Rebuild proof for the exact source

Only after Gate A passes, rerun the required local verification at the fixed
commit. Build a fresh candidate from that same tree. Confirm its manifest says:

- the exact source commit;
- `signed: false`;
- `production_promotable: false`;
- `authority: advisory`;
- unresolved signing, installer, and compatibility blockers.

The unsigned artifact is acceptable only for a controlled install/run rehearsal.
It cannot be called a production release. Record its SHA-256 digest before any
transfer and verify that digest again on the endpoint.

### 11:15–12:00 — Endpoint install-only rehearsal

For each endpoint separately, and only with `GO: install only`:

1. Transfer the exact candidate through the approved connector path.
2. Verify the recorded SHA-256 before extraction.
3. Extract into a new release directory named with the full commit or unique
   rehearsal ID.
4. Refuse extraction if the directory already exists.
5. Create a release-local environment without reading production secrets.
6. Run imports and offline tests from the extracted artifact.
7. Record resolved Python and entrypoint paths.
8. Write a non-secret receipt; do not create or switch `current`.

Minimum receipt fields:

```text
timestamp, operator, machine identity, connector/session identity,
source commit, artifact digest, manifest digest, release directory,
Python executable/version, checks performed, result, previous target,
activation attempted=false, rollback attempted=false
```

### Optional after lunch — Isolated start and rollback mechanics

Proceed only after reviewing the morning evidence and explicitly announcing
`GO: isolated run` for one endpoint.

- Use console/rehearsal configuration and disposable state.
- Bind loopback only on an unused rehearsal port.
- Do not start `cloudflared`, accept a cRIO connection, use production tokens,
  install a boot task, or bind `sim_`/`gw_`/live Convene fields.
- Verify health, manifest, state/history contract, process path, authority, and
  shutdown behavior.
- Stop the candidate and prove the prior endpoint state is unchanged.

Only after fixed install/switch/health/receipt/rollback scripts exist should a
later session practice switching `current` in an isolated service or task. A
manual collection of remote shell commands is not yet CD.

## 6. Immediate stop conditions

Stop the affected endpoint at once if any of these is true:

- connector direction, identity, privilege, audit, or revocation is unknown;
- a credential/token value appears in captured output;
- the endpoint is connected to an active chamber, cRIO, live tunnel, or live
  Convene namespace;
- active chamber is not `NONE`, independent power-safe state is unverified, or a
  gateway queue is non-empty/unknown;
- an unexpected publisher, engine, agent, scheduled task, listener, or writer is
  running;
- artifact or source digest differs from the recorded value;
- extraction would overwrite an existing directory;
- persistent state/queue compatibility is unknown for a proposed switch;
- no proven prior target and rollback procedure exist;
- command authority is anything other than `advisory`.

## 7. What we deliberately are not building tomorrow

The CI work is not unnecessary complexity. It gives one exact commit a repeatable
test record and catches cross-version regressions before either lab endpoint is
touched. The unnecessary complexity would be pretending the connector plus a
collection of privileged shell commands is already production CD.

Keep tomorrow's architecture deliberately small:

1. GitHub-hosted CI validates source without endpoint credentials.
2. A digest-bound, explicitly non-promotable candidate supports rehearsal.
3. A human uses the connector to invoke narrowly reviewed endpoint steps.
4. Each step produces a receipt and leaves the old installation intact.

Defer signing/provenance, unattended pull agents, protected production
environments, live state migration, automatic activation, and Convene/hardware
cutover until the manual rehearsal exposes the real endpoint constraints.

## 8. Definition of done

The session is complete when:

- the connector matrix is filled and risky reverse-control paths are resolved;
- GitHub/commit/check identity is recorded, or inability to verify it is a
  documented blocker;
- both endpoint inventories exist with no secrets captured;
- the gateway's existing code has a hash baseline and remains untouched;
- release-root, config/state, receipt, and rollback conventions are agreed;
- each endpoint has an explicit NO-GO, install-only GO, or isolated-run GO;
- any candidate used matches the intended commit and is labeled unsigned,
  non-promotable, and advisory;
- no live service, task, hardware, tunnel, firewall, token, Convene namespace, or
  command authority was changed.

The next implementation slice should then be chosen from evidence: either close
connector/security gaps, implement the fixed VM installer and receipt, implement
the fixed Windows installer and receipt, or formalize state/queue compatibility.
Do not start all three at once.
