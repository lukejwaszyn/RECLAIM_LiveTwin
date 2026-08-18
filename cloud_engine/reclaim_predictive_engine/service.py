"""
REST service bridge—predictive engine -> Convene digital-thread block.

Convene's thread block ingests one way: it polls a REST endpoint and feeds the
returned fields in as observed attributes. This module wraps the predictive
engine as a small HTTP service designed to run inside a Convene integrated VM
(alongside the Fusion 360 geometry source and the COMSOL refinement), exposing:

    GET /manifest  -> self-describing variable + state catalog (for the sensing
                      agent to auto-detect and bind; manual mapping also fine)
    GET /state     -> latest frame, flattened to {attribute: value} so Convene
                      can map each observed attribute directly from the JSON
    GET /history   -> last N frames (sparklines / trend panels)
    GET /health    -> liveness

Standard library only (http.server, threading, json) so it runs unmodified in
any VM. A background driver advances the engine over the synthetic scenario
harness at a configurable speed, so the polled state moves the way the hardware
would. Swap the driver for a TDMS replay or a live cRIO feed later without
touching the HTTP surface.

Run:
    python -m reclaim_predictive_engine.service --scenario runaway --port 8077 --speed 6
Then point a Convene thread block's REST endpoint at  http://<vm-host>:8077/state

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations

import argparse
import json
import math
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _jsonable(v):
    """JSON has no Infinity/NaN. Map non-finite floats to None (= 'no value').
    t_star = None therefore reads cleanly as 'no event predicted'."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v

from .config import EngineConfig, PhysicalParams, ENVIRONMENTS
from .engine import PredictiveEngine
from .thread import StateStreamPublisher, default_manifest
from .harness import (TruthPlant, runaway_scenario, nominal_scenario,
                      power_outage_scenario, ramp_scenario, seal_leak_scenario, Scenario)

SCENARIOS = {"runaway": runaway_scenario, "nominal": nominal_scenario,
             "power_outage": power_outage_scenario, "ramp": ramp_scenario,
             "seal_leak": seal_leak_scenario}


class TwinStateService:
    """Thread-safe holder of the latest manifest + frame, fed by a driver."""

    def __init__(self, history: int = 600, *, scenario: str | None = None,
                 environment: str | None = None, speed: float | None = None,
                 feed: str | None = None, host: str = "127.0.0.1",
                 port: int = 0):
        self._lock = threading.Lock()
        self._manifest = json.loads(default_manifest().to_json())
        self._latest = {"t_sim": None, "op_state": "S_Idle", "events": [],
                        "status": "starting"}
        self._history = deque(maxlen=history)
        self.cycle = 0
        self.metadata = {}
        if scenario is not None:
            self.metadata = {
                "mode": "harness" if feed == "harness" else "replay",
                "scenario": scenario,
                "environment": environment,
                "speed": speed,
                "feed": feed,
                "host": host,
                "port": port,
            }

    def set_manifest(self, manifest_json: str):
        with self._lock:
            self._manifest = json.loads(manifest_json)

    def update(self, frame_values: dict, t_sim: float, events, cycle: int):
        rec = _jsonable(dict(frame_values))
        for key in ("mode", "scenario", "environment", "speed"):
            if key in self.metadata:
                rec[key] = self.metadata[key]
        rec["t_sim"] = t_sim
        rec["events"] = list(events)
        rec["cycle"] = cycle
        rec["status"] = "running"
        with self._lock:
            self.cycle = cycle
            self._latest = rec
            self._history.append(rec)

    def manifest(self) -> dict:
        with self._lock:
            return dict(self._manifest)

    def state(self) -> dict:
        with self._lock:
            return dict(self._latest)

    def history(self, n: int) -> list:
        with self._lock:
            return list(self._history)[-n:]

    def health(self) -> dict:
        with self._lock:
            return {
                "ok": True,
                "service": "reclaim-predictive-engine",
                **self.metadata,
                "cycle": self.cycle,
                "status": self._latest.get("status", "starting"),
                "t_sim": self._latest.get("t_sim"),
            }


def _make_handler(svc: TwinStateService):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, obj, code=200):
            body = json.dumps(_jsonable(obj)).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")  # canvas/agent polling
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0].rstrip("/")
            if path in ("", "/health"):
                self._send(svc.health())
            elif path == "/manifest":
                self._send(svc.manifest())
            elif path == "/state":
                self._send(svc.state())
            elif path == "/history":
                # Keep enough samples to retain both the interruption and restart
                # transitions in the 900-second power-outage rehearsal.
                self._send({"frames": svc.history(600)})
            else:
                self._send({"error": "not found",
                            "endpoints": ["/manifest", "/state", "/history", "/health"]}, 404)

        def log_message(self, *a):  # quiet
            return
    return Handler


