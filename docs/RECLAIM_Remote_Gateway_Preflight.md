# RECLAIM MacBook scenario host preflight

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

**Deployment:** Windows 10 desktop at the cRIO/live boundary; MacBook excluded
**Cloud endpoint:** Windows Server 2025 predictive-engine VM
**Status:** required before competition cutover

## 1. Freeze and identify

Record the following without exposing secrets:

```bash
sw_vers
uname -m
python3 --version
python3.12 --version
git status --short
git rev-parse HEAD
system_profiler SPHardwareDataType
```

Use one approved Git SHA. Preserve untracked captures and diagnostic tools; do
not clean or overwrite the working tree to manufacture a clean status.

## 2. Network discovery

```bash
networksetup -listallhardwareports
ifconfig
route -n get default
networksetup -getinfo "Wi-Fi"
lsof -nP -iTCP:9070 -sTCP:LISTEN
lsof -nP -iTCP:9080 -sTCP:LISTEN
```

Record:

- cRIO-facing interface and MAC address;
- reserved/static Windows 10 gateway OT address;
- real cRIO source address;
- subnet mask and direct-link/switch topology;
- WAN/Wi-Fi default route;
- current owners of ports `9070` and `9080`.

The 2026-08-23 bench observations were MacBook `192.168.12.33` on active `en0`
and emulated endpoint `192.168.12.114`. They do not prove an isolated OT link.
The OT interface must not install a default route.

## 3. Firewall and exposure

Required policy:

- permit inbound TCP `9070` only from `<CRIO_SOURCE_IP>` on the OT interface;
- deny other inbound access to `9070`;
- do not create any inbound rule for `9080`;
- do not expose `9080` through Internet Sharing, a tunnel, or port forwarding;
- preserve normal HTTPS egress to the VM and Convene through WAN/Wi-Fi.

Use the site's approved macOS packet-filter configuration and capture its exact
rule and rollback. The macOS application firewall alone does not prove
source-address/interface scoping.

## 4. Runtime staging

```bash
cd /Users/lukewaszyn/RECLAIM_LiveTwin
python3.12 -m venv .venv-macbook
.venv-macbook/bin/python -m pip install -r pi_gateway/requirements.txt
mkdir -p "$HOME/Library/Application Support/RECLAIM/edge-gateway"
mkdir -p "$HOME/Library/Logs/RECLAIM"
cp pi_gateway/config.macbook.example.yaml \
  "$HOME/Library/Application Support/RECLAIM/edge-gateway/config.yaml"
chmod 600 "$HOME/Library/Application Support/RECLAIM/edge-gateway/config.yaml"
```

Record package versions and available disk space. Keep the queue, logs, and
captures on persistent local storage. Configure rotation/retention before a long
soak.

## 5. Configuration review

The populated configuration must define:

- Windows gateway `listen_host: <WINDOWS10_GATEWAY_IP>`, not the cRIO address;
- `listen_port: 9070`, `status_port: 9080`;
- `conn_idle_timeout_s: 15.0`, `max_line_bytes: 8192`;
- `strict_fields: false` until the signed complete manifest exists;
- an absolute persistent `buffer_path`;
- `transport: console` for first foreground proof;
- later, `transport: https`, `mode: live`, current `/ingest` URL, ingest token,
  and `verify_tls: true`;
- a separate MacBook Convene credential if raw gateway publishing is enabled.

Use `chmod 600` for configuration and credentials. Never print or diff a live
token into retained output.

## 6. Local verification

```bash
PYTHONPATH=pi_gateway .venv-macbook/bin/python -m pytest pi_gateway -q
PYTHONPATH=cloud_engine .venv-macbook/bin/python -m pytest cloud_engine -q
PYTHONPATH=crio_source_record .venv-macbook/bin/python -m pytest crio_source_record -q
PYTHONPATH="pi_gateway:cloud_engine:$PWD" \
  .venv-macbook/bin/python -m crio_source_record.bench_replay
```

Run the gateway in the foreground and verify `/health`, `/latest`, listener
addresses, Ctrl+C shutdown, restart, and queue preservation. Do not install
`launchd` until these pass.

## 7. Cloud verification

The VM owner privately supplies only the ingest URL/token, engine SHA, freshness
limit, and availability window. The MacBook must prove HTTPS/TLS delivery through
the actual tunnel. `/health` alone is insufficient; require matching engine
run/source/sequence, state bridge output, raw gateway, `sim_`, and stale expiry.

Close `deployment/CLOUD_ENGINE_LIVE_SCENARIO_HANDOFF_PROMPT.md` before accepting
the gateway if frames dead-letter as `timestamp_stale`.

## 8. launchd and competition posture

Follow `pi_gateway/macos/README.md`. Validate the LaunchAgent, reboot, log in,
and verify it returns. Connect AC power and disable sleep/automatic logout for the
event. Keep a foreground start command and rollback command available.

## 9. Go/no-go

Proceed only when every applicable item in
`deployment/GATEWAY_GO_LIVE.md` is closed. If the real cRIO contract is not
accepted, run only an explicitly labeled synthetic demonstration through the
MacBook and production VM.
