#!/usr/bin/env python3
"""
push_ingest_dual.py — dual-chamber predictive engine with a LIVE push seam (POST /ingest).

RECLAIM is a two-path recycler: a Plastics (pyrolysis) chamber and a Metals (smelt)
chamber, time-shared on one SSMG but with PHYSICALLY SEPARATE sensor suites. This
service runs the predictive estimator TWICE — one instance per chamber, each with its
own chamber_params — over two independent, chamber-tagged data streams. Same algorithm,
two configs, two streams in, two states out. The streams never collide:

    frame vars use PL_* and MT_* prefixes  ->  split by prefix
        PL_*  ->  plastics engine (chamber_params 'PL')  ->  PL_* published state
        MT_*  ->  metals   engine (chamber_params 'MT')  ->  MT_* published state

Endpoints (identical surface to push_ingest_service.py):
    POST /ingest   newline-delimited JSON frames whose `vars` carry PL_*/MT_* channels
    GET  /state    combined latest state: PL_* and MT_* estimates/forecasts/residuals
    GET  /manifest self-describing catalog (both chambers)
    GET  /history  last N combined frames
    GET  /health   liveness + counters

Run:  python push_ingest_dual.py --port 8078

LIVE INGEST CONTRACT (v1.1, fixes C1-C4/H1/H3 of the 2026-08 review):

  * PER-FRAME ACK. The /ingest response carries a `results` array, one entry per
    posted line, each `{"i", "status", "code", "final"}`:
        status  accepted | duplicate | rejected
        final   true  -> the gateway must NOT retry this frame (ack/dead-letter it)
                false -> transient (internal error); the gateway may retry
    The HTTP status is 200 whenever the request itself was processed; a mix of
    good and bad frames NEVER fails the batch. This removes the head-of-line
    deadlock in which one stale/poison frame blocked the queue forever.
  * STALE = REJECTED, FINAL. Frames older than --max-frame-age-s are refused and
    must be dropped by the gateway (dead-letter, counted). Freshness is a hard
    requirement: deprecated data never advances an estimator or reaches /state.
  * RUN SUPERSESSION. A valid, FRESH frame with a new run_id supersedes the
    active run (event RUN_SUPERSEDED); frames from retired runs are rejected
    final (run_superseded). A Pi reboot therefore recovers automatically, while
    stale leftovers from the old run cannot re-pin it (they fail freshness).
  * MONOTONE SEQUENCE PER (run_id, source_id). seq <= last_seq is a duplicate
    (final, never re-steps the engine); gaps are counted and evented (SEQ_GAP),
    never filled with fabricated samples. Run/seq state persists to
    --state-file (RECLAIM_INGEST_STATE) so a service restart cannot double-step.
  * REAL dt. Engine physics integrates the actual elapsed time between source
    timestamps, not an assumed 1 Hz.
  * NO FABRICATED MEASUREMENTS. A chamber with no valid temperature readings is
    NOT stepped; it publishes <CH>_sensor_valid=false (and SENSOR_MISSING when
    it is the active chamber) instead of a made-up 300 K.

Backward compatibility: if a frame carries UN-prefixed vars (legacy single-chamber
feed), they are routed to the plastics engine and published under PL_* — so old
emitters still work, just tagged. Gateways that predate `results` may treat any
2xx as batch-acked (previous behavior).

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hmac
import json
import logging
import math
import numbers
import os
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

import labview_map                          # real cRIO/LabVIEW -> canonical adapter
from reclaim_predictive_engine.config import EngineConfig, chamber_params
from reclaim_predictive_engine.engine import PredictiveEngine
from reclaim_predictive_engine.thread import StateStreamPublisher, default_manifest
from reclaim_predictive_engine.service import TwinStateService, _jsonable

log = logging.getLogger("reclaim.ingest")

# Plant-only observables that ride through to /state without entering the estimator.
_PASSTHROUGH = ("O2_pct", "mass_in_g", "mass_out_g", "T_bed_surf",
                "P_chamber", "P_downstream", "Q_vent", "Q_purge",
                "T_cond_top", "T_cond_bottom",
                "process", "preprocess", "postprocess",
                "chamber_pump", "purge_pump")

TELEMETRY_SCHEMA = "reclaim.telemetry.v1"
STATE_SCHEMA = "reclaim.state.v1"

# retained (run_id, source_id) sequence keys and retired-run memory, bounded
_MAX_SEQ_KEYS = 64
_MAX_RETIRED_RUNS = 256


class FrameRejected(ValueError):
    """A frame failed the live telemetry contract before reaching the estimator.

    `final` tells the gateway whether retrying can ever succeed. Every contract
    violation is final (retrying an old timestamp cannot make it fresh); only
    internal engine errors are retryable, and those are not FrameRejected.
    """

    def __init__(self, code: str, message: str, final: bool = True):
        super().__init__(message)
        self.code = code
        self.final = final


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value) -> datetime:
    if value in (None, ""):
        raise FrameRejected("timestamp_missing", "ts must be an ISO-8601 UTC timestamp")
    if not isinstance(value, str):
        raise FrameRejected("timestamp_invalid", "ts must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FrameRejected("timestamp_invalid", "ts must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise FrameRejected("timestamp_timezone", "ts must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _mean(vals):
    """Fault-tolerant mean of a sensor bank: drop None/NaN, average the rest."""
    xs = [float(x) for x in vals if x is not None and float(x) == float(x)]
    return sum(xs) / len(xs) if xs else None


def _bed_temp(v):
    """Bed temperature from whatever bank is present. Returns None when NO valid
    reading exists — never a fabricated default (fix C6)."""
    flat = [v[k] for k in v if k.startswith("T_bed_tc")]
    tcs = flat or v.get("T_bed_tcs")
    if isinstance(tcs, (list, tuple)) and tcs:
        m = _mean(tcs)
        if m is not None:
            return m
    for k in ("T_bed_meas", "T_bed_surf"):
        val = v.get(k)
        if val is not None and float(val) == float(val):
            return float(val)
    return None


def _wall_temp(v):
    """Wall temperature; None when no valid reading exists (fix C6)."""
    flat = [v[k] for k in v if k.startswith("T_wall_tc")]
    tcs = flat or v.get("T_wall_tcs")
    if isinstance(tcs, (list, tuple)) and tcs:
        m = _mean(tcs)
        if m is not None:
            return m
    val = v.get("T_wall_meas")
    if val is not None and float(val) == float(val):
        return float(val)
    return None


_SEV_RANK = {"NOMINAL": 0, "CAUTION": 1, "WARNING": 2, "CRITICAL": 3}
_MODE = {0: "TRACK", 1: "LIMIT", 2: "THROTTLE", 3: "SAFE_STATE"}
# power derating per advisory tier: NOMINAL track, CAUTION 80%, WARNING 50%, CRITICAL cut.
_DERATE = {0: 1.0, 1: 0.8, 2: 0.5, 3: 0.0}


def control_command(state: dict) -> dict:
    """Transparent control policy over the published state (the CD&H surrogate)."""
    gov = None  # (chamber, severity_rank, p_fwd)
    for ch in ("PL", "MT"):
        sev = state.get(f"{ch}_advisory_severity")
        if sev is None:
            continue
        r = _SEV_RANK.get(sev, 0)
        pf = float(state.get(f"{ch}_P_fwd", 0.0) or 0.0)
        cand = (ch, r, pf)
        if gov is None or r > gov[1] or (r == gov[1] and pf > gov[2]):
            gov = cand
    if gov is None:
        return {"chamber": None, "mode": "TRACK", "power_setpoint_W": 0.0,
                "safe_state_armed": False}
    ch, r, pf = gov
    return {"chamber": ch, "mode": _MODE[r],
            "power_setpoint_W": round(pf * _DERATE[r], 1),
            "safe_state_armed": r >= 3}


class IngestIdentityStore:
    """Run/sequence identity that survives a service restart (fixes C3+C4).

    Tracks the active run, retired runs, the last committed seq per
    (run_id, source_id), and the cumulative gap count. Persisted as a small
    JSON file written atomically after every committed frame, so an engine
    restart plus the gateway's at-least-once retry can never double-step the
    estimators. `path=None` keeps it in memory (dev / unit tests).
    """

    def __init__(self, path: str | None = None):
        self.path = path or None
        self.active_run_id: str | None = None
        self.retired: list[str] = []
        self.seqs: dict[str, int] = {}          # "run|source" -> last committed seq
        self.gap_count = 0
        self._load()

    def _load(self):
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path) as fh:
                d = json.load(fh)
            self.active_run_id = d.get("active_run_id")
            self.retired = list(d.get("retired", []))[-_MAX_RETIRED_RUNS:]
            self.seqs = {str(k): int(v) for k, v in dict(d.get("seqs", {})).items()}
            self.gap_count = int(d.get("gap_count", 0))
            log.info("ingest identity restored: run=%s seq_keys=%d gaps=%d",
                     self.active_run_id, len(self.seqs), self.gap_count)
        except Exception:
            log.exception("could not load ingest state from %s; starting clean", self.path)

    def save(self):
        if not self.path:
            return
        data = {"active_run_id": self.active_run_id,
                "retired": self.retired[-_MAX_RETIRED_RUNS:],
                "seqs": self.seqs, "gap_count": self.gap_count}
        d = os.path.dirname(os.path.abspath(self.path)) or "."
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".ingest_state.")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh)
            os.replace(tmp, self.path)          # atomic on POSIX
        except Exception:
            log.exception("could not persist ingest state to %s", self.path)
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def last_seq(self, run_id: str, source_id: str) -> int | None:
        return self.seqs.get(f"{run_id}|{source_id}")

    def commit(self, run_id: str, source_id: str, seq: int):
        self.seqs[f"{run_id}|{source_id}"] = seq
        if len(self.seqs) > _MAX_SEQ_KEYS:      # bound memory; oldest key first
            self.seqs.pop(next(iter(self.seqs)))
        self.save()

    def retire(self, run_id: str):
        if run_id and run_id not in self.retired:
            self.retired.append(run_id)
            self.retired = self.retired[-_MAX_RETIRED_RUNS:]


class ChamberEngine:
    """One predictive-engine instance bound to a single chamber's parameters."""

    def __init__(self, chamber_id: str, env: str):
        cfg = EngineConfig(physical=chamber_params(chamber_id), environment=env,
                           chamber_id=chamber_id)
        cfg.forecast.every = 1
        pub = StateStreamPublisher(default_manifest(), sink=lambda _m: None)
        self.eng = PredictiveEngine(cfg, publisher=pub, use_gp=False)
        self.chamber = chamber_id
        self.t = 0.0

    def step(self, v: dict, frame_op: str, dt: float, cycle_id=None):
        """Advance this chamber's estimator on its (un-prefixed) sub-vars.

        Returns (vals, events). When the chamber has no valid temperature
        measurements it is NOT stepped and no values are fabricated (fix C6):
        vals carries sensor_valid=False, the chamber-local op label, and the
        plant passthroughs only.
        """
        p_fwd = float(v.get("P_fwd", 0.0))
        p_refl = float(v.get("P_refl", 0.0))
        # physics is driven by power; a chamber with no forward power is idle/cooling,
        # so label its state accordingly for display regardless of the frame's op_state.
        op = frame_op if p_fwd > 0.0 else "S_Idle"

        zb, zw = _bed_temp(v), _wall_temp(v)
        if zb is None or zw is None:
            vals: dict = {"op_state": op, "sensor_valid": False,
                          "P_fwd": p_fwd, "P_refl": p_refl}
            for k in _PASSTHROUGH:
                if v.get(k) is not None:
                    vals[k] = float(v[k])
            return vals, []

        z = np.array([zb, zw])
        pch = v.get("P_chamber")
        # canonical unit is kPa (labview_map); SealMonitor works in Pa (fix C5).
        pch_pa = float(pch) * 1000.0 if pch is not None else None
        self.t += dt
        out = self.eng.step(self.t, z, p_fwd, p_refl, op_state=op,
                            p_chamber=pch_pa, dt=dt, system_op_state=frame_op,
                            cycle_id=cycle_id)
        vals = dict(out.frame.values)
        for k in _PASSTHROUGH:                      # plant-only observables ride through
            if v.get(k) is not None:
                vals[k] = float(v[k])
        vals["op_state"] = op
        vals["sensor_valid"] = True
        return vals, list(out.frame.events)


