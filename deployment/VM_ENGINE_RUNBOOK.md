# RECLAIM Cloud Engine — VM Deployment Runbook (quick-tunnel)

> **Stage:** 1 — Cloud engine on VM + egress tunnel · **Status:** CURRENT (active).
> Executable companion to `VM_ENGINE_SESSION_BRIEF.md`.

**Written:** 2026-08-15 · **Scope:** stand up the dual predictive engine
(`push_ingest_dual.py --production`) on the Convene VM, behind a **cloudflared
quick tunnel**, with tokens, then hand the ingress hostname + ingest token back
to finalize the laptop gateway. Companion to `deployment/VM_ENGINE_SESSION_BRIEF.md`
and `deployment/GATEWAY_GO_LIVE.md`. Cross-refs (§n) are to
`docs/RECLAIM_Remote_Gateway_Preflight.md`.

**Guardrails (verbatim):** engine binds **loopback only** — cloudflared is the
only path in. `--production` accepts `mode: "live"` **only**. Tokens come from
the `EnvironmentFile` **only** — never on a command line (visible in `ps`/`/proc`)
and never committed. Deploy to a **fresh dir**; never overwrite a running stack
in place.

Assumptions: a Linux VM (systemd), sudo, outbound Internet. Adjust `User=`,
paths, and Python as noted. This runbook is **prep-only** — commands are ready to
run on the VM when you have a session there; nothing here touches the live laptop.

---

## 0. Pre-flight on the VM (5 min)

```bash
# Confirm interpreter and that it's a supported one. Gateway staged on 3.13;
# pick a 3.10–3.13 python on the VM and record which (open decision §9.2).
python3 --version
which python3

# systemd + curl present?
systemctl --version | head -1
curl --version | head -1
```

Record the exact `python3` version you use here — it closes GO-LIVE §9.2 for the
cloud half.

---

## 1. Deploy the engine to a fresh dir

```bash
sudo install -d -o "$USER" -g "$USER" /opt/reclaim/engine
# Copy the cloud_engine tree to the VM. From your transfer method of choice, land:
#   /opt/reclaim/engine/push_ingest_dual.py
#   /opt/reclaim/engine/labview_map.py
#   /opt/reclaim/engine/reclaim_predictive_engine/   (whole package)
#   /opt/reclaim/engine/deploy/                       (requirements + unit + env example)
# Do NOT copy __pycache__ or .pytest_cache.

cd /opt/reclaim/engine
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r deploy/requirements-cloud.txt
```

`requirements-cloud.txt` in this snapshot already pins `numpy>=1.24`,
`scipy>=1.10`, `scikit-learn>=1.3`. **The old "scipy missing" gap noted in the
session brief is already closed** — the brief text is stale; the file is correct.

---

## 2. Dependency + import verification (do this before installing the service)

The single most likely failure is a numpy/scipy ABI mismatch on the VM's Python.
Prove the imports *before* systemd hides the traceback.

```bash
cd /opt/reclaim/engine && . .venv/bin/activate

# 2a. Versions actually resolved
pip show numpy scipy scikit-learn | grep -E '^(Name|Version)'

# 2b. The exact import that used to be the gap: scipy.stats.chi2 via anomaly.py
python - <<'PY'
import numpy, scipy, sklearn
from scipy.stats import chi2
print("numpy", numpy.__version__, "| scipy", scipy.__version__, "| sklearn", sklearn.__version__)
print("chi2.ppf(0.95, 3) =", float(chi2.ppf(0.95, 3)))  # exercises anomaly.py's call
import reclaim_predictive_engine.anomaly  # full module import
import push_ingest_dual                    # the service module itself imports clean
print("imports OK")
PY
```

Expected: version line prints, a finite chi2 value, then `imports OK`. If numpy
throws an ABI/`_core` error, reinstall matched wheels
(`pip install --force-reinstall --no-cache-dir numpy scipy`) and re-run.

---

## 3. Secrets first (mode-600 EnvironmentFile) — §3

