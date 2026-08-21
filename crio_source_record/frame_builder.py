"""crio_source_record/frame_builder.py — build the source telemetry frame.

Produces exactly ONE UTF-8 JSON object followed by ONE ``\\n``, per the source-frame
contract in section 4 of ``deployment/CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md``::

    {"source_id", "ts", "cycle_id", "source_op_state", "active_chamber", "vars": {...}}

This is the frame the (future, Gate-3-authorized) RT-side producer would branch off
its existing per-record snapshot. This module is offline and side-effect free: it
never opens a socket, and it NEVER invents authoritative metadata. ``source_id``,
``ts``, ``cycle_id``, ``source_op_state`` and ``active_chamber`` must all be supplied
from the sequencer/clock; a missing or empty one is an error, not a default.

Frame invariants enforced here:

* ``ts`` is an ISO-8601 timestamp carrying a UTC offset;
* ``active_chamber`` is the explicit physical value ``PL`` / ``MT`` / ``NONE`` — never
  inferred from RF or process flags;
* every ``vars`` value is a finite JSON number or a JSON boolean (no containers, no
  ``NaN``/``Infinity`` — invalid or quarantined channels are simply absent);
* the serialized line (including its LF) stays within the gateway's 8192-byte bound.

Measured serialized line sizes over the retained fixtures (bytes, incl. LF):
minimum 203, nominal 911, maximum 1319 — all comfortably under the bound.

Author: RECLAIM repository developer (Gate 2, offline).
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Mapping

__all__ = [
    "FrameBuildError",
    "MAX_LINE_BYTES",
    "VALID_CHAMBERS",
    "MEASURED_MIN_BYTES",
    "MEASURED_NOMINAL_BYTES",
    "MEASURED_MAX_BYTES",
    "build_frame",
]


class FrameBuildError(ValueError):
    """The requested frame violates the source-frame contract."""


MAX_LINE_BYTES = 8192            # == pi_gateway Config.max_line_bytes (receiver bound)
VALID_CHAMBERS = ("PL", "MT", "NONE")

# Documented measurements over the sanitized fixtures (see module docstring).
MEASURED_MIN_BYTES = 203
MEASURED_NOMINAL_BYTES = 911
MEASURED_MAX_BYTES = 1319

# Envelope keys the gateway framer owns; a var may not shadow them.
_RESERVED = frozenset({
    "schema_version", "mode", "run_id", "source_id", "src", "cycle_id", "seq",
    "ts", "source_op_state", "op_state", "active_chamber", "active", "chamber",
    "vars",
})


def _require_nonempty_str(value, field: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise FrameBuildError(f"{field} must be a non-empty authoritative string")
    return value


def _require_utc_iso(ts) -> str:
    if not isinstance(ts, str) or ts.strip() == "":
        raise FrameBuildError("ts must be a non-empty ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FrameBuildError(f"ts is not ISO-8601: {ts!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(None):
        raise FrameBuildError("ts must carry a UTC (+00:00 / Z) offset")
    return ts


def _clean_vars(variables: Mapping[str, object]) -> dict:
    if not isinstance(variables, Mapping):
        raise FrameBuildError("vars must be a mapping")
    out: dict = {}
    for name, value in variables.items():
        if not isinstance(name, str) or name == "":
            raise FrameBuildError("variable names must be non-empty strings")
        if name in _RESERVED:
            raise FrameBuildError(f"variable name {name!r} collides with the envelope")
        if isinstance(value, bool):
            out[name] = value
            continue
        if isinstance(value, int):  # JSON-safe integral scalar
            out[name] = value
            continue
        if isinstance(value, float):
            if not math.isfinite(value):
                raise FrameBuildError(f"variable {name!r} is non-finite")
            out[name] = value
            continue
        raise FrameBuildError(
            f"variable {name!r} must be a finite number or boolean, got {type(value).__name__}"
        )
    return out


def build_frame(
    variables: Mapping[str, object],
    *,
    source_id: str,
    ts: str,
    cycle_id: str,
    source_op_state: str,
    active_chamber: str,
    max_line_bytes: int = MAX_LINE_BYTES,
) -> bytes:
    """Return one JSON object + LF as UTF-8 bytes. Raises on any contract breach.

    All five metadata arguments are authoritative and mandatory; none is defaulted.
    ``active_chamber`` must be an explicit member of :data:`VALID_CHAMBERS`.
    """
    source_id = _require_nonempty_str(source_id, "source_id")
    cycle_id = _require_nonempty_str(cycle_id, "cycle_id")
    source_op_state = _require_nonempty_str(source_op_state, "source_op_state")
    ts = _require_utc_iso(ts)
    if active_chamber not in VALID_CHAMBERS:
        raise FrameBuildError(
            f"active_chamber must be explicit {VALID_CHAMBERS}, got {active_chamber!r}"
        )

    frame = {
        "source_id": source_id,
        "ts": ts,
        "cycle_id": cycle_id,
        "source_op_state": source_op_state,
        "active_chamber": active_chamber,
        "vars": _clean_vars(variables),
    }
    line = json.dumps(frame, separators=(",", ":"), allow_nan=False) + "\n"
    encoded = line.encode("utf-8")
    if len(encoded) > max_line_bytes:
        raise FrameBuildError(
            f"serialized frame {len(encoded)} B exceeds the {max_line_bytes} B bound"
        )
    return encoded
