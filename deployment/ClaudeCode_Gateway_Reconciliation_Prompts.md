# Claude Code Prompt Pack — Edge Gateway Reconciliation

> **Stage:** 0.5 — Documentation reconciliation (Pi→laptop naming) · **Status:**
> HISTORICAL — one-off session prompt pack, already executed (GATEWAY_GO_LIVE §9.6).
> Kept as a record; not a current work plan.

Deliberate, sequenced prompts to feed **Claude Code** (running on the laptop, in
the repo root `C:\Users\latitude4\Downloads\RECLAIM_LiveTwin`) once SSH access is
up. Each prompt is scoped, ends with a **stop-and-show** guardrail, and does not
change runtime behavior without your review.

Run Claude Code from the repo root so it has the whole tree in context:

```powershell
cd C:\Users\latitude4\Downloads\RECLAIM_LiveTwin
claude
```

---

## Prompt 0 — Context priming (paste first, once per session)

> You are working in the RECLAIM Live Twin repo. Runtime topology:
> cRIO/LabVIEW → **Windows 10 laptop gateway** (`pi_gateway/`, despite the "pi"
> name) → authenticated HTTPS → cloud dual predictive engine (`cloud_engine/`) →
> one Convene publisher + the read-only Convene-native `.stp` visualization. Governing doctrine:
> **live-only** (`--production` accepts `mode: "live"` exclusively), **side-by-side**
> deployment, and **never overwrite a running stack in place**. Read `README.md`,
> `CODE_REVIEW.md`, `FIXES.md`, and `docs/RECLAIM_Live_Telemetry_Architecture.md`
> before proposing changes. Work in small steps: for each task, show me a plan and
> a diff and wait for my approval before writing files. Do not touch Convene
> bindings, the cRIO link, or the cloud engine's live behavior.

---

## Prompt 1 — Reconcile the "Pi vs Windows laptop" naming drift

> `CODE_REVIEW.md` (H6) flagged naming drift: the gateway is deployed as a
> **Windows 10 laptop**, but `README.md`, `FIXES.md`, and the architecture doc
> still describe a "Raspberry Pi 3B+", and the preflight file is named
> `RECLAIM_Remote_Gateway_Preflight.md`. Audit every doc and comment that names the
> gateway hardware and produce a single consistent story ("Windows laptop
> gateway"). **Documentation and comments only — do not change any runtime code
> path or the systemd/scheduled-task logic.** Show me a per-file diff and a short
> list of anything ambiguous before applying.

---

## Prompt 2 — Fix the test-environment gap and prove green

> Running `cloud_engine` tests fails on a missing `scipy`
> (`reclaim_predictive_engine/anomaly.py` imports `scipy.stats.chi2`), yet
> `scipy` is not in `cloud_engine/deploy/requirements-cloud.txt` or
> `reclaim_predictive_engine/requirements.txt`. Add the correct pinned `scipy`
> (and confirm `numpy` pin compatibility). Then create/activate a venv, install,
> and run both suites: `cd cloud_engine && python -m pytest tests -q` and
> `cd ../pi_gateway && $env:PYTHONPATH="."; python -m pytest tests -q`. Report the
> pass counts (expected ~18 cloud + 10 gateway) and paste any failures. Show the
> requirements diff before editing.

---

## Prompt 3 — Generate the real `config.windows.yaml`

> Create `C:\RECLAIM\pi_gateway\config.windows.yaml` from
> `pi_gateway/config.example.yaml` for this deployment. Use the values from the
> preflight §4.2 (isolated cRIO link `listen_host: 192.168.50.1`,
> `listen_port: 9070`, `transport: https`, `mode: live`, `run_id: ""`,
> `strict_fields: false`, `buffer_path: C:/ProgramData/RECLAIM/queue.db`,
> `status_port: 9080`). Leave `cloud_url` and `auth_token` as clearly-marked
> placeholders — I will supply the ingress host and the `RECLAIM_INGEST_TOKEN`.
> Explain each field in a comment. Confirm the loader's fail-fast rejects a
> missing/typo'd key. Show the file for approval; do not start any service.

---

## Prompt 4 — Manual shakedown (console transport, no cloud, no cRIO)

> Do a safe local shakedown of the gateway without a cRIO or the cloud. Prepare a
> copy of the config with `transport: console`, set
> `RECLAIM_EDGE_CONFIG` to it, and run `python -m reclaim_edge.main` for ~30s.
> Confirm: it starts without crashing, the status endpoints answer
> (`GET 127.0.0.1:9080/health`, `/latest`, `/command`), worker threads stay
> alive, and the "unknown field preserved" warning logs **once per field name**
> (fix M5), not per frame. Summarize the health JSON. Then stop it. Do not install
> the scheduled task yet.

---

## Prompt 5 — Validate the always-on task installer (dry review)

> Review `pi_gateway/windows/install-gateway-task.ps1` against this machine:
> confirm the `$GatewayDir`, venv python path, and `$ConfigPath` match where we
> actually put things in Prompt 3, and that the `RECLAIM-EdgeGateway` task would
> start at boot as SYSTEM, restart on failure, and not resurrect a clean stop.
> List any path mismatches and the exact corrected script. **Do not run it** — we
> install the boot task only when the real cRIO link and cloud ingress are ready.

---

## Prompt 6 — Reconciliation punch-list

> Produce `deployment/GATEWAY_RECONCILIATION.md`: a checklist of what is done vs
> outstanding to bring the edge gateway to the preflight's "ready" state —
> covering the naming reconciliation (P1), test env (P2), config (P3), shakedown
> (P4), task installer (P5), and the still-open items from `CODE_REVIEW.md`/the
> preflight (real cRIO manifest capture for `strict_fields`, cloud token/state
> file, contract gates §5, shadow-run V&V §6). Keep it a living go/no-go list.

---

## Usage notes

- Keep prompts **in order** — 2 must be green before the shakedown in 4 is
  meaningful; 3 feeds 5.
- If Claude Code proposes editing anything under `cloud_engine/` runtime paths or
  Convene bindings, stop it — that's outside this reconciliation and outside the
  live-only/side-by-side doctrine.
- Everything here is local prep. Nothing posts to the live cloud or the cRIO until
  the preflight §5 contract gates are explicitly run.
