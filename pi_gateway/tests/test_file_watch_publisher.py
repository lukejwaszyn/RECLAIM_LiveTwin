from __future__ import annotations

from pathlib import Path
import stat
import threading

import pytest

from reclaim_edge.config import Config
from reclaim_edge.file_watch import FileWatchPublisher, frame_to_text


def _frame() -> dict:
    return {
        "schema_version": "reclaim.telemetry.v1",
        "mode": "harness",
        "run_id": "scenario-run-1",
        "source_id": "reclaim-macbook-scenario-01",
        "cycle_id": "scenario-cycle-1",
        "seq": 4,
        "ts": "2026-08-24T15:00:00Z",
        "source_op_state": "S_MicrowaveHeating",
        "active_chamber": "MT",
        "vars": {
            "MT_crucible_temperature": 313.418,
            "MW_RF": True,
            "MT_top": float("nan"),
        },
    }


def test_file_watch_writes_live_style_private_text_atomically(tmp_path: Path) -> None:
    target = tmp_path / "watch" / "scenario.txt"
    publisher = FileWatchPublisher(
        Config(file_watch_enabled=True, file_watch_path=str(target)),
        threading.Event(),
    )

    publisher._write(_frame())

    value = target.read_text(encoding="utf-8")
    assert value.startswith(
        "schema_version: reclaim.telemetry.v1, mode: harness, run_id: scenario-run-1"
    )
    assert ", active_chamber: MT, " in value
    assert "MT_crucible_temperature: 313.418000" in value
    assert "MT_top: NaN" in value
    assert "MW_RF: TRUE" in value
    assert "PL_surface_temp: NaN" in value
    assert len(value.rstrip("\n").split(", ")) == 43
    assert "vars:" not in value
    assert value.endswith("\n") and value.count("\n") == 1
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert not list(target.parent.glob(".*.tmp"))


def test_file_watch_submit_coalesces_to_latest_frame(tmp_path: Path) -> None:
    publisher = FileWatchPublisher(
        Config(file_watch_path=str(tmp_path / "scenario.txt")), threading.Event()
    )
    publisher.submit({"seq": 1})
    publisher.submit({"seq": 2})

    assert publisher.coalesced == 1
    assert publisher._pending.get_nowait()["seq"] == 2


def test_file_watch_requires_absolute_expanded_path(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "file_watch_enabled: true\nfile_watch_path: relative/scenario.txt\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="absolute file_watch_path"):
        Config.load(str(config))


def test_text_format_matches_labview_scalar_conventions() -> None:
    record = frame_to_text(_frame())

    assert "seq: 4" in record
    assert "MT_crucible_temperature: 313.418000" in record
    assert "MT_top: NaN" in record
    assert "MW_RF: TRUE" in record
