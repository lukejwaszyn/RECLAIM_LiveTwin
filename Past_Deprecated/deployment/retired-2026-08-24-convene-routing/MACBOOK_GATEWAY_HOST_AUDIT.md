# MacBook scenario host host audit

> **Role boundary — 2026-08-24:** The Windows 10 desktop is the sole live-data client/gateway. The MacBook is loopback-only and scenario-only; do not execute any contrary MacBook cRIO, OT-network, direct-cloud, or live-cutover instruction retained below. See `deployment/LIVE_GATEWAY_AND_SCENARIO_HOST_DECISION.md`.

**Captured:** 2026-08-23
**Updated after commissioning:** 2026-08-23
**Mutation:** protected runtime state and a user LaunchAgent were installed; no
macOS network or packet-filter settings were changed

## Observed state

| Item | Observation | Disposition |
|---|---|---|
| macOS | 26.5.2, build 25F84 | record for acceptance |
| Hardware | MacBook Air `Mac16,12`, Apple M4, 16 GB, arm64 | recorded without device serials or hardware UUIDs |
| System Python | 3.14.7 | outside repository requirement `<3.14`; do not use for gateway |
| Homebrew Python | 3.12 available at `/opt/homebrew/bin/python3.12` | use for `.venv-macbook`; supported by `pyproject.toml` range |
| Active IPv4 | `en0` = `192.168.12.33/24` | bench/WAN path; not accepted as isolated OT interface |
| Emulated peer | `192.168.12.114:9070` | diagnostic only; not assumed real cRIO |
| Default route | `en0` via `192.168.12.1` | confirms Wi-Fi is current WAN path |
| Available wired adapters | `en3`, `en4` | one can become the dedicated OT path after onsite assignment |
| Port 9070 listener | gateway on `127.0.0.1` | safe local rehearsal binding; not yet physical cRIO binding |
| Port 9080 listener | gateway on `127.0.0.1` | accepted loopback-only binding |
| Gateway sleep assertion | `caffeinate -dimsu` owned by LaunchAgent | prevents idle/display/system sleep while gateway runs |
| Power | AC connected and charging at capture time | reconnect and verify after final placement |
| Display sleep | disabled (`displaysleep 0`) | acceptable for event visibility |
| Persistent storage | 51 GiB available; queue/config/log directories on Data volume | adequate for commissioning; monitor during event |

## Completed local commissioning

- Built `.venv-macbook` with supported Homebrew Python 3.12.
- Passed 55 gateway tests, 76 cloud-engine tests, 70 source-record tests, and
  the bench replay.
- Installed protected configuration, queue, and log paths. Directories are
  `0700`; config, queue, and installed LaunchAgent are `0600`.
- Proved foreground start, loopback listeners, clean Ctrl+C shutdown, restart,
  and the installed `launchd` service.
- Ran one complete accelerated cycle each of nominal, power-outage, lunar, and
  loss-of-data through the installed service. Result: 2,104 received, 2,104
  delivered, queue depth 0, drops 0, dead letters 0.
- Installed a one-command rehearsal launcher that refuses synthetic traffic
  while another device has an established gateway connection.

Python 3.12.13 environment inventory:

```text
certifi 2026.7.22; charset-normalizer 3.5.1; idna 3.19;
iniconfig 2.3.0; joblib 1.5.3; narwhals 2.25.0; numpy 2.5.2;
packaging 26.3; paho-mqtt 1.6.1; pluggy 1.6.0; pygments 2.21.0;
pytest 9.1.1; pyyaml 6.0.3; requests 2.34.2; scikit-learn 1.9.0;
scipy 1.18.1; threadpoolctl 3.6.0; urllib3 2.7.0
```

## Required before physical cRIO cutover

- Attach or identify the dedicated cRIO-facing interface.
- Assign it a static address and confirm the real cRIO peer/subnet.
- Prove that OT interface has no default route.
- Apply and record the source/interface-scoped macOS packet-filter rule for 9070.
- Keep the config template on `127.0.0.1` until the dedicated OT assignment is proven.

## Required before competition operation

- Confirm automatic logout is disabled and retain AC power.
- Reboot once, log in, and verify the LaunchAgent, listeners, and sleep assertion.
- Obtain the production cloud ingest URL/token and Convene credential privately;
  the present safe configuration is `transport: console` with Convene disabled.
- Complete cloud, stale-expiry, real-source, and rollback checks in
  `GATEWAY_GO_LIVE.md`.
