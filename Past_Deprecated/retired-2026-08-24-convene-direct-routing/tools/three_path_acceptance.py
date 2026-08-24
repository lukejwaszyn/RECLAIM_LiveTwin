#!/usr/bin/env python3
"""Run the complete RECLAIM three-path acceptance chain on one host.

This is a historical isolated component rehearsal, not the deployed architecture.
The deployed MacBook is scenario-only and has no direct cloud path. This tool runs the
production gateway, production ingest engine, and production state bridge with
short-lived credentials and Cloudflare Quick Tunnels. A narrow local acceptance
sink emulates only Convene's two documented write surfaces so correlation can be
proved before production machine credentials are installed:

    isolated synthetic source -> temporary gateway component
      |-> HTTPS/cloudflared -> Convene sink (exact source names)
      `-> HTTPS/cloudflared -> production engine -> state bridge
                                              -> Convene heartbeat sink sim_*

No credential is printed or written to the evidence file. Quick-tunnel URLs are
ephemeral and are evidence, not production configuration.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import select
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests
import yaml


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv-macbook" / "bin" / "python"
TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
SCENARIOS = (
    ("nominal", "nominal", "earth_lab"),
    ("power-outage", "power_outage", "earth_lab"),
    ("lunar", "nominal", "lunar_surface"),
)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


class ManagedProcess:
    def __init__(self, name: str, args: list[str], log_path: Path, *, env=None):
        self.name = name
        self.args = args
        self.log_path = log_path
        self._log = log_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            args,
            cwd=ROOT,
            env=env,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def assert_running(self) -> None:
        code = self.process.poll()
        if code is not None:
            raise RuntimeError(
                f"{self.name} exited with {code}; inspect {self.log_path}"
            )

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self._log.close()


class QuickTunnel(ManagedProcess):
    def __init__(self, name: str, origin: str, log_path: Path):
        cloudflared = shutil.which("cloudflared")
        if not cloudflared:
            raise RuntimeError("cloudflared is not installed")
        super().__init__(
            name,
            [
                cloudflared,
                "tunnel",
                "--url",
                origin,
                "--no-autoupdate",
                "--loglevel",
                "info",
            ],
            log_path,
        )
        self.url = self._wait_for_url()

    def _wait_for_url(self, timeout_s: float = 45.0) -> str:
        deadline = time.time() + timeout_s
        discovered = ""
        while time.time() < deadline:
            self.assert_running()
            self._log.flush()
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
            match = TUNNEL_URL.search(text)
            if match:
                discovered = match.group(0)
            if discovered and "Registered tunnel connection" in text:
                return discovered
            time.sleep(0.25)
        raise TimeoutError(f"{self.name} did not publish a Quick Tunnel URL")


class RestrictedConnectProxy:
    """Loopback CONNECT proxy for networks that block trycloudflare DNS.

    TLS remains end-to-end between the caller and Cloudflare. The proxy accepts
    only ``*.trycloudflare.com:443`` and pins the connection to Cloudflare's
    public anycast edge; it cannot be used as a general-purpose proxy.
    """

    EDGE_IPS = ("104.16.231.132", "104.16.230.132")

    def __init__(self, port: int):
        parent = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                self.request.settimeout(10)
                request = bytearray()
                while b"\r\n\r\n" not in request and len(request) < 16_384:
                    chunk = self.request.recv(4096)
                    if not chunk:
                        return
                    request.extend(chunk)
                first = bytes(request).split(b"\r\n", 1)[0].decode("ascii", "replace")
                parts = first.split()
                if len(parts) != 3 or parts[0].upper() != "CONNECT":
                    self.request.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
                    return
                host, separator, port_text = parts[1].rpartition(":")
                if (
                    not separator
                    or not host.endswith(".trycloudflare.com")
                    or port_text != "443"
                ):
                    self.request.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                    return
                upstream = None
                for edge_ip in parent.EDGE_IPS:
                    try:
                        upstream = socket.create_connection((edge_ip, 443), timeout=10)
                        break
                    except OSError:
                        continue
                if upstream is None:
                    self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                    return
                with upstream:
                    self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    sockets = (self.request, upstream)
                    while True:
                        readable, _, _ = select.select(sockets, (), (), 15)
                        if not readable:
                            continue
                        for source in readable:
                            try:
                                data = source.recv(65_536)
                            except OSError:
                                return
                            if not data:
                                return
                            target = upstream if source is self.request else self.request
                            target.sendall(data)

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.server = Server(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever, name="restricted-connect-proxy", daemon=True
        )
        self.url = f"http://127.0.0.1:{port}"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


class ConveneAcceptanceSink:
    """Authenticated recorder for Convene's direct and heartbeat write shapes."""

    def __init__(self, port: int, gateway_token: str, vm_token: str):
        self.port = port
        self.gateway_token = gateway_token
        self.vm_token = vm_token
        self.lock = threading.Lock()
        self.gw_count = 0
        self.sim_count = 0
        self.latest_gw: dict[str, Any] = {}
        self.latest_sim: dict[str, Any] = {}
        self.namespace_errors: list[str] = []
        self.server = self._build_server()
        self.thread = threading.Thread(
            target=self.server.serve_forever, name="convene-acceptance-sink", daemon=True
        )

    def _build_server(self) -> ThreadingHTTPServer:
        sink = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, status: int, body: dict[str, Any]) -> None:
                encoded = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_GET(self) -> None:
                if self.path.rstrip("/") == "/health":
                    self._reply(200, {"ok": True, "service": "convene-acceptance-sink"})
                else:
                    self._reply(404, {"error": "not found"})

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                try:
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return self._reply(400, {"error": "invalid JSON"})
                token = self.headers.get("X-Agent-Token", "")
                path = self.path.rstrip("/")
                if path == "/api/machine/publish":
                    if token != sink.gateway_token:
                        return self._reply(401, {"error": "unauthorized"})
                    variables = body.get("variables")
                    if not isinstance(variables, dict):
                        return self._reply(400, {"error": "variables required"})
                    # Gateway fields keep their exact canonical names. A
                    # contract-defined gw_ field is legal; sim_ remains owned
                    # exclusively by the cloud-engine publisher.
                    wrong = [key for key in variables if key.startswith("sim_")]
                    with sink.lock:
                        sink.namespace_errors.extend(wrong)
                        sink.latest_gw = dict(variables)
                        sink.gw_count += 1
                    return self._reply(200, {"ok": True})
                if path == "/api/machine/heartbeat":
                    if token != sink.vm_token:
                        return self._reply(401, {"error": "unauthorized"})
                    variables = body.get("simVars")
                    if not isinstance(variables, dict):
                        return self._reply(400, {"error": "simVars required"})
                    # The production Convene agent sends unprefixed simVars;
                    # Convene exposes that machine namespace as sim_*.
                    exposed = {
                        key if key.startswith("sim_") else f"sim_{key}": value
                        for key, value in variables.items()
                    }
                    wrong = [key for key in exposed if not key.startswith("sim_")]
                    with sink.lock:
                        sink.namespace_errors.extend(wrong)
                        sink.latest_sim = exposed
                        sink.sim_count += 1
                    return self._reply(200, {"commands": [], "autoMetrics": []})
                self._reply(404, {"error": "not found"})

            def log_message(self, *_args) -> None:
                return

        return ThreadingHTTPServer(("127.0.0.1", self.port), Handler)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "gw_count": self.gw_count,
                "sim_count": self.sim_count,
                "latest_gw": dict(self.latest_gw),
                "latest_sim": dict(self.latest_sim),
                "namespace_errors": list(self.namespace_errors),
            }


