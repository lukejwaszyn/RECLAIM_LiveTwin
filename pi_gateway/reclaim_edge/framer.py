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
import uuid
from datetime import datetime, timezone
from typing import Dict, Iterable, Tuple

from .config import Config


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
        # A run identity belongs to the Pi session, not to an individual cRIO line.
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
        warnings = []
        incoming = raw.get("vars", raw)  # accept either {vars:{...}} or a flat dict

        vars_out: Dict[str, float] = {}
        for k, v in incoming.items():
            if k in ("schema_version", "mode", "run_id", "source_id", "src",
                     "cycle_id", "seq", "ts", "source_op_state", "op_state",
                     "active_chamber", "active", "chamber"):
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
        return json.dumps(frame, separators=(",", ":"))


def parse_line(line: str) -> Dict:
    """Parse an inbound cRIO line. JSON preferred; CSV 'k=v,k=v' tolerated."""
    line = line.strip()
    if not line:
        return {}
    if line[0] in "{[":
        return json.loads(line)
    out: Dict = {}
    for tok in line.split(","):
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k.strip()] = v.strip()
    return out
