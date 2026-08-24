# Convene Backend — Missing Firestore Composite Index (Handover)

> **For:** the Convene backend owner. **Not actionable from the RECLAIM side.**
> **Impact:** blocks Convene from displaying the RECLAIM rehearsal scenarios.
> Does **not** affect live raw gateway telemetry publishing.

---

## 1. The defect

Every agent heartbeat to `POST {backend}/api/machine/heartbeat` updates machine
presence and then returns **HTTP 500**. The response body carries the cause:

```
Error: 9 FAILED_PRECONDITION: The query requires an index.
```

The failing query is a Firestore `machineCommands` lookup that filters on
`machineId` and `status` and orders by `createdAt`. Firestore requires a composite
index for that combination and none exists.

Captured 2026-08-23 against machine `BcryPSMP2iLbSRns5uhm`. The desktop agent has
logged this **2622 consecutive times**; the log line is
Captured 2026-08-23 against machine `BcryPSMP2iLbSRns5uhm`. As of that date the
desktop agent had logged this **2841 consecutive times** — one per 30 s heartbeat,
and still accumulating for as long as the index is missing, so treat the figure as
a floor rather than a current total. The log line is
`[Heartbeat] HTTP 500; collectors were not returned`.

## 2. The fix — exact index required

Decoded from the `create_composite` payload in the error:

| Property | Value |
|---|---|
| Project | `reservationproject-f1d26` |
| Database | `(default)` |
| Collection group | `machineCommands` |
| Query scope | COLLECTION |

| Field | Order |
|---|---|
| `machineId` | ASCENDING |
| `status` | ASCENDING |
| `createdAt` | ASCENDING |
| `__name__` | ASCENDING |

**One-click creation URL** (from the Firestore error itself — this pre-fills the
exact index):

```
https://console.firebase.google.com/v1/r/project/reservationproject-f1d26/firestore/indexes?create_composite=CmBwcm9qZWN0cy9yZXNlcnZhdGlvbnByb2plY3QtZjFkMjYvZGF0YWJhc2VzLyhkZWZhdWx0KS9jb2xsZWN0aW9uR3JvdXBzL21hY2hpbmVDb21tYW5kcy9pbmRleGVzL18QARoNCgltYWNoaW5lSWQQARoKCgZzdGF0dXMQARoNCgljcmVhdGVkQXQQARoMCghfX25hbWVfXxAB
```

Equivalent declarative form for `firestore.indexes.json`:

```json
{
  "indexes": [
    {
      "collectionGroup": "machineCommands",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "machineId", "order": "ASCENDING" },
        { "fieldPath": "status",    "order": "ASCENDING" },
        { "fieldPath": "createdAt", "order": "ASCENDING" }
      ]
    }
  ]
}
```

Or via CLI:

```bash
gcloud firestore indexes composite create \
  --project=reservationproject-f1d26 \
  --collection-group=machineCommands \
  --query-scope=COLLECTION \
  --field-config=field-path=machineId,order=ascending \
  --field-config=field-path=status,order=ascending \
  --field-config=field-path=createdAt,order=ascending
```

`__name__` is appended implicitly; it does not need declaring.

## 3. Why it matters to RECLAIM

The heartbeat response is how the agent receives its **collector configs**, as
`autoVars`. Collectors are what tell the agent which endpoints to poll and push
back every beat. With the heartbeat 500-ing, no collectors are ever delivered, so
**the agent polls nothing**.

Consequence: **the RECLAIM rehearsal scenarios cannot appear in Convene at all.**
Those services are GET-only by design (`127.0.0.1:8177`–`8181`) and never push —
Convene is supposed to read them via collectors. No collectors, no rehearsal data.

**What is NOT affected:** live gateway telemetry. The raw gateway audit tap posts
directly to `/api/machine/publish` with the agent token and never touches the
heartbeat. Verified under sustained load on 2026-08-23: 450 frames, 270 delivered
plus 180 coalesced, **0 failed**. Machine presence also still works, because
presence is written *before* the query that fails — which is why Convene shows the
machine as connected while no variables arrive.

## 4. Verifying the fix

After the index finishes building (Firestore reports "Building" then "Enabled"):

1. `C:\Users\latitude4\.convene\agent.log` should stop emitting
   `[Heartbeat] HTTP 500; collectors were not returned` and resume normal beats.
2. A heartbeat should return **HTTP 200** with an `autoVars` array.
3. With a rehearsal scenario running, its variables should begin appearing under
   the labeled rehearsal identity (e.g. `reclaim-rehearsal-nominal`, prefix
   `rehearsal_nominal_`, source `127.0.0.1:8177`).

To re-capture the error on demand, one authenticated heartbeat is enough — the
agent already makes this exact call every 30 s, so an extra one changes nothing
operationally. Read the credential from
`C:\Windows\System32\config\systemprofile\.convene_agent.json`; **never** print or
paste the `agentToken`.

## 5. Secondary observations (RECLAIM-side, not blocking)

- **The agent discards the response body on failure.** `convene_agent.py:463`
  prints only the status code, which is why thousands of log lines contain no
  diagnostic detail and the index URL above went unseen for weeks. Logging the
  body on the *first* failure only would have surfaced this immediately.
- **`agent.log` grows unbounded** — 475 KB and climbing, one useless line every
  30 s. Worth rotating or truncating.

Both are in Convene's agent, not RECLAIM code, and are noted for whoever owns it.

---

**Standing status unchanged: labeled engineering shadow — NO-GO for any production
claim.** No command, return, or actuation path exists or is affected by this issue.
