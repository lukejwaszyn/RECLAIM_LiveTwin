from __future__ import annotations

import json
from pathlib import Path
import stat
import threading

import pytest

from reclaim_edge.config import Config
from reclaim_edge.file_watch import FileWatchPublisher


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


def test_file_watch_writes_flat_private_json_atomically(tmp_path: Path) -> None:
    target = tmp_path / "watch" / "scenario.json"
    publisher = FileWatchPublisher(
        Config(file_watch_enabled=True, file_watch_path=str(target)),
        threading.Event(),
    )

    publisher._write(_frame())

    value = json.loads(target.read_text(encoding="utf-8"))
    assert value["mode"] == "harness"
    assert value["active_chamber"] == "MT"
    assert value["MT_crucible_temperature"] == 313.418
    assert value["MW_RF"] is True
    assert "MT_top" not in value
    assert "vars" not in value
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert not list(target.parent.glob(".*.tmp"))


def test_file_watch_submit_coalesces_to_latest_frame(tmp_path: Path) -> None:
    publisher = FileWatchPublisher(
        Config(file_watch_path=str(tmp_path / "scenario.json")), threading.Event()
    )
    publisher.submit({"seq": 1})
    publisher.submit({"seq": 2})

    assert publisher.coalesced == 1
    assert publisher._pending.get_nowait()["seq"] == 2


def test_file_watch_requires_absolute_expanded_path(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "file_watch_enabled: true\nfile_watch_path: relative/scenario.json\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="absolute file_watch_path"):
        Config.load(str(config))
