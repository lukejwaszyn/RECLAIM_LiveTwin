"""RECLAIM Edge Gateway — framer.

Builds the canonical wire frame and validates it against the manifest field set.
The validation is the enforcement point for naming convergence: any key the cRIO
sends that is not a manifest field, or any manifest field missing, is flagged here
so drift is caught at the edge rather than silently binding to nothing downstream.

Canonical frame:
    {"schema_version", "mode", "run_id", "source_id", "cycle_id", "seq",
     "ts", "source_op_state", "active_chamber", "vars": {...}}

Author: LJW.
"""
from __future__ import annotations

import itertools
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from .config import Config


class FrameContractError(ValueError):
    """An inbound source line does not satisfy the telemetry wire contract."""


_ENVELOPE_FIELDS = {
    "schema_version", "mode", "run_id", "source_id", "src", "cycle_id",
    "seq", "ts", "source_op_state", "op_state", "active_chamber", "active",
    "chamber",
}


def _reject_json_constant(value: str) -> None:
    """Reject JavaScript constants that Python's JSON decoder accepts by default."""
    raise FrameContractError(f"non-finite JSON number '{value}' is not allowed")


def _validate_variables(variables: Any, *, flat: bool = False) -> None:
    if not isinstance(variables, dict):
        raise FrameContractError("'vars' must be a JSON object")

    for name, value in variables.items():
        if flat and name in _ENVELOPE_FIELDS:
            continue
        if not isinstance(name, str) or not name:
            raise FrameContractError("variable names must be non-empty strings")
        if name in _ENVELOPE_FIELDS:
            raise FrameContractError(f"variable name '{name}' is reserved for the envelope")
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            continue
        if isinstance(value, float) and math.isfinite(value):
            continue
        raise FrameContractError(
            f"variable '{name}' must be a finite JSON number or boolean scalar"
        )


class Framer:
    def __init__(self, cfg: Config, seq_store=None):
        """`seq_store` (optional, duck-typed: get_meta/set_meta) persists the
        sequence high-water mark per run_id — required when `run_id` is pinned
        in config so a gateway restart resumes AFTER the last emitted seq
        instead of colliding with already-delivered numbers (review fix M7).
        With a generated run_id the seq space is fresh anyway."""
        self.cfg = cfg
        self._allowed = set(cfg.fields)
        self._warned_fields: set = set()   # warn once per unknown field (fix M5)
        # A run identity belongs to the gateway session, not to an individual cRIO line.
        self.run_id = cfg.run_id or str(uuid.uuid4())
        self._seq_store = seq_store
        start = 1
        if cfg.run_id and seq_store is not None:
            prev = seq_store.get_meta(f"seq:{self.run_id}")
            if prev is not None:
                start = int(prev) + 1
        self._seq = itertools.count(start)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def build(self, raw: Dict) -> Tuple[Dict, list]:
        """Return (canonical_frame, warnings).

        `raw` is the normalized dict parsed from the cRIO line. It may carry its own
        `ts`/`cycle_id`; if so we keep them (timing measured at the source).
        """
        if not isinstance(raw, dict):
            raise FrameContractError("top-level telemetry value must be a JSON object")

        warnings = []
        structured = "vars" in raw
        incoming = raw["vars"] if structured else raw
        # Direct callers retain the legacy flat-dict API. Network input is stricter:
        # parse_line() requires an explicit vars object before build() is reached.
        _validate_variables(incoming, flat=not structured)

        vars_out: Dict[str, Any] = {}
        for k, v in incoming.items():
            if k in _ENVELOPE_FIELDS:
                continue
            if k not in self._allowed:
                if self.cfg.strict_fields:
                    warnings.append(f"unknown field '{k}' (not in manifest) — dropped")
                    continue
                # The real LabVIEW schema is normalized by labview_map in the cloud.
                # Preserve it here so booleans and raw channel names are not destroyed.
                # Warn ONCE per field name, not per frame — at telemetry rate the
                # old per-frame warning flooded the journal/SD card (fix M5).
                if k not in self._warned_fields:
                    self._warned_fields.add(k)
                    warnings.append(f"unknown field '{k}' preserved for cloud normalization"
                                    " (logged once)")
            vars_out[k] = v

        missing = self._allowed - vars_out.keys()
        if missing and self.cfg.strict_fields:
            warnings.append(f"missing manifest fields: {sorted(missing)}")

        source_op_state = raw.get("source_op_state", raw.get("op_state"))
        active_chamber = raw.get("active_chamber", raw.get("active", raw.get("chamber")))
        frame = {
            "schema_version": self.cfg.schema_version,
            "mode": self.cfg.mode,
            "run_id": self.run_id,
            "source_id": raw.get("source_id", raw.get("src", self.cfg.src)),
            "cycle_id": raw.get("cycle_id", ""),
            "seq": next(self._seq),
            "ts": raw.get("ts") or self._now_iso(),
            "source_op_state": source_op_state,
            "active_chamber": active_chamber,
            "vars": vars_out,
        }
        return frame, warnings

    @staticmethod
    def dumps(frame: Dict) -> str:
        return json.dumps(frame, separators=(",", ":"), allow_nan=False)


def parse_line(line: str) -> Dict:
    """Parse and validate one inbound structured telemetry JSON object."""
    line = line.strip()
    if not line:
        return {}
    try:
        raw = json.loads(line, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        raise FrameContractError(f"invalid telemetry JSON: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise FrameContractError("top-level telemetry value must be a JSON object")
    if "vars" not in raw:
        raise FrameContractError("top-level telemetry object must contain a 'vars' object")
    _validate_variables(raw["vars"])
    return raw