class DualPushEngine:
    """Two chamber engines fed by prefix-split frames; one combined published state."""

    def __init__(self, env: str = "earth_lab", *, production: bool = False,
                 max_frame_age_s: float = 15.0, state_file: str | None = None):
        self.svc = TwinStateService()
        self.pl = ChamberEngine("PL", env)
        self.mt = ChamberEngine("MT", env)
        self._lock = threading.Lock()
        self.count = 0
        self.t = 0.0
        self.production = production
        self.max_frame_age_s = max_frame_age_s
        self.ident = IngestIdentityStore(state_file)
        self._last_ts: datetime | None = None
        self.last_ingest = {"accepted": False, "duplicate": False,
                            "reason": "no frame received"}
        self._states = set(default_manifest().states)
        self.command = {"chamber": None, "mode": "TRACK", "power_setpoint_W": 0.0,
                        "safe_state_armed": False}
        self._set_manifest()

    @property
    def active_run_id(self):
        return self.ident.active_run_id

    def _set_manifest(self):
        base = json.loads(default_manifest().to_json())
        names = [x.get("name") for x in base.get("variables", [])] if isinstance(base, dict) else []
        names = [n for n in names if n] + ["sensor_valid"]
        provenance = ["schema_version", "mode", "run_id", "source_id", "seq", "ts_source",
                      "ts_engine", "cycle_id", "active_chamber", "source_op_state", "op_state",
                      "ingest_status", "ingest_age_ms", "last_event", "event_count",
                      "gap_count"]
        command = ["cmd_chamber", "cmd_mode", "cmd_power_setpoint_W", "cmd_safe_state_armed"]
        variables = ([{"name": "PL_" + n} for n in names]
                     + [{"name": "MT_" + n} for n in names]
                     + [{"name": n} for n in provenance + command])
        self.svc.set_manifest(json.dumps({
            "type": "manifest", "schema_version": STATE_SCHEMA,
            "model_ref": base.get("model_ref"), "chambers": ["PL", "MT"],
            "states": sorted(self._states | {"S_Unknown"}), "variables": variables,
        }))

    @staticmethod
    def _split(v: dict):
        """Split flat vars into (plastics, metals) sub-dicts by PL_/MT_ prefix.
        Un-prefixed keys default to plastics (legacy single-chamber compatibility)."""
        pl, mt = {}, {}
        for k, val in v.items():
            if k.startswith("PL_"):
                pl[k[3:]] = val
            elif k.startswith("MT_"):
                mt[k[3:]] = val
            else:
                pl[k] = val                          # legacy: treat bare vars as plastics
        return pl, mt

    def _validate_frame(self, frame: dict) -> dict:
        """Validate the envelope and return its normalized provenance values.

        Development accepts legacy frames so existing synthetic tools continue to
        work. Production requires the complete v1 contract and only accepts live
        telemetry; no invalid frame ever advances an estimator.
        """
        if not isinstance(frame, dict):
            raise FrameRejected("frame_invalid", "frame must be a JSON object")
        is_v1 = frame.get("schema_version") == TELEMETRY_SCHEMA
        if self.production and not is_v1:
            raise FrameRejected("schema_required", f"schema_version must be {TELEMETRY_SCHEMA}")
        if frame.get("schema_version") not in (None, TELEMETRY_SCHEMA):
            raise FrameRejected("schema_unsupported", "unsupported schema_version")

        mode = frame.get("mode", "legacy")
        if self.production and mode != "live":
            raise FrameRejected("mode_rejected", "production accepts mode=live only")
        if mode not in ("live", "harness", "replay", "legacy"):
            raise FrameRejected("mode_invalid", "mode must be live, harness, replay, or legacy")

        required = ("run_id", "source_id", "seq", "ts", "cycle_id", "source_op_state",
                    "active_chamber", "vars")
        if self.production:
            missing = [k for k in required if frame.get(k) in (None, "")]
            if missing:
                raise FrameRejected("envelope_missing", "missing required fields: " + ", ".join(missing))

        ts = _parse_timestamp(frame["ts"]) if frame.get("ts") else _utc_now()
        age_s = (_utc_now() - ts).total_seconds()
        if self.production and (age_s < -5.0 or age_s > self.max_frame_age_s):
            # FINAL by design: deprecated data must never reach the estimator,
            # and retrying cannot make an old timestamp fresh (fix C1).
            raise FrameRejected("timestamp_stale",
                                f"frame age {age_s:.3f}s outside allowed window")

        op = frame.get("source_op_state", frame.get("op_state"))
        if op is None:
            op = "S_Unknown"
        if op not in self._states and op != "S_Unknown":
            raise FrameRejected("state_invalid", f"unknown source_op_state: {op}")

        active = frame.get("active_chamber", frame.get("active", frame.get("chamber")))
        if active is None and not self.production:
            active = "NONE"
        if active not in ("PL", "MT", "NONE"):
            raise FrameRejected("chamber_invalid", "active_chamber must be PL, MT, or NONE")

        seq = frame.get("seq", self.count + 1)
        if isinstance(seq, bool) or not isinstance(seq, numbers.Integral):
            raise FrameRejected("sequence_invalid", "seq must be an integer")
        seq = int(seq)
        if seq < 0:
            raise FrameRejected("sequence_invalid", "seq must be non-negative")
        run_id = str(frame.get("run_id", "legacy"))
        source_id = str(frame.get("source_id", frame.get("src", "legacy")))
        return {"mode": mode, "run_id": run_id, "source_id": source_id, "seq": seq,
                "ts": ts, "cycle_id": str(frame.get("cycle_id", "")),
                "source_op_state": op, "active_chamber": active,
                "age_ms": max(0, round(age_s * 1000))}

    @staticmethod
    def _require_finite_number(value, field: str) -> float:
        """Return a finite numeric scalar without accepting JSON coercions.

        Physical ranges deliberately do not live here: this is the inference-safe
        structural boundary only.
        """
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise FrameRejected("telemetry_invalid", f"{field} must be a numeric scalar")
        number = float(value)
        if not math.isfinite(number):
            raise FrameRejected("telemetry_invalid", f"{field} must be finite")
        return number

    def _validate_raw_telemetry(self, raw: dict) -> None:
        if not isinstance(raw, dict):
            raise FrameRejected("telemetry_invalid", "vars must be an object")

        if labview_map.looks_like_labview(raw):
            numeric = {
                *labview_map._PL_BED, *labview_map._MT_BED,
                "PL_surface_temp", "PL_top_condenser_temp",
                "PL_bottom_condenser_temp", "PL_chamber_pressure",
                "PL_output_pressure", "MT_top", "MW_power", "MW_reverse",
                "MW_freq", "MW_width", "MW_period", "MW_water_temp",
                "MW_flow_rate",
            }
            boolean = {*labview_map._PL_FLAGS, "MW_water_state", "MW_flow_state",
                       "MW_RF", "MW_status"}
            for key in numeric & raw.keys():
                self._require_finite_number(raw[key], key)
            for key in boolean & raw.keys():
                if not isinstance(raw[key], bool):
                    raise FrameRejected("telemetry_invalid", f"{key} must be boolean")
            return

        # Canonical chamber telemetry. Flat PL bed banks have four sensors and
        # flat MT banks have one in the approved inference contract. A list bank
        # remains supported for legacy development input, but every member must
        # still be a finite scalar.
        for chamber, expected in (("PL", 4), ("MT", 1)):
            prefix = f"{chamber}_T_bed_tc"
            bank = sorted(k for k in raw if k.startswith(prefix))
            if bank and bank != [f"{prefix}{i}" for i in range(1, expected + 1)]:
                raise FrameRejected(
                    "telemetry_invalid",
                    f"{chamber} bed sensor bank must contain {expected} channels",
                )

        boolean_suffixes = {
            "process", "preprocess", "postprocess", "chamber_pump", "purge_pump"
        }
        for key, value in raw.items():
            bare = key[3:] if key.startswith(("PL_", "MT_")) else key
            if bare in boolean_suffixes:
                if not isinstance(value, bool):
                    raise FrameRejected("telemetry_invalid", f"{key} must be boolean")
                continue
            if bare in ("T_bed_tcs", "T_wall_tcs"):
                if not isinstance(value, (list, tuple)) or not value:
                    raise FrameRejected("telemetry_invalid", f"{key} must be a sensor bank")
                for index, item in enumerate(value):
                    self._require_finite_number(item, f"{key}[{index}]")
                continue
            # These are the values consumed by ChamberEngine or converted to
            # scalar pass-through state. Unknown raw fields remain preserved but
            # do not enter the model and therefore are not assigned invented rules.
            if (bare.startswith(("T_bed_tc", "T_wall_tc"))
                    or bare in {"T_bed_meas", "T_bed_surf", "T_wall_meas",
                                "P_fwd", "P_refl", *_PASSTHROUGH}):
                self._require_finite_number(value, key)

    def _prepare_telemetry(self, frame: dict, meta: dict) -> dict:
        """Validate the full consumed payload, then normalize it once.

        No adapter, model, clock, counter, output, command, or identity mutation
        occurs before this function returns.
        """
        raw_value = frame.get("vars", frame)
        if not isinstance(raw_value, dict):
            raise FrameRejected("telemetry_invalid", "vars must be an object")
        raw = dict(raw_value)
        raw["active"] = meta["active_chamber"]
        self._validate_raw_telemetry(raw)
        is_lv = labview_map.looks_like_labview(raw)
        values, mw_globals, active = labview_map.normalize(raw)
        # Validate normalized values as a second boundary. This protects future
        # adapter changes from introducing a prohibited model input.
        self._validate_raw_telemetry(values)
        for key, value in mw_globals.items():
            if isinstance(value, bool):
                continue
            self._require_finite_number(value, key)
        return {"raw": raw, "values": values, "mw_globals": mw_globals,
                "active": active, "is_labview": is_lv}

    @staticmethod
    def _clone_service(service: TwinStateService) -> TwinStateService:
        with service._lock:
            candidate = TwinStateService(history=service._history.maxlen)
            candidate._manifest = copy.deepcopy(service._manifest)
            candidate._latest = copy.deepcopy(service._latest)
            candidate._history.extend(copy.deepcopy(list(service._history)))
            candidate.cycle = service.cycle
        return candidate

    def _candidate(self):
        candidate = copy.copy(self)
        candidate.pl = copy.deepcopy(self.pl)
        candidate.mt = copy.deepcopy(self.mt)
        candidate.svc = self._clone_service(self.svc)
        candidate.ident = copy.deepcopy(self.ident)
        candidate.command = copy.deepcopy(self.command)
        candidate._last_ts = self._last_ts
        return candidate

    def _publish_candidate(self, candidate) -> None:
        """Deterministic, non-throwing post-durability in-memory commit."""
        self.pl = candidate.pl
        self.mt = candidate.mt
        self.svc = candidate.svc
        self.ident = candidate.ident
        self.count = candidate.count
        self.t = candidate.t
        self._last_ts = candidate._last_ts
        self.command = candidate.command

    # ------------------------------------------------------------------ ingest
    def ingest_line(self, frame: dict) -> dict:
        """Process one frame; return its disposition (never raises FrameRejected).

        Disposition: {"status": accepted|duplicate|rejected, "code", "message",
                      "final", "run_id", "seq"}. `final` follows the v1.1 ack
        contract: the gateway must not retry final frames. All identity
        decisions and estimator stepping happen under ONE lock (fix M2).
        """
        try:
            meta = self._validate_frame(frame)
            prepared = self._prepare_telemetry(frame, meta)
        except FrameRejected as exc:
            self.last_ingest = {"accepted": False, "duplicate": False,
                                "reason": exc.code}
            return {"status": "rejected", "code": exc.code, "message": str(exc),
                    "final": exc.final, "run_id": frame.get("run_id") if isinstance(frame, dict) else None,
                    "seq": frame.get("seq") if isinstance(frame, dict) else None}

        run_id, source_id, seq = meta["run_id"], meta["source_id"], meta["seq"]
        with self._lock:
            events_extra: list[tuple[str, str]] = []

            # ---- run identity (fix C2): supersede, never wedge -------------
            superseded_from = None
            if self.ident.active_run_id is None:
                pass                                        # adopted on commit
            elif run_id != self.ident.active_run_id:
                if run_id in self.ident.retired:
                    self.last_ingest = {"accepted": False, "duplicate": False,
                                        "reason": "run_superseded", **meta}
                    return {"status": "rejected", "code": "run_superseded",
                            "message": "run_id was superseded by a newer run",
                            "final": True, "run_id": run_id, "seq": seq}
                if self.production:
                    # Fresh + fully validated (staleness already enforced), so
                    # this is a legitimate new run (e.g. gateway restart).
                    superseded_from = self.ident.active_run_id
                    log.warning("run supersession: %s -> %s", superseded_from, run_id)
                    events_extra.append(("SYS", f"RUN_SUPERSEDED:{superseded_from}"))

            # ---- monotone sequence (fix C3) --------------------------------
            last = self.ident.last_seq(run_id, source_id)
            gap = 0
            if last is not None:
                if seq <= last:
                    if self.production or seq == last:
                        self.last_ingest = {"accepted": True, "duplicate": True, **meta}
                        return {"status": "duplicate", "code": None,
                                "message": f"seq {seq} <= last committed {last}",
                                "final": True, "run_id": run_id, "seq": seq}
                    # dev convenience: a restarted synthetic tool resets its stream
                    log.info("dev seq reset for %s|%s: %d -> %d", run_id, source_id, last, seq)
                elif seq > last + 1:
                    gap = seq - last - 1

            # ---- isolated accepted-frame candidate ------------------------
            try:
                candidate = self._candidate()

                # Instance-level fault hooks are used by the integrity tests and
                # by local fault campaigns. Temporarily exposing only the detached
                # chamber candidates lets such hooks inspect the candidate graph;
                # production instances use class methods and never take this path.
                hooked = "step" in vars(self.pl) or "step" in vars(self.mt)
                live_pl, live_mt = self.pl, self.mt
                if hooked:
                    self.pl, self.mt = candidate.pl, candidate.mt
                try:
                    combined = candidate._step_locked(prepared, meta, gap, events_extra)
                finally:
                    if hooked:
                        self.pl, self.mt = live_pl, live_mt

                # Identity belongs to the same candidate. Durable persistence is
                # the commit point; no live object reference has changed yet.
                if superseded_from is not None:
                    candidate.ident.retire(superseded_from)
                    candidate.ident.seqs = {
                        k: v for k, v in candidate.ident.seqs.items()
                        if not k.startswith(superseded_from + "|")
                    }
                if candidate.ident.active_run_id is None or superseded_from is not None:
                    candidate.ident.active_run_id = run_id
                if gap:
                    candidate.ident.gap_count += gap
                    log.warning("sequence gap: %d frame(s) missing before %s|%s seq %d",
                                gap, run_id, source_id, seq)
                candidate.ident.commit(run_id, source_id, seq)
            except Exception as exc:
                # Retryable: identity NOT committed, so the gateway's retry will
                # re-step cleanly (fix M3 — the frame is not silently lost).
                log.error("engine step failed for %s|%s seq %d: %s\n%s",
                          run_id, source_id, seq, exc, traceback.format_exc())
                self.last_ingest = {"accepted": False, "duplicate": False,
                                    "reason": "internal_error", **meta}
                return {"status": "rejected", "code": "internal_error",
                        "message": f"{type(exc).__name__}: {exc}", "final": False,
                        "run_id": run_id, "seq": seq}

            # Persistence succeeded. The remaining commit is a fixed sequence of
            # plain assignments and cannot call model, publisher, or filesystem code.
            self._publish_candidate(candidate)
            self.last_ingest = {"accepted": True, "duplicate": False, **meta}
            return {"status": "accepted", "code": None, "message": "",
                    "final": True, "run_id": run_id, "seq": seq,
                    "state": combined}

    def _step_locked(self, prepared: dict, meta: dict, gap: int,
                     events_extra: list[tuple[str, str]]) -> dict:
        """Both chamber candidates + combined record. Caller holds _lock."""
        op = meta["source_op_state"]
        raw = prepared["raw"]
        v = prepared["values"]
        mw_globals = prepared["mw_globals"]
        active = prepared["active"]
        is_lv = prepared["is_labview"]

        # real dt from source timestamps (fix H1); clamped so a first frame or a
        # timestamp hiccup cannot inject a huge or non-positive integration step.
        if self._last_ts is not None:
            dt = (meta["ts"] - self._last_ts).total_seconds()
            dt = min(max(dt, 0.05), 10.0) if dt > 0.0 else 0.05
        else:
            dt = 1.0
        self._last_ts = meta["ts"]

        pl_v, mt_v = self._split(v)
        self.count += 1
        self.t += dt
        combined, events = {}, []
        cid = meta["cycle_id"]
        if pl_v:
            vals, ev = self.pl.step(pl_v, op, dt, cycle_id=cid)
            combined.update({"PL_" + k: val for k, val in vals.items()})
            events += [("PL", e) for e in ev]
            if vals.get("sensor_valid") is False and meta["active_chamber"] == "PL":
                events.append(("PL", "SENSOR_MISSING"))
        if mt_v:
            vals, ev = self.mt.step(mt_v, op, dt, cycle_id=cid)
            combined.update({"MT_" + k: val for k, val in vals.items()})
            events += [("MT", e) for e in ev]
            if vals.get("sensor_valid") is False and meta["active_chamber"] == "MT":
                events.append(("MT", "SENSOR_MISSING"))

        # plausibility cross-check (diagnostic, never an override — fix C7):
        # what the sensors imply vs what the sequencer declared.
        if is_lv:
            inferred = labview_map.inferred_chamber(raw)
            declared = meta["active_chamber"]
            if inferred is not None and inferred != (declared if declared != "NONE" else None):
                events.append(("SYS", f"CHAMBER_MISMATCH:declared={declared},inferred={inferred}"))

        events = events_extra + events
        if gap:
            events.append(("SYS", f"SEQ_GAP:{gap}"))

        combined.update(mw_globals)                 # shared SSMG diagnostics -> /state
        combined["schema_version"] = STATE_SCHEMA
        combined["mode"] = meta["mode"]
        combined["run_id"] = meta["run_id"]
        combined["source_id"] = meta["source_id"]
        combined["seq"] = meta["seq"]
        combined["ts_source"] = meta["ts"].isoformat().replace("+00:00", "Z")
        combined["ts_engine"] = _utc_now().isoformat().replace("+00:00", "Z")
        combined["cycle_id"] = meta["cycle_id"]
        # sequencer authoritative in production; inference is dev fallback only.
        combined["active_chamber"] = (meta["active_chamber"] if self.production
                                      else (meta["active_chamber"]
                                            if meta["active_chamber"] != "NONE"
                                            else (active or "NONE")))
        combined["source_op_state"] = meta["source_op_state"]
        combined["op_state"] = meta["source_op_state"]
        combined["ingest_status"] = "accepted"
        combined["ingest_age_ms"] = meta["age_ms"]
        combined["gap_count"] = self.ident.gap_count + gap
        combined["event_count"] = len(events)
        combined["last_event"] = ";".join(f"{ch}:{event}" for ch, event in events) or "NONE"
        self.command = control_command(combined)
        combined["cmd_chamber"] = self.command["chamber"]
        combined["cmd_mode"] = self.command["mode"]
        combined["cmd_power_setpoint_W"] = self.command["power_setpoint_W"]
        combined["cmd_safe_state_armed"] = self.command["safe_state_armed"]
        self.svc.update(combined, self.t, events, self.count)
        return combined

    def ingest(self, frame: dict):
        """Compatibility API (tests/dev tools): returns the combined state for an
        accepted frame, the current state for a duplicate, and raises
        FrameRejected otherwise."""
        d = self.ingest_line(frame)
        if d["status"] == "accepted":
            return d["state"]
        if d["status"] == "duplicate":
            return self.svc.state()
        raise FrameRejected(d["code"], d["message"], final=d.get("final", True))