```bash
sudo install -d -m 700 /etc/reclaim
sudo sh -c 'umask 077; cp /opt/reclaim/engine/deploy/reclaim-ingest.env.example /etc/reclaim/reclaim-ingest.env'

# Generate two DISTINCT long random secrets
INGEST=$(openssl rand -hex 32); READ=$(openssl rand -hex 32)
sudo tee /etc/reclaim/reclaim-ingest.env >/dev/null <<EOF
RECLAIM_INGEST_TOKEN=$INGEST
RECLAIM_READ_TOKEN=$READ
EOF
sudo chown root:root /etc/reclaim/reclaim-ingest.env
sudo chmod 600 /etc/reclaim/reclaim-ingest.env
unset INGEST READ   # keep them out of shell history/env
```

- `RECLAIM_INGEST_TOKEN` → bearer for `POST /ingest`; **this same value** becomes
  the gateway's `auth_token` in §6.
- `RECLAIM_READ_TOKEN` → **distinct** bearer for `GET /state /manifest /history
  /command` (Convene publisher + its native `.stp` visualization). `/health` stays open for probes.

Retrieve the ingest token later, without echoing it into history:
`sudo sed -n 's/^RECLAIM_INGEST_TOKEN=//p' /etc/reclaim/reclaim-ingest.env`

---

## 4. Install the systemd unit