class SimHeartbeatAgent(threading.Thread):
    """Acceptance-only stand-in for the installed VM Convene heartbeat agent."""

    def __init__(
        self, source: Path, api: str, token: str, stop: threading.Event, proxy_url: str
    ):
        super().__init__(name="sim-heartbeat-agent", daemon=True)
        self.source = source
        self.api = api.rstrip("/")
        self.token = token
        self.stop_event = stop
        self.proxies = {"https": proxy_url}
        self.delivered = 0
        self.failed = 0

    def run(self) -> None:
        while not self.stop_event.wait(0.25):
            try:
                variables = json.loads(self.source.read_text(encoding="utf-8"))
                response = requests.post(
                    self.api + "/machine/heartbeat",
                    json={"simVars": variables},
                    headers={"X-Agent-Token": self.token},
                    timeout=8,
                    proxies=self.proxies,
                )
                response.raise_for_status()
                self.delivered += 1
            except (OSError, ValueError, requests.RequestException):
                self.failed += 1


def wait_json(
    url: str, *, headers=None, timeout_s: float = 30.0, proxy_url: str | None = None
) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = requests.get(
                url,
                headers=headers or {},
                timeout=5,
                proxies={"https": proxy_url} if proxy_url else None,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            time.sleep(0.25)
    raise TimeoutError(f"JSON endpoint did not become ready: {url}: {last_error}")


def wait_stable_json(
    url: str,
    *,
    consecutive: int = 10,
    timeout_s: float = 45.0,
    proxy_url: str | None = None,
) -> dict[str, Any]:
    """Require repeated tunnel successes before any telemetry is released."""
    deadline = time.time() + timeout_s
    stable = 0
    latest: dict[str, Any] | None = None
    while time.time() < deadline:
        try:
            latest = wait_json(url, timeout_s=5, proxy_url=proxy_url)
            stable += 1
            if stable >= consecutive:
                return latest
        except TimeoutError:
            stable = 0
        time.sleep(0.25)
    raise TimeoutError(f"JSON endpoint did not remain stable: {url}")


def wait_until(predicate, message: str, timeout_s: float = 45.0):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(0.25)
    raise TimeoutError(f"{message}; last observation={last!r}")


def write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    path.chmod(0o600)


def correlation(snapshot: dict[str, Any], expected_source: str) -> dict[str, Any] | None:
    gw = snapshot["latest_gw"]
    sim = snapshot["latest_sim"]
    if not gw or not sim:
        return None
    required_equal = ("run_id", "source_id", "seq", "cycle_id", "source_op_state")
    if any(gw.get(name) != sim.get(f"sim_{name}") for name in required_equal):
        return None
    if gw.get("source_id") != expected_source:
        return None
    if sim.get("sim_data_live") is not True or sim.get("sim_bridge_status") != "ok":
        return None
    raw_bank = [gw.get(f"PL_bottom{i}") for i in range(1, 5)]
    if not all(isinstance(value, (int, float)) for value in raw_bank):
        return None
    expected_kelvin = sum(raw_bank) / 4.0 + 273.15
    measured_kelvin = sim.get("sim_PL_T_bed_meas")
    if not isinstance(measured_kelvin, (int, float)):
        return None
    if abs(expected_kelvin - measured_kelvin) > 0.01:
        return None
    return {
        "run_id": gw["run_id"],
        "source_id": gw["source_id"],
        "cycle_id": gw["cycle_id"],
        "seq": gw["seq"],
        "source_op_state": gw["source_op_state"],
        "raw_bed_mean_degC": round(sum(raw_bank) / 4.0, 4),
        "computed_bed_K": measured_kelvin,
        "sim_data_live": True,
    }


def run(args: argparse.Namespace) -> Path:
    if not PYTHON.exists():
        raise RuntimeError(f"MacBook runtime missing: {PYTHON}")
    work = Path(tempfile.mkdtemp(prefix="reclaim-three-path-"))
    logs = work / "logs"
    logs.mkdir()
    processes: list[ManagedProcess] = []
    sink: ConveneAcceptanceSink | None = None
    connect_proxy: RestrictedConnectProxy | None = None
    agent_stop = threading.Event()
    agent: SimHeartbeatAgent | None = None

    engine_port, sink_port, gateway_port, status_port, proxy_port = (
        free_port() for _ in range(5)
    )
    ingest_token, read_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    gateway_convene_token, vm_convene_token = (
        secrets.token_urlsafe(32),
        secrets.token_urlsafe(32),
    )
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    evidence: dict[str, Any] = {
        "schema_version": "reclaim.three-path-acceptance.v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": sha,
        "tunnel_mode": "cloudflare-quick-tunnel",
        "scenarios": [],
    }

    try:
        sink = ConveneAcceptanceSink(sink_port, gateway_convene_token, vm_convene_token)
        sink.start()
        connect_proxy = RestrictedConnectProxy(proxy_port)
        connect_proxy.start()

        engine_env = os.environ.copy()
        engine_env.update(
            {
                "RECLAIM_INGEST_TOKEN": ingest_token,
                "RECLAIM_READ_TOKEN": read_token,
                "RECLAIM_INGEST_STATE": str(work / "ingest_state.json"),
            }
        )
        engine = ManagedProcess(
            "production engine",
            [
                str(PYTHON),
                "cloud_engine/push_ingest_dual.py",
                "--host",
                "127.0.0.1",
                "--port",
                str(engine_port),
                "--production",
            ],
            logs / "engine.log",
            env=engine_env,
        )
        processes.append(engine)
        wait_json(f"http://127.0.0.1:{engine_port}/health")

        engine_tunnel = QuickTunnel(
            "engine Cloudflare tunnel",
            f"http://127.0.0.1:{engine_port}",
            logs / "engine-tunnel.log",
        )
        processes.append(engine_tunnel)
        convene_tunnel = QuickTunnel(
            "Convene Cloudflare tunnel",
            f"http://127.0.0.1:{sink_port}",
            logs / "convene-tunnel.log",
        )
        processes.append(convene_tunnel)
        wait_stable_json(
            engine_tunnel.url + "/health", timeout_s=45, proxy_url=connect_proxy.url
        )
        wait_stable_json(
            convene_tunnel.url + "/health", timeout_s=45, proxy_url=connect_proxy.url
        )
        evidence["engine_tunnel_host"] = engine_tunnel.url.split("//", 1)[1]
        evidence["convene_tunnel_host"] = convene_tunnel.url.split("//", 1)[1]

        read_secret = work / "read-token.txt"
        read_secret.write_text(read_token, encoding="utf-8")
        read_secret.chmod(0o600)
        sim_vars = work / "sim_vars.json"
        bridge_config = work / "bridge.yaml"
        write_yaml(
            bridge_config,
            {
                "engine_state_url": f"http://127.0.0.1:{engine_port}/state",
                "poll_interval_s": 0.2,
                "request_timeout_s": 1.0,
                "freshness_limit_ms": 15000,
                "publisher_heartbeat_ms": 250,
                "lease_duration_ms": 18000,
                "output_path": str(sim_vars),
                "prefix_mode": "passthrough",
                "environment": "acceptance",
                "engine_source_sha": sha,
                "bridge_source_sha": sha,
                "bridge_instance_id": "three-path-acceptance-bridge",
                "secret_file": str(read_secret),
                "lock_path": str(work / "bridge.lock"),
                "health_path": str(work / "bridge-health.json"),
                "log_path": str(logs / "bridge.log"),
                "replace_retry_timeout_s": 1.0,
                "replace_retry_interval_s": 0.05,
                "allow_non_loopback_state_url": False,
                "live_mode": True,
            },
        )
        bridge = ManagedProcess(
            "state bridge",
            [str(PYTHON), "-m", "convene_bridge", "--config", str(bridge_config)],
            logs / "bridge-console.log",
        )
        processes.append(bridge)
        wait_until(sim_vars.exists, "state bridge did not create sim_vars.json")

        agent = SimHeartbeatAgent(
            sim_vars,
            convene_tunnel.url + "/api",
            vm_convene_token,
            agent_stop,
            connect_proxy.url,
        )
        agent.start()

        credential = work / "gateway-convene.json"
        atomic_json(
            credential,
            {"machineId": "macbook-three-path-acceptance", "agentToken": gateway_convene_token},
        )
        credential.chmod(0o600)
        gateway_config = work / "gateway.yaml"
        write_yaml(
            gateway_config,
            {
                "src": "reclaim-crio-rt-01",
                "run_id": f"three-path-{utc_stamp()}",
                "mode": "live",
                "schema_version": "reclaim.telemetry.v1",
                "listen_host": "127.0.0.1",
                "listen_port": gateway_port,
                "transport": "https",
                "cloud_url": engine_tunnel.url + "/ingest",
                "auth_token": ingest_token,
                "verify_tls": True,
                "convene_enabled": True,
                "convene_api": convene_tunnel.url + "/api",
                "convene_credentials_path": str(credential),
                "convene_timeout_s": 8.0,
                "buffer_path": str(work / "gateway-queue.db"),
                "buffer_max_frames": 500000,
                "publish_batch": 50,
                "publish_interval_s": 0.05,
                "health_interval_s": 2.0,
                "strict_fields": False,
                "conn_idle_timeout_s": 15.0,
                "max_line_bytes": 8192,
                "status_port": status_port,
            },
        )
        gateway_env = os.environ.copy()
        gateway_env.update(
            {
                "RECLAIM_EDGE_CONFIG": str(gateway_config),
                "PYTHONPATH": str(ROOT / "pi_gateway"),
                "HTTPS_PROXY": connect_proxy.url,
                "NO_PROXY": "127.0.0.1,localhost",
            }
        )
        gateway = ManagedProcess(
            "MacBook scenario host",
            [str(PYTHON), "-m", "reclaim_edge.main"],
            logs / "gateway.log",
            env=gateway_env,
        )
        processes.append(gateway)
        status_url = f"http://127.0.0.1:{status_port}"
        wait_json(status_url + "/health")

        for label, scenario, environment in SCENARIOS:
            print(f"[three-path] running {label}", flush=True)
            before = wait_json(status_url + "/health")
            source = f"reclaim-synthetic-scenario:{scenario}:{environment}"
            completed = subprocess.run(
                [
                    str(PYTHON),
                    "tools/synthetic_crio.py",
                    "--scenario",
                    scenario,
                    "--env",
                    environment,
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(gateway_port),
                    "--speed",
                    str(args.speed),
                    "--cycles",
                    "1",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if completed.returncode:
                raise RuntimeError(
                    f"scenario {label} failed: {completed.stdout}\n{completed.stderr}"
                )

            def scenario_ready():
                health = wait_json(status_url + "/health", timeout_s=5)
                latest = wait_json(status_url + "/latest", timeout_s=5)
                snapshot = sink.snapshot()
                corr = correlation(snapshot, source)
                if (
                    health["queue_depth"] == 0
                    and health["received"] == health["delivered"]
                    and latest.get("source_id") == source
                    and corr
                ):
                    return health, snapshot, corr
                return None

            health, snapshot, corr = wait_until(
                scenario_ready, f"{label} did not converge across raw gateway and sim_", timeout_s=90
            )
            record = {
                "profile": label,
                "frames_received": health["received"] - before["received"],
                "frames_delivered": health["delivered"] - before["delivered"],
                "queue_depth": health["queue_depth"],
                "drops": health["drops"],
                "dead_letter": health["dead_letter"],
                "gateway_convene_delivered": health["convene"]["delivered"],
                "gateway_convene_failed": health["convene"]["failed"],
                "sink_gw_publications": snapshot["gw_count"],
                "sink_sim_heartbeats": snapshot["sim_count"],
                "correlation": corr,
                "passed": (
                    health["drops"] == 0
                    and health["dead_letter"] == 0
                    and health["convene"]["failed"] == 0
                    and not snapshot["namespace_errors"]
                ),
            }
            if not record["passed"]:
                raise RuntimeError(f"{label} acceptance failed: {record}")
            evidence["scenarios"].append(record)
            print(
                f"[three-path] PASS {label}: {record['frames_received']} frames, "
                f"correlated seq {corr['seq']}",
                flush=True,
            )

        def stale_ready():
            sim = sink.snapshot()["latest_sim"]
            return sim if sim.get("sim_data_live") is False else None

        stale = wait_until(stale_ready, "sim_ did not fail closed after source stop", 25)
        evidence["stale_expiry"] = {
            "passed": True,
            "sim_data_live": stale.get("sim_data_live"),
            "sim_bridge_status": stale.get("sim_bridge_status"),
            "sim_bridge_error_code": stale.get("sim_bridge_error_code"),
        }
        final_health = wait_json(status_url + "/health")
        evidence["final_gateway_health"] = {
            key: final_health[key]
            for key in (
                "received",
                "delivered",
                "queue_depth",
                "drops",
                "dead_letter",
                "transport",
                "mode",
                "convene",
            )
        }
        evidence["heartbeat_agent"] = {
            "delivered": agent.delivered,
            "failed": agent.failed,
        }
        evidence["passed"] = True
        evidence["completed_at"] = datetime.now(timezone.utc).isoformat()
        output = Path(args.output) if args.output else ROOT / "captures" / f"three-path-{utc_stamp()}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(output, evidence)
        print(f"[three-path] ACCEPTED; evidence: {output}", flush=True)
        return output
    finally:
        agent_stop.set()
        if agent is not None:
            agent.join(timeout=3)
        for process in reversed(processes):
            process.stop()
        if sink is not None:
            sink.stop()
        if connect_proxy is not None:
            connect_proxy.stop()
        if args.keep_workdir:
            print(f"[three-path] retained work directory: {work}", flush=True)
        else:
            shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RECLAIM three-path acceptance")
    parser.add_argument("--speed", type=float, default=100.0)
    parser.add_argument("--output", default="")
    parser.add_argument("--keep-workdir", action="store_true")
    args = parser.parse_args(argv)
    try:
        run(args)
        return 0
    except Exception as exc:
        print(f"[three-path] FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
