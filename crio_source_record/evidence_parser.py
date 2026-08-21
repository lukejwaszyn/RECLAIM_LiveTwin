"""crio_source_record/evidence_parser.py — strict, fail-closed parser for the
legacy cRIO USB process record (``Data Stream.vi`` -> ``*_data_stream.txt``).

EVIDENCE INPUT ONLY. The retained USB ``name: value`` text record is a schema and
correlation fixture, never the production wire contract. The production contract is
one UTF-8 JSON object + LF (see :mod:`crio_source_record.frame_builder` and section 4
of ``deployment/CRIO_ACQUISITION_PATH_FORWARD_HANDOFF.md``). This parser exists so the
retained captures can be sanitized, replayed, and regression-tested offline without
ever binding the fragile positional text syntax into the live path.

Fail-closed contract — a record that violates ANY rule is rejected whole, never
partially kept:

* every line must use the exact ``": "`` (colon-space) delimiter — the delimiter
  defects observed in the earliest 30-field captures (``MT_crucible_temperature`` and
  ``MW_reverse_coupler``) are therefore rejected by design;
* no duplicate field name within a record;
* numeric fields must parse to a FINITE float — ``inf``/``nan``/overflow rejected;
  exact ``0``/``0.0`` remains a valid measurement;
* boolean fields must be exactly ``TRUE`` / ``FALSE`` (LabVIEW text booleans);
* every field name must belong to the record's schema (unknown field rejected);
* the record's field SET and ORDER must match a recognized schema; an unrecognized
  or partial schema is rejected.

Schema authority:

* :data:`FIELDS_34` — the evidence-backed 34-field order from PATH_FORWARD section
  2.3. AUTHORITATIVE.
* :data:`FIELDS_32`, :data:`FIELDS_30` — UNCONFIRMED reconstructions. The captures
  proved the record grew 30 -> 32 -> 34, but WHICH fields were added at each step is
  not established by committed evidence. These reconstructions assume the trailing
  probe pair and the wall pair were the later additions; controls must confirm this
  against the retained intermediate captures before either is trusted.

A value may be marked invalid ONLY by a :class:`QualityProfile`. Until controls signs
a profile, the sole default action is the conservative quarantine of
``PL_bottom2`` (the persistent ~1383 reading whose physical meaning is unproven).

Author: RECLAIM repository developer (Gate 2, offline).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Sequence, Tuple

__all__ = [
    "EvidenceParseError",
    "FIELDS_34",
    "FIELDS_32",
    "FIELDS_30",
    "BOOLEAN_FIELDS",
    "SCHEMAS",
    "QualityProfile",
    "default_profile",
    "ParsedRecord",
    "parse_record",
    "parse_records",
]


class EvidenceParseError(ValueError):
    """A record does not satisfy the strict evidence-record contract."""


# --- Schemas -----------------------------------------------------------------

# Evidence-backed 34-field order (PATH_FORWARD section 2.3). AUTHORITATIVE.
FIELDS_34: Tuple[str, ...] = (
    "PL_surface_temp",
    "PL_output_pressure",
    "PL_chamber_pressure",
    "PL_top_condenser_temp",
    "PL_bottom_condenser_temp",
    "PL_wall1",
    "PL_wall2",
    "PL_bottom1",
    "PL_bottom2",
    "PL_bottom3",
    "PL_bottom4",
    "PL_flow_meter",
    "PL_process",
    "PL_preprocess",
    "MW_reverse_coupler",
    "PL_postprocess",
    "PL_chamber_pump",
    "PL_purge_pump",
    "MT_crucible_temperature",
    "MT_top",
    "MT_bottom",
    "MW_water_state",
    "MW_flow_state",
    "MW_RF",
    "MW_status",
    "MW_power",
    "MW_reverse",
    "MW_period",
    "MW_width",
    "MW_freq",
    "MW_water_temp",
    "MW_flow_rate",
    "PL_Probe1",
    "PL_Probe2",
)

# UNCONFIRMED reconstruction: 34 minus the trailing probe pair.
FIELDS_32: Tuple[str, ...] = tuple(
    f for f in FIELDS_34 if f not in {"PL_Probe1", "PL_Probe2"}
)
# UNCONFIRMED reconstruction: 32 minus the plastics wall pair.
FIELDS_30: Tuple[str, ...] = tuple(
    f for f in FIELDS_32 if f not in {"PL_wall1", "PL_wall2"}
)

SCHEMAS: Dict[str, Tuple[str, ...]] = {
    "34": FIELDS_34,
    "32-UNCONFIRMED": FIELDS_32,
    "30-UNCONFIRMED": FIELDS_30,
}

# Boolean-typed record fields (LabVIEW text TRUE/FALSE). Everything else is numeric.
BOOLEAN_FIELDS = frozenset({
    "PL_process", "PL_preprocess", "PL_postprocess",
    "PL_chamber_pump", "PL_purge_pump",
    "MW_water_state", "MW_flow_state", "MW_RF", "MW_status",
})

_SCHEMA_SETS = {name: frozenset(fields) for name, fields in SCHEMAS.items()}
_BLANK_SPLIT = re.compile(r"\n[ \t]*\n")


# --- Quality profile ---------------------------------------------------------

@dataclass(frozen=True)
class QualityProfile:
    """Controls-owned validity rules. UNSIGNED by default.

    ``quarantine`` is the ONLY rule that acts without a signature: it drops a channel
    whose physical meaning is unproven regardless of value. ``ranges`` and
    ``sentinels`` are applied ONLY once ``signed_by`` is set, so no physical validity
    judgement is ever made on unsigned inference.
    """

    signed_by: Optional[str] = None
    ranges: Mapping[str, Tuple[float, float]] = field(default_factory=dict)
    sentinels: Mapping[str, Sequence[float]] = field(default_factory=dict)
    quarantine: frozenset = frozenset({"PL_bottom2"})
    sentinel_tol: float = 0.5

    def is_signed(self) -> bool:
        return bool(self.signed_by)

    def marks_invalid(self, name: str, value) -> bool:
        if name in self.quarantine:
            return True
        if not self.is_signed():
            return False
        if isinstance(value, bool):
            return False
        for s in self.sentinels.get(name, ()):  # open-TC / overrange sentinels
            if abs(value - s) <= self.sentinel_tol:
                return True
        rng = self.ranges.get(name)
        if rng is not None and not (rng[0] <= value <= rng[1]):
            return True
        return False


def default_profile() -> QualityProfile:
    """The unsigned default: nothing but the ``PL_bottom2`` quarantine."""
    return QualityProfile()


# --- Parsed record -----------------------------------------------------------

@dataclass(frozen=True)
class ParsedRecord:
    schema: str
    fields: Dict[str, object]
    invalid: frozenset
    order: Tuple[str, ...]

    def valid_vars(self) -> Dict[str, object]:
        """Structurally-valid fields with quality-flagged channels omitted.

        This is what a producer would place in a frame's ``vars``: invalid or
        quarantined channels are ABSENT (never zeroed or defaulted)."""
        return {k: v for k, v in self.fields.items() if k not in self.invalid}


# --- Parsing -----------------------------------------------------------------

def _match_schema(names: frozenset) -> Optional[str]:
    for schema, expected in _SCHEMA_SETS.items():
        if names == expected:
            return schema
    return None


def _parse_number(raw: str, name: str) -> float:
    tok = raw.strip()
    if tok == "":
        raise EvidenceParseError(f"{name}: empty numeric value")
    if tok.lower() in ("true", "false"):
        raise EvidenceParseError(f"{name}: boolean token in numeric field")
    try:
        val = float(tok)
    except ValueError as exc:
        raise EvidenceParseError(f"{name}: non-numeric value {tok!r}") from exc
    if not math.isfinite(val):
        raise EvidenceParseError(f"{name}: non-finite value {tok!r}")
    return val


def _parse_bool(raw: str, name: str) -> bool:
    tok = raw.strip()
    if tok == "TRUE":
        return True
    if tok == "FALSE":
        return False
    raise EvidenceParseError(f"{name}: invalid boolean {tok!r} (expected TRUE/FALSE)")


def parse_record(block: str, *, profile: Optional[QualityProfile] = None) -> ParsedRecord:
    """Parse and validate ONE record block. Fail-closed (see module docstring)."""
    profile = profile or default_profile()

    lines = [ln.rstrip("\r") for ln in block.splitlines() if ln.strip() != ""]
    if not lines:
        raise EvidenceParseError("empty record")

    raw_values: Dict[str, str] = {}
    order = []
    for ln in lines:
        if ": " not in ln:
            raise EvidenceParseError(f"line missing ': ' delimiter: {ln!r}")
        name, _, value = ln.partition(": ")
        if name == "" or name != name.strip():
            raise EvidenceParseError(f"malformed field name in line: {ln!r}")
        if name in raw_values:
            raise EvidenceParseError(f"duplicate field {name!r}")
        raw_values[name] = value
        order.append(name)

    schema = _match_schema(frozenset(raw_values))
    if schema is None:
        raise EvidenceParseError(
            "unrecognized or partial schema: field set matches no known record "
            f"(got {len(raw_values)} fields)"
        )
    expected = SCHEMAS[schema]
    if tuple(order) != expected:
        raise EvidenceParseError(f"field order does not match the {schema} schema")

    fields: Dict[str, object] = {}
    invalid = set()
    for name in expected:
        raw = raw_values[name]
        if name in BOOLEAN_FIELDS:
            fields[name] = _parse_bool(raw, name)
        else:
            fields[name] = _parse_number(raw, name)
        if profile.marks_invalid(name, fields[name]):
            invalid.add(name)

    return ParsedRecord(
        schema=schema,
        fields=fields,
        invalid=frozenset(invalid),
        order=tuple(expected),
    )


def parse_records(text: str, *, profile: Optional[QualityProfile] = None):
    """Parse every blank-line-separated record block in a capture. Fail-closed:
    one bad record raises rather than yielding a partial result."""
    blocks = [b for b in _BLANK_SPLIT.split(text.strip("\n")) if b.strip()]
    return [parse_record(b, profile=profile) for b in blocks]