def _build_engine(svc: TwinStateService, env_name: str):
    cfg = EngineConfig(physical=PhysicalParams(), environment=env_name)
    cfg.forecast.every = 1
    pub = StateStreamPublisher(default_manifest(),
                               sink=lambda msg: _route(svc, msg))
    return PredictiveEngine(cfg, publisher=pub, use_gp=False), cfg


def _route(svc: TwinStateService, msg: str):
    """Publisher sink: capture the manifest if that's what was emitted."""
    try:
        obj = json.loads(msg)
    except Exception:
        return
    if obj.get("type") == "manifest":
        svc.set_manifest(msg)


def driver(svc: TwinStateService, scenario_name: str, env_name: str,
           speed: float, loop: bool, stop: threading.Event):
    """Advance the engine over the harness, updating the service in ~real time.

    speed = simulated seconds per wall-clock second (e.g. 6 -> 6x faster).
    """
    env = ENVIRONMENTS[env_name]
    while not stop.is_set():
        svc.cycle += 1
        eng, cfg = _build_engine(svc, env_name)
        scenario: Scenario = SCENARIOS.get(scenario_name, runaway_scenario)(env)
        truth = TruthPlant(PhysicalParams(), scenario, seed=svc.cycle)
        dt = scenario.dt
        for t, z, p_fwd, p_refl, _ in truth.stream():
            if stop.is_set():
                return
            op_state = scenario.op_state_fn(t) if scenario.op_state_fn else "S_MicrowaveHeating"
            extra = scenario.event_fn(t) if scenario.event_fn else None
            pch = scenario.pressure_fn(t) if scenario.pressure_fn else None
            out = eng.step(t, z, p_fwd, p_refl, op_state=op_state, extra_events=extra,
                           p_chamber=pch)
            svc.update(out.frame.values, t, out.frame.events, svc.cycle)
            time.sleep(max(0.0, dt / max(speed, 1e-6)))
            if z[0] >= float(cfg.physical.t_limit):
                break
        if not loop:
            return
        time.sleep(1.0)


def replay_driver(svc: TwinStateService, path: str, env_name: str,
                  speed: float, loop: bool, stop: threading.Event):
    """Feed the engine from a logged TDMS/CSV file instead of the harness.
    Same HTTP surface; this is the path to live physical-asset monitoring."""
    try:
        from .ingest import replay_stream
    except ImportError as exc:   # fix M1: fail loudly, not with a bare traceback
        raise SystemExit(
            "--feed replay requires the optional 'ingest' replay module, which is "
            "not part of this live-twin release (it lives in the source workspace "
            "with the TDMS tooling). Use the live push path (push_ingest_dual.py) "
            f"or restore reclaim_predictive_engine/ingest.py. ({exc})") from exc
    while not stop.is_set():
        svc.cycle += 1
        eng, cfg = _build_engine(svc, env_name)
        for t, z, p_fwd, p_refl in replay_stream(path):
            if stop.is_set():
                return
            out = eng.step(t, z, p_fwd, p_refl)
            svc.update(out.frame.values, t, out.frame.events, svc.cycle)
            time.sleep(max(0.0, 1.0 / max(speed, 1e-6)))
        if not loop:
            return
        time.sleep(1.0)


def main():
    ap = argparse.ArgumentParser(description="RECLAIM predictive-engine REST service")
    ap.add_argument("--scenario", default="runaway", choices=list(SCENARIOS))
    ap.add_argument("--env", default="earth_lab", choices=list(ENVIRONMENTS))
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8077)
    ap.add_argument("--speed", type=float, default=6.0, help="sim s per wall s")
    ap.add_argument("--no-loop", action="store_true")
    ap.add_argument("--feed", default="harness", choices=["harness", "replay"],
                    help="harness = synthetic scenarios; replay = TDMS/CSV file")
    ap.add_argument("--file", default=None, help="TDMS/CSV path when --feed replay")
    args = ap.parse_args()

    svc = TwinStateService(
        scenario=args.scenario,
        environment=args.env,
        speed=args.speed,
        feed=args.feed,
        host=args.host,
        port=args.port,
    )
    stop = threading.Event()
    if args.feed == "replay":
        if not args.file:
            ap.error("--feed replay requires --file <path.tdms|.csv>")
        th = threading.Thread(target=replay_driver, args=(svc, args.file, args.env,
                              args.speed, not args.no_loop, stop), daemon=True)
    else:
        th = threading.Thread(target=driver, args=(svc, args.scenario, args.env,
                              args.speed, not args.no_loop, stop), daemon=True)
    th.start()

    server = ThreadingHTTPServer((args.host, args.port), _make_handler(svc))
    print(f"[reclaim] serving on http://{args.host}:{args.port}  "
          f"(scenario={args.scenario}, env={args.env}, speed={args.speed}x)")
    print("[reclaim] endpoints: /manifest  /state  /history  /health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.shutdown()


if __name__ == "__main__":
    main()
