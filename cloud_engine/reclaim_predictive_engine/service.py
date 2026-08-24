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

from .config import EngineConfig, ENVIRONMENTS, chamber_params
from .engine import PredictiveEngine
from .thread import StateStreamPublisher, default_manifest
from .harness import (TruthPlant, runaway_scenario, nominal_scenario,
                      power_outage_scenario, lunar_surface_process_scenario,
                      ramp_scenario, seal_leak_scenario, Scenario)

SCENARIOS = {"runaway": runaway_scenario, "nominal": nominal_scenario,
             "power_outage": power_outage_scenario, "ramp": ramp_scenario,
             "seal_leak": seal_leak_scenario,
             "lunar_surface_process": lunar_surface_process_scenario}


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

    def mark_stopped(self) -> None:
        """The driver has finished producing frames — stop reporting `running`.

        Without this, /state and /health keep advertising `status: running` over
        a record that can no longer change, which is exactly the misleading
        display the loss-of-data rehearsal exists to catch. The latest view is
        copied before mutation so the history entry keeps the status it actually
        had while the stream was live.
        """
        with self._lock:
            if self._latest.get("status") == "running":
                self._latest = dict(self._latest)
                self._latest["status"] = "stopped"

    def manifest(self) -> dict:
        with self._lock:
            return dict(self._manifest)

    def state(self) -> dict:
        with self._lock:
            # /state is the scalar digital-thread surface. Structured event
            # detail remains available from /history, while event_count and
            # last_event carry the current summary for scalar-only consumers
            # such as the Convene shared-file agent.
            return {
                key: value
                for key, value in self._latest.items()
                if value is None or isinstance(value, (str, bool, int, float))
            }

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


CHAMBERS = ("PL", "MT")


def _build_engine(svc: TwinStateService, env_name: str, chamber_id: str = "PL"):
    # chamber_params(chamber_id) applies the CAD-derived geometry, material, and
    # t_wall_limit for the named chamber; the bare PhysicalParams() default this
    # replaced carries none of that (see the current Convene-routed handoff).
    cfg = EngineConfig(physical=chamber_params(chamber_id), environment=env_name,
                       chamber_id=chamber_id)
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


def _dual_manifest_json() -> str:
    """PL_/MT_-prefixed manifest for the dual-chamber rehearsal, mirroring the
    production fan-out (push_ingest_dual.py) so /manifest matches what /state
    actually publishes once both chambers are stepped. Rehearsal-identity
    fields (mode/scenario/environment/speed) stay unprefixed -- they describe
    the service run, not a chamber -- while op_state is republished per
    chamber since PL and MT can be in different phases."""
    base = default_manifest()
    identity_names = {"mode", "scenario", "environment", "speed"}
    variables = [v.to_dict() for v in base.variables if v.name in identity_names]
    chamber_fields = [v for v in base.variables if v.name not in identity_names]
    for prefix in ("PL_", "MT_"):
        for v in chamber_fields:
            d = v.to_dict()
            d["name"] = prefix + d["name"]
            variables.append(d)
    return json.dumps({
        "type": "manifest", "system": base.system, "model_ref": base.model_ref,
        "schema_version": base.schema_version, "chambers": list(CHAMBERS),
        "variables": variables, "states": base.states,
    })


def driver(svc: TwinStateService, scenario_name: str, env_name: str,
           speed: float, loop: bool, stop: threading.Event):
    """Advance PL and MT engines over the harness in lockstep, updating the
    service in ~real time. Matches production's dual-chamber fan-out
    (push_ingest_dual.py): two independent engine instances -- each bound to
    its own chamber_params, including its own TruthPlant so the simulated
    truth and the estimator's forward model agree -- stepping the same
    simulated clock. Combined frame values publish PL_*/MT_*-prefixed.

    speed = simulated seconds per wall-clock second (e.g. 6 -> 6x faster).
    """
    env = ENVIRONMENTS[env_name]
    while not stop.is_set():
        svc.cycle += 1
        engines = {}
        streams = {}
        for i, ch in enumerate(CHAMBERS):
            eng, cfg = _build_engine(svc, env_name, ch)
            scenario: Scenario = SCENARIOS.get(scenario_name, runaway_scenario)(env)
            # distinct seed per chamber so PL/MT measurement noise is independent,
            # not a mirrored copy of the same draw.
            truth = TruthPlant(chamber_params(ch), scenario, seed=svc.cycle * 2 + i)
            engines[ch] = (eng, cfg, scenario)
            streams[ch] = truth.stream()
        # engine construction re-emits each engine's own (unprefixed) manifest via
        # _route; reassert the dual, prefixed manifest now that both are built.
        svc.set_manifest(_dual_manifest_json())
        dt = engines["PL"][2].dt
        done = {ch: False for ch in CHAMBERS}
        combined: dict = {}
        for (t_pl, z_pl, pf_pl, pr_pl, _), (t_mt, z_mt, pf_mt, pr_mt, _) \
                in zip(streams["PL"], streams["MT"]):
            if stop.is_set():
                return
            events: list = []
            for ch, t, z, p_fwd, p_refl in (
                ("PL", t_pl, z_pl, pf_pl, pr_pl), ("MT", t_mt, z_mt, pf_mt, pr_mt),
            ):
                if done[ch]:
                    continue    # keep publishing this chamber's last frozen values
                eng, cfg, scenario = engines[ch]
                op_state = scenario.op_state_fn(t) if scenario.op_state_fn else "S_MicrowaveHeating"
                extra = scenario.event_fn(t) if scenario.event_fn else None
                pch = scenario.pressure_fn(t) if scenario.pressure_fn else None
                out = eng.step(t, z, p_fwd, p_refl, op_state=op_state, extra_events=extra,
                               p_chamber=pch)
                combined.update({f"{ch}_{k}": v for k, v in out.frame.values.items()})
                events += [f"{ch}:{e}" for e in out.frame.events]
                if z[0] >= float(cfg.physical.t_limit):
                    done[ch] = True
            # PL and MT run the same scenario_name/env, so op_state_fn(t) agrees
            # between them; expose it unprefixed too for identity consumers.
            combined["op_state"] = combined.get("PL_op_state", combined.get("MT_op_state"))
            svc.update(combined, t_pl, events, svc.cycle)
            time.sleep(max(0.0, dt / max(speed, 1e-6)))
            if all(done.values()):
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

    def _drive_then_mark(fn, *fn_args):
        """Run a driver and flag the stream stopped when it returns, so a
        finished (--no-loop) or exhausted run stops reading as live."""
        try:
            fn(*fn_args)
        finally:
            svc.mark_stopped()

    if args.feed == "replay":
        if not args.file:
            ap.error("--feed replay requires --file <path.tdms|.csv>")
        th = threading.Thread(target=_drive_then_mark,
                              args=(replay_driver, svc, args.file, args.env,
                                    args.speed, not args.no_loop, stop), daemon=True)
    else:
        th = threading.Thread(target=_drive_then_mark,
                              args=(driver, svc, args.scenario, args.env,
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
