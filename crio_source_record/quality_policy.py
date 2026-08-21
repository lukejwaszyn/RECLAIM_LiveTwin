"""crio_source_record/quality_policy.py — per-channel validity + incomplete-bank
policy, applied at the SOURCE quality layer (backlog item 1).

Problem this solves (all documented, verified against the real cloud):

* An excluded bed thermocouple is today a SILENT drop. There is no per-channel or
  per-chamber signal saying *which* channel was withheld or why.
* If one plastics bed TC is withheld, ``labview_map.normalize`` emits an incomplete
  ``PL_T_bed_tc{1,3,4}`` bank, and the cloud completeness gate
  (``push_ingest_dual._validate_raw_telemetry``) rejects the WHOLE frame
  (``telemetry_invalid``) — losing MT and MW with it.

Key verified property of the cloud: the completeness gate is
``if bank and bank != [tc1..N]`` — an *empty* bed bank passes, and a chamber with no
valid bed temperature publishes ``<CH>_sensor_valid=false`` and is not stepped
(``push_ingest_dual`` C6). So the incomplete-bank policies below are realizable purely
at the source, with NO change to the signed cloud validator.

Policies (the choice is CONTROLS-OWNED; default preserves today's behavior):

* ``REJECT`` (default) — leave the partial bank intact. The cloud rejects the frame,
  exactly as it does now. No behavior change ships without a signed decision.
* ``SUPPRESS_INCOMPLETE`` — drop the whole affected bed bank (step on the remaining
  valid TCs). The cloud then KEEPS the frame, marks that chamber
  ``sensor_valid=false``, and MT/MW survive. This is the recommended policy once
  controls signs the open-TC semantics, because it stops one open channel from
  destroying an entire multi-chamber frame while never contaminating the bed mean.

The per-channel and per-chamber validity are returned as STRUCTURED metadata, not as
inline wire vars: the frame contract (section 4) admits invalid channels only as
"omitted or accompanied by an approved quality contract", so validity belongs in a
signed quality sidecar, not smuggled into ``vars``.

The open-TC trigger must ultimately be the NI-9213's own open-thermocouple status
(ground truth), applied via a signed :class:`QualityProfile`; a "value ~ 1383"
sentinel is only an inference until controls confirms it.

Author: RECLAIM repository developer (offline).
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .evidence_parser import ParsedRecord, QualityProfile, default_profile

__all__ = ["BankPolicy", "BED_BANKS", "PolicyResult", "apply_policy"]


class BankPolicy(enum.Enum):
    REJECT = "reject"                       # current cloud behavior (default)
    SUPPRESS_INCOMPLETE = "suppress"        # drop the incomplete bank, keep the frame


# Raw record fields feeding each canonical bed bank (see labview_map _PL_BED/_MT_BED).
BED_BANKS: Dict[str, Tuple[str, ...]] = {
    "PL": ("PL_bottom1", "PL_bottom2", "PL_bottom3", "PL_bottom4"),
    "MT": ("MT_bottom",),
}


@dataclass(frozen=True)
class PolicyResult:
    vars: Dict[str, object]                 # frame vars after the policy is applied
    channel_validity: Dict[str, bool]       # per raw channel: survived the profile?
    chamber_validity: Dict[str, bool]       # per chamber: bed bank complete & valid?
    policy: BankPolicy

    def invalid_channels(self) -> Tuple[str, ...]:
        return tuple(k for k, ok in self.channel_validity.items() if not ok)


def apply_policy(
    record: ParsedRecord,
    *,
    profile: Optional[QualityProfile] = None,
    policy: BankPolicy = BankPolicy.REJECT,
) -> PolicyResult:
    """Apply the incomplete-bank policy to a parsed record.

    ``record`` should already be parsed under ``profile`` (its ``.invalid`` set drives
    validity); ``profile`` is accepted only to make the default explicit.
    """
    _ = profile or default_profile()

    valid = record.valid_vars()             # invalid/quarantined already omitted
    channel_validity = {name: (name not in record.invalid) for name in record.fields}

    out = dict(valid)
    chamber_validity: Dict[str, bool] = {}
    for chamber, bank in BED_BANKS.items():
        present_in_record = [f for f in bank if f in record.fields]
        if not present_in_record:
            continue                        # this chamber's bank is not in this schema
        surviving = [f for f in bank if f in valid]
        complete = len(surviving) == len(present_in_record)
        chamber_validity[chamber] = complete
        if not complete and policy is BankPolicy.SUPPRESS_INCOMPLETE:
            for f in surviving:             # step on the remaining valid TCs
                out.pop(f, None)

    return PolicyResult(
        vars=out,
        channel_validity=channel_validity,
        chamber_validity=chamber_validity,
        policy=policy,
    )
