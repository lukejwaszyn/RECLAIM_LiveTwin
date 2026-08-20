from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "crio_psp_adapter" / "windows" / "reclaim-psp-adapter.ps1"
FIXTURE = ROOT / "crio_psp_adapter" / "fixtures" / "engineering-poc.example.json"
POWERSHELL32 = Path(os.environ["WINDIR"]) / "SysWOW64" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


def run_fixture(output: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(POWERSHELL32), "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
            "-Source", "Fixture", "-FixturePath", str(FIXTURE),
            "-Sink", "File", "-OutputPath", str(output), "-MaxFrames", "1", *extra,
        ],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_fixture_emits_one_compact_utf8_lf_line_and_preserves_zero(tmp_path: Path):
    output = tmp_path / "frame.ndjson"
    result = run_fixture(output)
    assert result.returncode == 0, result.stderr
    payload = output.read_bytes()
    assert payload.endswith(b"\n")
    assert not payload.endswith(b"\n\n")
    assert payload.count(b"\n") == 1
    assert not payload.startswith(b"\xef\xbb\xbf")
    frame = json.loads(payload)
    assert frame["source_id"] == "reclaim-crio-psp-poc"
    assert frame["source_op_state"] == "S_Idle"
    assert frame["active_chamber"] == "NONE"
    assert frame["vars"]["PL_bottom1"] == 0.0
    assert frame["vars"]["PL_output_pressure"] == 0.0
    assert frame["vars"]["PL_chamber_pressure"] == 760.0


def test_frame_byte_limit_is_enforced_before_write(tmp_path: Path):
    output = tmp_path / "too-small.ndjson"
    result = run_fixture(output, "-MaxLineBytes", "128")
    assert result.returncode != 0
    assert "limit is 128" in result.stderr
    assert not output.exists()


def test_unknown_field_is_rejected(tmp_path: Path):
    fixture = tmp_path / "unknown.json"
    fixture.write_text(json.dumps({"vars": {"Mod4/AO0": 1.0}}), encoding="utf-8")
    output = tmp_path / "unknown.ndjson"
    result = subprocess.run(
        [
            str(POWERSHELL32), "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
            "-Source", "Fixture", "-FixturePath", str(fixture),
            "-Sink", "File", "-OutputPath", str(output), "-MaxFrames", "1",
        ],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode != 0
    assert "not in the POC allowlist" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("bad_value", ["NaN", "Infinity", [], {}, None])
def test_non_finite_or_non_scalar_value_is_rejected(tmp_path: Path, bad_value):
    fixture = tmp_path / "bad.json"
    fixture.write_text(json.dumps({"vars": {"PL_bottom1": bad_value}}), encoding="utf-8")
    output = tmp_path / "bad.ndjson"
    result = subprocess.run(
        [
            str(POWERSHELL32), "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
            "-Source", "Fixture", "-FixturePath", str(fixture),
            "-Sink", "File", "-OutputPath", str(output), "-MaxFrames", "1",
        ],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode != 0
    assert not output.exists()


def test_fixture_snapshot_skew_is_rejected(tmp_path: Path):
    now = datetime.now(timezone.utc)
    fixture = tmp_path / "skew.json"
    fixture.write_text(json.dumps({
        "vars": {"PL_bottom1": 1.0, "PL_bottom2": 2.0},
        "observed_at": {
            "PL_bottom1": (now - timedelta(seconds=3)).isoformat(),
            "PL_bottom2": now.isoformat(),
        },
    }), encoding="utf-8")
    output = tmp_path / "skew.ndjson"
    result = subprocess.run(
        [
            str(POWERSHELL32), "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
            "-Source", "Fixture", "-FixturePath", str(fixture),
            "-Sink", "File", "-OutputPath", str(output), "-MaxFrames", "1",
            # Keep this test about cross-channel skew, not subprocess startup
            # latency on a loaded Windows gateway.
            "-FreshnessMs", "60000", "-MaxSkewMs", "1000",
        ], text=True, capture_output=True, timeout=20, check=False,
    )
    assert result.returncode != 0
    assert "snapshot skew exceeds 1000 ms" in result.stderr
    assert not output.exists()


def test_restart_releases_single_instance_lock_and_emits_only_fresh_frames(tmp_path: Path):
    output = tmp_path / "restart.ndjson"
    first = run_fixture(output)
    second = run_fixture(output)
    assert first.returncode == second.returncode == 0
    lines = output.read_bytes().splitlines()
    assert len(lines) == 2
    frames = [json.loads(line) for line in lines]
    assert frames[0]["ts"] != frames[1]["ts"]


def test_tcp_disconnect_fails_without_creating_a_replay_file(tmp_path: Path):
    # Port 1 is expected to be closed; the fixture is current but cannot be sent.
    result = subprocess.run(
        [
            str(POWERSHELL32), "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
            "-Source", "Fixture", "-FixturePath", str(FIXTURE),
            "-Sink", "Tcp", "-GatewayHost", "127.0.0.1", "-GatewayPort", "1",
            "-MaxFrames", "1",
        ], text=True, capture_output=True, timeout=20, check=False,
    )
    assert result.returncode != 0
    assert not list(tmp_path.iterdir())


def test_live_reader_requires_ni_metadata_and_floating_scan_values():
    source = SCRIPT.read_text(encoding="utf-8-sig")
    assert "returned no NI metadata" in source
    assert "not a floating-point scan value" in source
    assert "scan_Mod3_AI0_raw" in source
    for channel in range(8):
        assert f"scan_Mod2_TC{channel}_degC" in source
        assert f"'Mod2/TC{channel}'" in source
    assert "MT_top                   = 'Mod2/TC2'" not in source
    assert "PL_bottom2               = 'Mod2/TC5'" not in source
    assert "PL_bottom3               = 'Mod2/TC6'" not in source
    assert "PL_bottom4               = 'Mod2/TC7'" not in source


def test_continuous_psp_mode_has_sustainable_default_and_discards_failed_snapshots():
    source = SCRIPT.read_text(encoding="utf-8-sig")
    assert "[int]$CadenceMs = 3000" in source
    assert "[int]$ReconnectDelayMs = 5000" in source
    assert "[int]$ConnectSpacingMs = 100" in source
    assert "if ($Source -ne 'Psp' -or $MaxFrames -ne 0) { throw }" in source
    assert "discarded snapshot" in source
    assert "Close-PspReaders" in source
    assert "Close-TcpConnection" in source