The supplied `deploy/reclaim-ingest.service` is already correct for the
`/opt/reclaim/engine` + `User=reclaim` layout: it binds `--host 127.0.0.1 --port
8078 --production --max-frame-age-s 15`, sets `EnvironmentFile=` (required, no
leading `-`), `StateDirectory=reclaim-ingest`, and
`RECLAIM_INGEST_STATE=/var/lib/reclaim-ingest/ingest_state.json` (fix C4, so a
restart can't double-step). Only edit if your VM differs:

- If your service account isn't `reclaim`, change `User=reclaim`.
- If the venv/workdir isn't `/opt/reclaim/engine/.venv`, fix `WorkingDirectory=`
  and the `ExecStart=` python path.

```bash
sudo cp /opt/reclaim/engine/deploy/reclaim-ingest.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now reclaim-ingest
sudo systemctl status reclaim-ingest --no-pager
journalctl -u reclaim-ingest -n 30 --no-pager
```

Sanity — the two `--production` guards must be *satisfied*, not tripped: the
process refuses to start without `RECLAIM_INGEST_TOKEN` **and**
`RECLAIM_INGEST_STATE`. A clean start proves both are wired.

```bash
# Loopback only — must show 127.0.0.1:8078, never 0.0.0.0
ss -ltnp | grep 8078
# Local liveness (no token)
curl -s http://127.0.0.1:8078/health
```

---

## 5. Cloudflared quick tunnel (egress) — §3

Quick tunnel = no domain, no account config. **Caveats to plan around:** the
`trycloudflare.com` hostname is **ephemeral (changes every restart)** and has
**no Cloudflare Access policy**. Fine for first bring-up; move to a named tunnel
+ domain once interop matters (see §8).

```bash
# Install cloudflared if absent (Debian/Ubuntu example)
curl -L -o /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i /tmp/cloudflared.deb

# Foreground first, to read the assigned hostname:
cloudflared tunnel --url http://127.0.0.1:8078
# -> note the printed https://<random>.trycloudflare.com  (this is your ingress host)
```

To keep it up across logout, run it as a second unit (edit the URL only):

```bash
sudo tee /etc/systemd/system/reclaim-tunnel.service >/dev/null <<'EOF'
[Unit]
Description=RECLAIM cloudflared quick tunnel -> 127.0.0.1:8078
After=network-online.target reclaim-ingest.service
Wants=network-online.target
[Service]
ExecStart=/usr/bin/cloudflared tunnel --url http://127.0.0.1:8078 --no-autoupdate
Restart=on-failure
RestartSec=3
User=reclaim
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload && sudo systemctl enable --now reclaim-tunnel
# Read the hostname from the tunnel log after start:
journalctl -u reclaim-tunnel -n 40 --no-pager | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com'
```

Because the hostname changes on every tunnel restart, treat it as a value you
re-fetch and re-hand to the gateway each time until you move to a named tunnel.

---

## 6. Verify end-to-end, then hand back to the gateway

Set `HOST` to the printed hostname and pull the read token locally on the VM:

```bash
HOST=https://<random>.trycloudflare.com
READ=$(sudo sed -n 's/^RECLAIM_READ_TOKEN=//p' /etc/reclaim/reclaim-ingest.env)

curl -s "$HOST/health"                                        # open, expect JSON liveness
curl -s -H "Authorization: Bearer $READ" "$HOST/state"        # read-token gated
# From the LAPTOP too (records round-trip; GATEWAY_GO_LIVE §3):
#   curl -w '\n%{time_total}s\n' https://<host>/health
```

Hand back to the gateway (closes the egress loop — GO-LIVE §3):

1. **Ingress hostname** → set `cloud_url: https://<host>/ingest` in
   `C:\RECLAIM\pi_gateway\config.windows.yaml`.
2. **`RECLAIM_INGEST_TOKEN`** (the ingest value, not the read value) → `auth_token`
   (same string).
3. **ACL-lock** that config — it now holds the token in cleartext: break
   inheritance, grant SYSTEM + Administrators only.

Reminder: those placeholders don't block startup (`config.py:131` only checks
`auth_token` non-empty; `cloud_url` isn't validated). Replacing them is a **human
gate** — verify by eye.

---

## 7. What becomes runnable next (still gated, still ordered)

Only after **ingress** (§2 cRIO IPs) *and* this **egress** are both real:
install the gateway boot task, then run the **six §5 contract gates**
(fresh / duplicate / harness-reject / stale / gateway-restart / cloud-restart +
freshness decay), then the **§6 three-column V&V** with the `gw_` audit machine.
The harness-reject gate is the live-only proof: `--production` rejects
`mode: harness`. See `GATEWAY_GO_LIVE.md` §5–§7.

---

## 8. Upgrade path — named tunnel + domain (when interop matters)

Replaces the ephemeral hostname with a stable `cloud_url` and lets you put a
Cloudflare Access policy in front of `/ingest` and the GET routes:

```
cloudflared tunnel login
cloudflared tunnel create reclaim-engine
cloudflared tunnel route dns reclaim-engine engine.<your-domain>
# config.yml: ingress rule -> service http://127.0.0.1:8078 ; run as a service
# then add a self-hosted Access app over engine.<your-domain>
```

Record the decision wherever GO-LIVE §9.1's access model is finalized.

---

## 9. Open items this session should also close or record

- **§9.2** Confirm the VM's Python (from §0) as supported, or pin one.
- **§9.3** Graceful stop: the engine catches `KeyboardInterrupt` → `server.shutdown()`.
  Confirm `systemctl stop reclaim-ingest` exits cleanly (no `on-failure` restart).
- **§9.5** After first real frames flow, diff `/state` `vars` keys against
  `CONVENE_GW_MAPPING.md` before considering `strict_fields: true`.
- **§9.9** Record team acceptance of the SYSTEM-level Convene remote-shell posture
  on the gateway; decide who may issue commands.
- Quick-tunnel has **no Access policy** — until §8, the ingest bearer token is the
  only thing protecting `POST /ingest`. Don't advertise the hostname.

---

## Quick reference

| Item | Value |
|---|---|
| Engine dir | `/opt/reclaim/engine` |
| Bind | `127.0.0.1:8078` (loopback only) |
| Service | `reclaim-ingest.service` (`--production --max-frame-age-s 15`) |
| Secrets | `/etc/reclaim/reclaim-ingest.env` (mode 600 root:root) |
| State | `/var/lib/reclaim-ingest/ingest_state.json` |
| Tunnel | `cloudflared tunnel --url http://127.0.0.1:8078` (quick) |
| Open routes | `/health` (open) · `/state /manifest /history /command` (read token) · `/ingest` (ingest token, POST) |
| Hand back | `cloud_url=https://<host>/ingest`, `auth_token=<RECLAIM_INGEST_TOKEN>`, then ACL-lock |
