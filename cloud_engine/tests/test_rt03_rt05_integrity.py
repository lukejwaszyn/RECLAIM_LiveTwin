"""Failing regression baseline for RT-03 and inference-safe RT-05.

These tests state the required future transaction and validation invariants.  They
are expected to fail against the 2026-08-16 implementation for product reasons:
partial dual-chamber mutation, swallowed durable-identity failures, and missing
pre-mutation type/dimension/finiteness validation.

Physical minimum/maximum cases are intentionally absent.  They are blocked on the
controls/thermal-owner decision for approved units, envelopes, reflected-power
semantics, and sensor-bank disagreement limits; this file does not invent them.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import copy
import math
import sys

import numpy as np
import pytest


ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

import push_ingest_dual as ingest_module
from push_ingest_dual import DualPushEngine, TELEMETRY_SCHEMA


PHYSICAL_RANGE_CASES_BLOCKED = (
    "controls/thermal owners must approve units, operating envelopes, "
    "reflected-power semantics, and sensor-disagreement limits"
)


def _frame(now: datetime) -> dict:
    """One canonical frame with valid measurements for both chamber paths."""
    return {
        "schema_version": TELEMETRY_SCHEMA,
        "mode": "live",
        "run_id": "rt-integrity-run-001",
        "source_id": "rt-integrity-crio-01",
        "seq": 1,
        "ts": now.isoformat(),
        "cycle_id": "rt-integrity-cycle-001",
        "source_op_state": "S_MicrowaveHeating",
        "active_chamber": "PL",
        "vars": {
            "PL_T_bed_tc1": 600.0,
            "PL_T_bed_tc2": 601.0,
            "PL_T_bed_tc3": 599.0,
            "PL_T_bed_tc4": 600.0,
            "PL_T_wall_meas": 450.0,
            "PL_P_fwd": 3000.0,
            "PL_P_refl": 100.0,
            "PL_P_chamber": 95.0,
            "MT_T_bed_tc1": 700.0,
            "MT_T_wall_meas": 500.0,
            "MT_P_fwd": 0.0,
            "MT_P_refl": 0.0,
            "MT_P_chamber": 101.0,
        },
    }


def _freeze(value):
    """Recursively capture object state, including nested private mutable fields.

    This is deliberately structural rather than a shallow ``__dict__`` copy.  It
    records arrays, deques, dataclass/config objects, estimator caches, publisher
    state, and future object attributes.  Locks and executable callables are the
    only non-state members reduced to stable type/name markers.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return {"float": "nan"}
        if math.isinf(value):
            return {"float": "+inf" if value > 0 else "-inf"}
        return value
    if isinstance(value, np.generic):
        return _freeze(value.item())
    if isinstance(value, np.ndarray):
        return {
            "array_dtype": str(value.dtype),
            "array_shape": tuple(value.shape),
            "array_values": _freeze(value.tolist()),
        }
    if isinstance(value, datetime):
        return {"datetime": value.isoformat()}
    if isinstance(value, Path):
        return {"path": str(value)}
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, Enum):
        return {"enum": f"{type(value).__module__}.{type(value).__qualname__}.{value.name}"}
    if isinstance(value, dict):
        return {str(k): _freeze(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_freeze(v) for v in value]
    if isinstance(value, deque):
        return {"deque_maxlen": value.maxlen, "items": [_freeze(v) for v in value]}
    if isinstance(value, (set, frozenset)):
        frozen = [_freeze(v) for v in value]
        return {"set": sorted(frozen, key=repr)}
    if callable(value):
        return {"callable": getattr(value, "__qualname__", type(value).__qualname__)}
    if hasattr(value, "__dict__"):
        attrs = {
            name: _freeze(member)
            for name, member in sorted(vars(value).items())
            if name != "_lock"
        }
        return {"object": f"{type(value).__module__}.{type(value).__qualname__}", "attrs": attrs}
    return {"opaque_type": f"{type(value).__module__}.{type(value).__qualname__}"}


def _durable_identity(engine: DualPushEngine):
    path = engine.ident.path
    if not path:
        return None
    target = Path(path)
    return target.read_bytes() if target.exists() else None


def _transaction_snapshot(engine: DualPushEngine) -> dict:
    """Complete accepted-frame transaction aggregate, excluding attempt status.

    ``last_ingest`` is intentionally excluded: it is the disposition of the
    attempted frame and must change to report a rejection.  Locks and the identity
    file's location are not logical transaction state.  Durable file *contents* are
    included separately.
    """
    return _freeze({
        "dual": {
            "count": engine.count,
            "t": engine.t,
            "last_ts": engine._last_ts,
            "production": engine.production,
            "max_frame_age_s": engine.max_frame_age_s,
            "states": engine._states,
        },
        "plastics": {
            "chamber": engine.pl.chamber,
            "t": engine.pl.t,
            "predictive_engine": engine.pl.eng,
        },
        "metals": {
            "chamber": engine.mt.chamber,
            "t": engine.mt.t,
            "predictive_engine": engine.mt.eng,
        },
        "service": engine.svc,
        "command": engine.command,
        "identity": {
            "active_run_id": engine.ident.active_run_id,
            "retired": engine.ident.retired,
            "seqs": engine.ident.seqs,
            "gap_count": engine.ident.gap_count,
            "durable_bytes": _durable_identity(engine),
        },
    })


def _first_differences(before, after, path="state", limit=12):
    differences: list[str] = []

    def walk(left, right, here):
        if len(differences) >= limit:
            return
        if type(left) is not type(right):
            differences.append(f"{here}: type {type(left).__name__} != {type(right).__name__}")
            return
        if isinstance(left, dict):
            for key in sorted(set(left) | set(right), key=str):
                if key not in left:
                    differences.append(f"{here}.{key}: added")
                elif key not in right:
                    differences.append(f"{here}.{key}: removed")
                else:
                    walk(left[key], right[key], f"{here}.{key}")
                if len(differences) >= limit:
                    return
        elif isinstance(left, list):
            if len(left) != len(right):
                differences.append(f"{here}: length {len(left)} != {len(right)}")
            for index, (l_item, r_item) in enumerate(zip(left, right)):
                walk(l_item, r_item, f"{here}[{index}]")
                if len(differences) >= limit:
                    return
        elif left != right:
            differences.append(f"{here}: {left!r} != {right!r}")

    walk(before, after, path)
    return differences


@pytest.fixture
def fixed_now(monkeypatch):
    now = datetime(2026, 8, 16, 16, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(ingest_module, "_utc_now", lambda: now)
    return now


def test_RT_03_failure_after_PL_before_MT_preserves_dual_engine_state(
    tmp_path, monkeypatch, fixed_now
):
    engine = DualPushEngine(production=True, state_file=str(tmp_path / "identity.json"))
    frame = _frame(fixed_now)
    before = _transaction_snapshot(engine)
    metals_started = False

    def fail_as_metals_begins(*_args, **_kwargs):
        nonlocal metals_started
        metals_started = True
        assert engine.pl.t > 0.0, "fault must occur only after plastics completed its step"
        assert engine.pl.eng._k == 1, "plastics predictive graph must have mutated before fault"
        raise RuntimeError("RT-03 injected failure after plastics, as metals begins")

    monkeypatch.setattr(engine.mt, "step", fail_as_metals_begins)
    disposition = engine.ingest_line(frame)
    after = _transaction_snapshot(engine)

    assert metals_started
    assert disposition["status"] == "rejected"
    assert disposition["code"] == "internal_error"
    assert disposition["final"] is False
    if after != before:
        pytest.fail(
            "RT-03: retryable partial failure mutated the accepted-frame transaction aggregate:\n"
            + "\n".join(_first_differences(before, after)),
            pytrace=False,
        )


def test_RT_03_retry_after_partial_failure_equals_clean_one_pass(
    tmp_path, monkeypatch, fixed_now
):
    frame = _frame(fixed_now)
    retried = DualPushEngine(
        production=True, state_file=str(tmp_path / "retried-identity.json")
    )
    original_mt_step = retried.mt.step

    def fail_after_plastics(*_args, **_kwargs):
        assert retried.pl.eng._k == 1
        raise RuntimeError("RT-03 injected partial failure")

    monkeypatch.setattr(retried.mt, "step", fail_after_plastics)
    failed = retried.ingest_line(copy.deepcopy(frame))
    assert failed["status"] == "rejected"
    assert failed["code"] == "internal_error"
    assert failed["final"] is False

    monkeypatch.setattr(retried.mt, "step", original_mt_step)
    retried_result = retried.ingest_line(copy.deepcopy(frame))

    clean = DualPushEngine(
        production=True, state_file=str(tmp_path / "clean-identity.json")
    )
    clean_result = clean.ingest_line(copy.deepcopy(frame))
    retried_state = _transaction_snapshot(retried)
    clean_state = _transaction_snapshot(clean)

    assert retried_result["status"] == "accepted"
    assert clean_result["status"] == "accepted"
    if retried_state != clean_state:
        pytest.fail(
            "RT-03: retry after partial mutation differs from a clean one-pass engine:\n"
            + "\n".join(_first_differences(clean_state, retried_state)),
            pytrace=False,
        )


def test_RT_03_identity_persist_failure_is_not_reported_accepted(
    tmp_path, monkeypatch, fixed_now
):
    engine = DualPushEngine(production=True, state_file=str(tmp_path / "identity.json"))
    before = _transaction_snapshot(engine)

    def fail_durable_replace(*_args, **_kwargs):
        raise OSError("RT-03 injected durable identity replace failure")

    monkeypatch.setattr(ingest_module.os, "replace", fail_durable_replace)
    disposition = engine.ingest_line(_frame(fixed_now))
    after = _transaction_snapshot(engine)

    problems = []
    if disposition["status"] != "rejected":
        problems.append(
            f"durable commit failed but disposition was {disposition['status']!r}; "
            "an accepted result must never be reported"
        )
    if disposition.get("code") != "internal_error" or disposition.get("final") is not False:
        problems.append(
            "persistence failure must be retryable internal_error, got "
            f"status={disposition.get('status')!r}, code={disposition.get('code')!r}, "
            f"final={disposition.get('final')!r}"
        )
    if after != before:
        problems.append(
            "persistence failure left visible/in-memory transaction mutation:\n"
            + "\n".join(_first_differences(before, after))
        )
    if problems:
        pytest.fail(
            "RT-03 durable identity invariant violated:\n" + "\n".join(problems),
            pytrace=False,
        )


INVALID_CASES = [
    pytest.param(("vars", "PL_T_bed_tc1"), math.nan, "telemetry_invalid", id="bed-bank-nan"),
    pytest.param(("vars", "PL_T_bed_tc1"), math.inf, "telemetry_invalid", id="bed-bank-pos-inf"),
    pytest.param(("vars", "PL_T_bed_tc1"), -math.inf, "telemetry_invalid", id="bed-bank-neg-inf"),
    pytest.param(("vars", "PL_T_bed_tc1"), True, "telemetry_invalid", id="bed-bank-bool"),
    pytest.param(("vars", "PL_T_bed_tc1"), "600", "telemetry_invalid", id="bed-bank-numeric-string"),
    pytest.param(("vars", "PL_T_bed_tc1"), [600.0], "telemetry_invalid", id="bed-bank-nested"),
    pytest.param(("vars", "__PL_BED_BANK_WRONG_SIZE__"), None, "telemetry_invalid", id="bed-bank-wrong-size"),
    pytest.param(("vars", "MT_T_bed_tc1"), {"sensor": 700.0}, "telemetry_invalid", id="bed-bank-malformed-object"),
    pytest.param(("vars", "PL_T_wall_meas"), math.nan, "telemetry_invalid", id="wall-temp-nan"),
    pytest.param(("vars", "PL_T_wall_meas"), True, "telemetry_invalid", id="wall-temp-bool"),
    pytest.param(("vars", "PL_T_wall_meas"), "450", "telemetry_invalid", id="wall-temp-numeric-string"),
    pytest.param(("vars", "PL_T_wall_meas"), [450.0], "telemetry_invalid", id="wall-temp-array"),
    pytest.param(("vars", "PL_P_fwd"), math.nan, "telemetry_invalid", id="power-nan"),
    pytest.param(("vars", "PL_P_fwd"), math.inf, "telemetry_invalid", id="power-pos-inf"),
    pytest.param(("vars", "PL_P_fwd"), -math.inf, "telemetry_invalid", id="power-neg-inf"),
    pytest.param(("vars", "PL_P_fwd"), False, "telemetry_invalid", id="power-bool"),
    pytest.param(("vars", "PL_P_fwd"), "3000", "telemetry_invalid", id="power-numeric-string"),
    pytest.param(("vars", "PL_P_fwd"), {"watts": 3000.0}, "telemetry_invalid", id="power-object"),
    pytest.param(("vars", "PL_P_refl"), [100.0], "telemetry_invalid", id="reflected-power-array"),
    pytest.param(("vars", "PL_P_chamber"), math.inf, "telemetry_invalid", id="pressure-inf"),
    pytest.param(("vars", "PL_P_chamber"), True, "telemetry_invalid", id="pressure-bool"),
    pytest.param(("vars", "PL_P_chamber"), "95", "telemetry_invalid", id="pressure-numeric-string"),
    pytest.param(("vars", "PL_P_chamber"), {"kPa": 95.0}, "telemetry_invalid", id="pressure-object"),
    pytest.param(("ts",), "12345", "timestamp_invalid", id="timestamp-numeric-string"),
    pytest.param(("ts",), True, "timestamp_invalid", id="timestamp-bool"),
    pytest.param(("ts",), ["2026-08-16T16:00:00Z"], "timestamp_invalid", id="timestamp-array"),
    pytest.param(("seq",), True, "sequence_invalid", id="sequence-bool"),
    pytest.param(("seq",), "1", "sequence_invalid", id="sequence-numeric-string"),
    pytest.param(("seq",), 1.5, "sequence_invalid", id="sequence-fractional"),
    pytest.param(("seq",), math.nan, "sequence_invalid", id="sequence-nan"),
    pytest.param(("seq",), math.inf, "sequence_invalid", id="sequence-inf"),
    pytest.param(("seq",), [1], "sequence_invalid", id="sequence-array"),
]


def _set_path(target: dict, path: tuple[str, ...], value) -> None:
    if path == ("vars", "__PL_BED_BANK_WRONG_SIZE__"):
        for key in ("PL_T_bed_tc2", "PL_T_bed_tc3", "PL_T_bed_tc4"):
            target["vars"].pop(key)
        return
    obj = target
    for key in path[:-1]:
        obj = obj[key]
    obj[path[-1]] = value


@pytest.mark.parametrize("path,value,expected_code", INVALID_CASES)
def test_RT_05_nan_inf_bool_string_and_wrong_dimension_rejected_before_mutation(
    path, value, expected_code, tmp_path, monkeypatch, fixed_now
):
    engine = DualPushEngine(production=True, state_file=str(tmp_path / "identity.json"))
    frame = _frame(fixed_now)
    _set_path(frame, path, value)
    before = _transaction_snapshot(engine)
    calls = {"PL": 0, "MT": 0}
    original_pl_step = engine.pl.step
    original_mt_step = engine.mt.step

    def observe_pl(*args, **kwargs):
        calls["PL"] += 1
        return original_pl_step(*args, **kwargs)

    def observe_mt(*args, **kwargs):
        calls["MT"] += 1
        return original_mt_step(*args, **kwargs)

    monkeypatch.setattr(engine.pl, "step", observe_pl)
    monkeypatch.setattr(engine.mt, "step", observe_mt)
    raised = None
    try:
        disposition = engine.ingest_line(frame)
    except Exception as exc:  # current seq conversion can raise before a disposition exists
        raised = exc
        disposition = None
    after = _transaction_snapshot(engine)

    problems = []
    if raised is not None:
        problems.append(f"validation raised {type(raised).__name__}: {raised}")
    elif not (
        disposition.get("status") == "rejected"
        and disposition.get("code") == expected_code
        and disposition.get("final") is True
    ):
        problems.append(
            f"expected final {expected_code!r} rejection, got "
            f"status={disposition.get('status')!r}, code={disposition.get('code')!r}, "
            f"final={disposition.get('final')!r}"
        )
    if calls != {"PL": 0, "MT": 0}:
        problems.append(f"chamber step was entered before rejection: {calls!r}")
    if after != before:
        problems.append(
            "filter/lifecycle/time/count/command/output/identity state changed:\n"
            + "\n".join(_first_differences(before, after))
        )
    if problems:
        pytest.fail(
            "RT-05 pre-mutation validation invariant violated:\n" + "\n".join(problems),
            pytrace=False,
        )
