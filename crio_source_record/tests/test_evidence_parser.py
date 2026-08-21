"""Strict-parser contract tests for the legacy cRIO evidence record."""
from __future__ import annotations

from pathlib import Path

import pytest

from crio_source_record.evidence_parser import (
    BOOLEAN_FIELDS,
    EvidenceParseError,
    FIELDS_34,
    ParsedRecord,
    QualityProfile,
    default_profile,
    parse_record,
    parse_records,
)

FX = Path(__file__).resolve().parents[1] / "fixtures"


def _fixture(name: str) -> str:
    return (FX / name).read_text()


# --- happy path --------------------------------------------------------------

def test_parses_nominal_34_record():
    rec = parse_record(_fixture("record_34_nominal.txt"))
    assert isinstance(rec, ParsedRecord)
    assert rec.schema == "34"
    assert tuple(rec.fields) == FIELDS_34
    assert len(rec.fields) == 34


def test_numeric_and_boolean_fields_are_typed():
    rec = parse_record(_fixture("record_34_nominal.txt"))
    assert isinstance(rec.fields["PL_surface_temp"], float)
    assert rec.fields["PL_process"] is True
    assert rec.fields["PL_preprocess"] is False
    for name in BOOLEAN_FIELDS:
        assert isinstance(rec.fields[name], bool)


def test_exact_zero_is_a_valid_measurement():
    rec = parse_record(_fixture("record_34_nominal.txt"))
    assert rec.fields["MT_top"] == 0.0
    assert "MT_top" not in rec.invalid


def test_32_and_30_reconstructions_detected():
    assert parse_record(_fixture("record_32_unconfirmed.txt")).schema == "32-UNCONFIRMED"
    assert parse_record(_fixture("record_30_unconfirmed.txt")).schema == "30-UNCONFIRMED"


def test_parse_records_reads_a_multi_record_stream():
    recs = parse_records(_fixture("record_34_stream.txt"))
    assert len(recs) == 3
    assert all(r.schema == "34" for r in recs)
    assert [r.fields["MW_power"] for r in recs] == [3000.0, 3010.5, 2990.0]


# --- fail-closed --------------------------------------------------------------

def test_delimiter_defect_is_rejected():
    with pytest.raises(EvidenceParseError, match="delimiter"):
        parse_record(_fixture("record_30_delimiter_defect.txt"))


def test_duplicate_field_is_rejected():
    block = _fixture("record_34_nominal.txt") + "PL_surface_temp: 1.0\n"
    with pytest.raises(EvidenceParseError, match="duplicate"):
        parse_record(block)


def test_unknown_field_makes_schema_unrecognized():
    block = _fixture("record_34_nominal.txt") + "PL_ghost_channel: 1.0\n"
    with pytest.raises(EvidenceParseError, match="schema"):
        parse_record(block)


def test_partial_schema_is_rejected():
    lines = _fixture("record_34_nominal.txt").splitlines()
    partial = "\n".join(lines[:-1]) + "\n"  # drop the last field
    with pytest.raises(EvidenceParseError, match="schema"):
        parse_record(partial)


def test_field_order_mismatch_is_rejected():
    lines = _fixture("record_34_nominal.txt").splitlines()
    lines[0], lines[1] = lines[1], lines[0]
    with pytest.raises(EvidenceParseError, match="order"):
        parse_record("\n".join(lines) + "\n")


def test_missing_colon_space_is_rejected():
    lines = _fixture("record_34_nominal.txt").splitlines()
    lines[0] = lines[0].replace(": ", ":")  # colon, no space
    with pytest.raises(EvidenceParseError, match="delimiter"):
        parse_record("\n".join(lines) + "\n")


@pytest.mark.parametrize("token", ["inf", "-inf", "nan", "1e999"])
def test_non_finite_numeric_is_rejected(token):
    lines = _fixture("record_34_nominal.txt").splitlines()
    lines[0] = f"PL_surface_temp: {token}"
    with pytest.raises(EvidenceParseError):
        parse_record("\n".join(lines) + "\n")


def test_empty_numeric_value_is_rejected():
    lines = _fixture("record_34_nominal.txt").splitlines()
    lines[0] = "PL_surface_temp: "
    with pytest.raises(EvidenceParseError):
        parse_record("\n".join(lines) + "\n")


def test_invalid_boolean_token_is_rejected():
    lines = _fixture("record_34_nominal.txt").splitlines()
    idx = FIELDS_34.index("PL_process")
    lines[idx] = "PL_process: 1"
    with pytest.raises(EvidenceParseError, match="boolean"):
        parse_record("\n".join(lines) + "\n")


def test_boolean_token_in_numeric_field_is_rejected():
    lines = _fixture("record_34_nominal.txt").splitlines()
    lines[0] = "PL_surface_temp: TRUE"
    with pytest.raises(EvidenceParseError, match="boolean"):
        parse_record("\n".join(lines) + "\n")


# --- quality profile ----------------------------------------------------------

def test_default_profile_is_unsigned_and_quarantines_pl_bottom2():
    prof = default_profile()
    assert prof.is_signed() is False
    assert prof.quarantine == frozenset({"PL_bottom2"})


def test_pl_bottom2_quarantined_by_default():
    rec = parse_record(_fixture("record_34_nominal.txt"))
    assert "PL_bottom2" in rec.invalid
    assert "PL_bottom2" not in rec.valid_vars()
    assert len(rec.valid_vars()) == 33


def test_overrange_bottom2_is_flagged_by_default_quarantine():
    rec = parse_record(_fixture("record_34_pl_bottom2_overrange.txt"))
    assert "PL_bottom2" in rec.invalid


def test_unsigned_profile_does_not_apply_ranges():
    # A range is supplied but the profile is UNSIGNED, so it must NOT act.
    prof = QualityProfile(ranges={"PL_surface_temp": (0.0, 100.0)})
    rec = parse_record(_fixture("record_34_nominal.txt"), profile=prof)
    assert "PL_surface_temp" not in rec.invalid  # 224 is out of range but unsigned


def test_signed_profile_range_flags_out_of_range():
    prof = QualityProfile(signed_by="controls-x", quarantine=frozenset(),
                          ranges={"PL_surface_temp": (0.0, 100.0)})
    rec = parse_record(_fixture("record_34_nominal.txt"), profile=prof)
    assert "PL_surface_temp" in rec.invalid


def test_signed_profile_sentinel_flags_open_channel():
    prof = QualityProfile(signed_by="controls-x", quarantine=frozenset(),
                          sentinels={"PL_bottom2": (1383.0,)})
    rec = parse_record(_fixture("record_34_nominal.txt"), profile=prof)
    assert "PL_bottom2" in rec.invalid


def test_signed_all_valid_profile_keeps_the_full_bank():
    prof = QualityProfile(signed_by="controls-x", quarantine=frozenset())
    rec = parse_record(_fixture("record_34_nominal.txt"), profile=prof)
    assert rec.invalid == frozenset()
    assert "PL_bottom2" in rec.valid_vars()
