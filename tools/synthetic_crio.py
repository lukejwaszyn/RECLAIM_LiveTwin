"""Synthetic scenario source for the loopback-only MacBook scenario host.

The rehearsal services on 8177-8181 run their own estimator in-process and
publish finished answers. That exercises the physics but *short-cuts the
pipeline*: nothing downstream of the plant is tested.

It emits the same channel shape as the cRIO for explicit scenario runs, but it
does not participate in the Windows 10 desktop's live-data path:

    synthetic_crio -> MacBook loopback receiver -> framer -> Convene scenario machine

It writes line-delimited raw LabVIEW-shaped scenario frames in the same units to
the MacBook's local socket.

The installed MacBook service owns the scenario envelope and stamps
``mode=harness`` or ``mode=replay``. The raw frame carries a conspicuous
``reclaim-synthetic-scenario`` source identity. Any Convene-to-VM scenario pipe
is configured separately.

Read-only with respect to `cloud_engine`: it imports the physics harness and
changes nothing there.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator

# cloud_engine is the VM's software and is read-only from this desktop. Import
# the harness; never modify it.
_CLOUD_ENGINE = Path(__file__).resolve().parents[1] / "cloud_engine"
if str(_CLOUD_ENGINE) not in sys.path:
    sys.path.insert(0, str(_CLOUD_ENGINE))

from reclaim_predictive_engine.harness import TruthPlant  # noqa: E402
from reclaim_predictive_engine.config import ENVIRONMENTS, chamber_params  # noqa: E402
# Import the scenario table the rehearsals themselves use, so the two can never
# drift apart. Importing the module defines names only; it starts no server.
from reclaim_predictive_engine.service import SCENARIOS  # noqa: E402

log = logging.getLogger("reclaim.synthetic_crio")

C_TO_K = 273.15
TORR_TO_KPA = 0.1333224

#: Deterministic per-thermocouple offsets (degC) around the true bed
#: temperature. The four-TC mean stays the true value, which is what the raw
#: audit compares against sim_PL_T_bed_meas.
_TC_OFFSETS = (-0.35, -0.12, 0.12, 0.35)


def _k_to_c(kelvin: float) -> float:
    """The cRIO reports degC; the cloud converts back (labview_map.py:31)."""
    return kelvin - C_TO_K


def _kpa_to_torr(kpa: float) -> float:
    """The cRIO reports Torr; the cloud converts back (labview_map.py:32)."""
    return kpa / TORR_TO_KPA


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_channels(t_bed_K: float, t_wall_K: float, p_fwd_W: float,
                   p_refl_W: float, p_chamber_kPa: float | None = None,
                   active_chamber: str = "PL",
                   ) -> Dict[str, Any]:
    """The raw LabVIEW channel block, in the cRIO's own names and units.

    Names come from `labview_map.py`'s raw tables, not invented here: the four
    plastics bed thermocouples, the IR skin temperature that becomes the wall
    node, chamber pressure, the shared SSMG power pair, and the flags that tell
    the mapper which chamber the SSMG is driving.
    """
    if active_chamber not in {"PL", "MT"}:
        raise ValueError("active_chamber must be PL or MT")

    channels: Dict[str, Any] = {
        # Shared SSMG power is attributed by the authoritative envelope chamber.
        "MW_power": round(float(p_fwd_W), 1),
        "MW_reverse": round(float(p_refl_W), 2),
        "MW_RF": bool(p_fwd_W > 0.0),
        # Keep the legacy inference signal consistent with the envelope so an MT
        # scenario does not generate a false CHAMBER_MISMATCH diagnostic.
        "PL_process": active_chamber == "PL",
    }
    if active_chamber == "PL":
        channels.update({
            f"PL_bottom{i + 1}": round(_k_to_c(t_bed_K) + offset, 3)
            for i, offset in enumerate(_TC_OFFSETS)
        })
        channels["PL_surface_temp"] = round(_k_to_c(t_wall_K), 3)
    else:
        # These are the two signed MT channels currently mapped by labview_map.
        channels["MT_bottom"] = round(_k_to_c(t_bed_K), 3)
        channels["MT_top"] = round(_k_to_c(t_wall_K), 3)

    if (active_chamber == "PL" and p_chamber_kPa is not None
            and math.isfinite(p_chamber_kPa)):
        channels["PL_chamber_pressure"] = round(_kpa_to_torr(p_chamber_kPa), 4)
    return channels


def build_raw_frame(t_bed_K: float, t_wall_K: float, p_fwd_W: float,
                    p_refl_W: float, op_state: str,
                    p_chamber_kPa: float | None = None,
                    cycle_id: str = "synthetic-scenario",
                    source_id: str = "reclaim-synthetic-scenario",
                    active_chamber: str = "PL") -> Dict[str, Any]:
    """One line on the wire, in the shape the gateway's receiver requires.

    Network input is stricter than the framer's direct-caller API: `parse_line`
    rejects any object without an explicit `vars` block (`framer.py:158`). The
    envelope hints stay at the top level, where the framer looks for them
    (`framer.py:127-131`); everything else is a channel.
    """
    return {
        "source_id": source_id,
        "ts": _now_iso(),
        "source_op_state": op_state,
        "active_chamber": active_chamber,
        "cycle_id": cycle_id,
        "vars": build_channels(
            t_bed_K, t_wall_K, p_fwd_W, p_refl_W, p_chamber_kPa,
            active_chamber,
        ),
    }


def plant_frames(scenario_name: str, env_name: str, cycle: int = 1,
                 active_chamber: str = "PL",
                 ) -> Iterator[tuple[float, Dict[str, Any], float]]:
    """Yield (t_sim, raw_frame, dt) from the same harness the rehearsals use."""
    env = ENVIRONMENTS[env_name]
    scenario = SCENARIOS[scenario_name](env)
    truth = TruthPlant(chamber_params(active_chamber), scenario, seed=cycle)
    source_id = f"reclaim-synthetic-scenario:{active_chamber}:{scenario_name}:{env_name}"
    cycle_id = f"synthetic-{active_chamber}-{scenario_name}-{env_name}-{cycle:03d}"
    for t, z, p_fwd, p_refl, _x in truth.stream():
        op_state = scenario.op_state_fn(t) if scenario.op_state_fn else "S_MicrowaveHeating"
        p_chamber = scenario.pressure_fn(t) if scenario.pressure_fn else None
        yield t, build_raw_frame(float(z[0]), float(z[1]), float(p_fwd),
                                 float(p_refl), op_state, p_chamber,
                                 cycle_id, source_id, active_chamber), scenario.dt


class SyntheticCrio:
    """Hold one outbound connection to the gateway and stream raw frames.

    The gateway's receiver accepts a single cRIO connection and reads
    line-delimited JSON (`receiver.py`), so this is deliberately the same shape:
    connect, write lines, let the gateway own framing, sequence and identity.
    """

    def __init__(self, host: str, port: int, timeout_s: float = 10.0):
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self._sock: socket.socket | None = None
        self.sent = 0

    def connect(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout_s)
        sock.connect((self.host, self.port))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self._sock = sock
        log.info("connected to gateway at %s:%d", self.host, self.port)

    def send(self, frame: Dict[str, Any]) -> None:
        if self._sock is None:
            raise RuntimeError("not connected")
        self._sock.sendall((json.dumps(frame) + "\n").encode("utf-8"))
        self.sent += 1

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._sock.close()
            self._sock = None

    def __enter__(self) -> "SyntheticCrio":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Impersonate the cRIO and drive the real pipeline with synthetic frames"
    )
    parser.add_argument("--scenario", default="nominal", choices=sorted(SCENARIOS))
    parser.add_argument("--env", default="earth_lab", choices=sorted(ENVIRONMENTS))
    parser.add_argument("--active-chamber", choices=("PL", "MT"), default="PL")
    parser.add_argument("--host", default="127.0.0.1", help="gateway receiver host")
    parser.add_argument("--port", type=int, default=9070, help="gateway receiver port")
    parser.add_argument("--speed", type=float, default=2.0, help="sim s per wall s")
    parser.add_argument("--cycles", type=int, default=0, help="0 = loop forever")
    parser.add_argument("--max-frames", type=int, default=0, help="0 = unlimited")
    parser.add_argument("--dry-run", action="store_true",
                        help="print frames instead of connecting; touches no socket")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    log.info("synthetic cRIO: chamber=%s scenario=%s env=%s speed=%sx -> %s:%d%s",
             args.active_chamber, args.scenario, args.env, args.speed, args.host, args.port,
             "  [DRY RUN, no socket]" if args.dry_run else "")
    log.info("scenario path: local source -> MacBook -> Convene exact-name variables")

    crio = None if args.dry_run else SyntheticCrio(args.host, args.port)
    if crio is not None:
        crio.connect()

    sent = 0
    cycle = 0
    try:
        while True:
            cycle += 1
            for t, frame, dt in plant_frames(
                args.scenario, args.env, cycle, args.active_chamber
            ):
                if args.dry_run:
                    print(json.dumps(frame))
                else:
                    crio.send(frame)
                sent += 1
                if args.max_frames and sent >= args.max_frames:
                    log.info("reached --max-frames %d; stopping", args.max_frames)
                    return 0
                time.sleep(max(0.0, dt / max(args.speed, 1e-6)))
            log.info("cycle %d complete (%d frames sent)", cycle, sent)
            if args.cycles and cycle >= args.cycles:
                return 0
            time.sleep(1.0)
    except KeyboardInterrupt:
        log.info("stopped after %d frames", sent)
        return 0
    except (OSError, ConnectionError) as exc:
        log.error("gateway connection failed after %d frames: %s", sent, exc)
        return 1
    finally:
        if crio is not None:
            crio.close()


if __name__ == "__main__":
    raise SystemExit(main())