def _bearer_ok(headers, token: str) -> bool:
    if not token:
        return True
    supplied = headers.get("Authorization", "")
    return hmac.compare_digest(supplied, f"Bearer {token}")


def _make_handler(pe: DualPushEngine, ingest_token: str = "", read_token: str = ""):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, obj, code=200):
            body = json.dumps(_jsonable(obj)).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            path = self.path.split("?")[0].rstrip("/")
            if path != "/ingest":
                return self._send({"error": "not found", "post": ["/ingest"]}, 404)
            if not _bearer_ok(self.headers, ingest_token):
                return self._send({"error": "unauthorized"}, 401)
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n).decode("utf-8", "replace") if n else ""
            ingested = duplicate = rejected = 0
            results, errors = [], []
            i = -1
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                i += 1
                try:
                    obj = json.loads(line)
                except ValueError as exc:
                    d = {"status": "rejected", "code": "json_invalid",
                         "message": str(exc), "final": True}
                except Exception as exc:  # pragma: no cover - defensive
                    d = {"status": "rejected", "code": "json_invalid",
                         "message": str(exc), "final": True}
                else:
                    try:
                        d = pe.ingest_line(obj)
                    except Exception as exc:  # pragma: no cover - defensive
                        log.error("unhandled ingest error: %s\n%s", exc,
                                  traceback.format_exc())
                        d = {"status": "rejected", "code": "internal_error",
                             "message": str(exc), "final": False}
                if d["status"] == "accepted":
                    ingested += 1
                elif d["status"] == "duplicate":
                    duplicate += 1
                else:
                    rejected += 1
                    errors.append({"code": d.get("code"), "message": d.get("message")})
                results.append({"i": i, "status": d["status"], "code": d.get("code"),
                                "final": bool(d.get("final", True))})
            # v1.1 contract: the request was processed -> 200, with per-frame
            # results. A bad frame never fails its batch-mates (fix C1/H3).
            # `bad`/`errors` retained for pre-1.1 clients.
            self._send({"ingested": ingested, "duplicate": duplicate,
                        "rejected": rejected, "bad": rejected,
                        "results": results, "errors": errors[:5],
                        "total": pe.count, "command": pe.command}, 200)

        def do_GET(self):
            path = self.path.split("?")[0].rstrip("/")
            if path not in ("", "/health") and not _bearer_ok(self.headers, read_token):
                return self._send({"error": "unauthorized"}, 401)
            if path in ("", "/health"):
                self._send({"ok": True, "service": "reclaim-push-ingest-dual",
                            "ingested_total": pe.count, "chambers": ["PL", "MT"],
                            "mode": "production" if pe.production else "development",
                            "active_run_id": pe.active_run_id,
                            "gap_count": pe.ident.gap_count})
            elif path == "/manifest":
                self._send(pe.svc.manifest())
            elif path == "/state":
                obj = pe.svc.state()
                # freshness at read time: lets every consumer (Convene publisher
                # and its .stp visualization) gate DATA NOT LIVE without trusting
                # a stored age.
                ts_e = obj.get("ts_engine")
                if isinstance(ts_e, str):
                    try:
                        age = (_utc_now() - _parse_timestamp(ts_e)).total_seconds()
                        obj["state_age_ms"] = max(0, round(age * 1000))
                    except FrameRejected:
                        pass
                self._send(obj)
            elif path == "/command":
                self._send(pe.command)          # latest ControlCommand for the cRIO
            elif path == "/history":
                self._send({"frames": pe.svc.history(200)})
            else:
                self._send({"error": "not found",
                            "endpoints": ["POST /ingest", "/state", "/manifest",
                                          "/history", "/health"]}, 404)

        def log_message(self, *a):
            return
    return Handler


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="RECLAIM dual-chamber engine — POST /ingest")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8078)
    ap.add_argument("--env", default="earth_lab")
    ap.add_argument("--production", action="store_true",
                    help="require authenticated, complete mode=live telemetry envelopes")
    ap.add_argument("--ingest-token", default=os.environ.get("RECLAIM_INGEST_TOKEN", ""),
                    help="Bearer token for POST /ingest (prefer RECLAIM_INGEST_TOKEN env; "
                         "a CLI value is visible in the process list)")
    ap.add_argument("--read-token", default=os.environ.get("RECLAIM_READ_TOKEN", ""),
                    help="optional Bearer token for GET /state,/manifest,/history,/command "
                         "(RECLAIM_READ_TOKEN env). /health stays open for probes.")
    ap.add_argument("--state-file",
                    default=os.environ.get("RECLAIM_INGEST_STATE", ""),
                    help="path for persisted run/seq identity (RECLAIM_INGEST_STATE). "
                         "Required in --production so a restart cannot double-step.")
    ap.add_argument("--max-frame-age-s", type=float, default=15.0)
    args = ap.parse_args()

    if args.production and not args.ingest_token:
        ap.error("--production requires RECLAIM_INGEST_TOKEN (env) or --ingest-token")
    if args.production and not args.state_file:
        ap.error("--production requires RECLAIM_INGEST_STATE (env) or --state-file "
                 "so dedup/run identity survives a restart")
    pe = DualPushEngine(env=args.env, production=args.production,
                        max_frame_age_s=args.max_frame_age_s,
                        state_file=args.state_file or None)
    server = ThreadingHTTPServer((args.host, args.port),
                                 _make_handler(pe, args.ingest_token, args.read_token))
    print(f"[reclaim-dual] serving on http://{args.host}:{args.port}")
    print("[reclaim-dual] two chambers (PL + MT)  ·  POST /ingest  ·  GET /state /manifest /history /health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
