from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "crio_psp_adapter" / "windows" / "reclaim-psp-adapter.ps1"
TCP_GET_PROBE = ROOT / "crio_psp_adapter" / "windows" / "capture-crio-tcp-get.ps1"
TCP_PROXY = ROOT / "crio_psp_adapter" / "windows" / "capture_crio_tcp_proxy.py"
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
    assert "$null = $Reader.SyncConnectTo" in source
    assert "if (-not $Connected" not in source
    assert "if ($Reader.LastError -ne 0)" in source
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


def run_tcp_get_server(response: bytes):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    received = []

    def serve():
        try:
            connection, _ = listener.accept()
            with connection:
                received.append(connection.recv(16))
                connection.sendall(response)
        finally:
            listener.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return listener.getsockname()[1], received, thread


def test_tcp_get_probe_sends_exact_request_and_preserves_raw_response(tmp_path: Path):
    response = b"PL_surface_temp: 224.119084\r\n"
    port, received, thread = run_tcp_get_server(response)
    output = tmp_path / "response.bin"
    result = subprocess.run(
        [
            str(POWERSHELL32), "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(TCP_GET_PROBE),
            "-CrioHost", "127.0.0.1", "-CrioPort", str(port),
            "-OutputPath", str(output),
        ], text=True, capture_output=True, timeout=20, check=False,
    )
    thread.join(timeout=5)
    assert result.returncode == 0, result.stderr
    assert received == [b"GET"]
    assert output.read_bytes() == response
    evidence = json.loads(result.stdout)
    assert evidence["request_hex"] == "474554"
    assert evidence["bytes"] == len(response)


def test_tcp_get_probe_rejects_oversize_response_without_partial_file(tmp_path: Path):
    port, _, thread = run_tcp_get_server(b"x" * 33)
    output = tmp_path / "oversize.bin"
    result = subprocess.run(
        [
            str(POWERSHELL32), "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(TCP_GET_PROBE),
            "-CrioHost", "127.0.0.1", "-CrioPort", str(port),
            "-OutputPath", str(output), "-MaxResponseBytes", "32",
        ], text=True, capture_output=True, timeout=20, check=False,
    )
    thread.join(timeout=5)
    assert result.returncode != 0
    assert "exceeds 32 bytes" in result.stderr
    assert not output.exists()


def test_tcp_get_probe_refuses_to_overwrite_evidence(tmp_path: Path):
    output = tmp_path / "existing.bin"
    output.write_bytes(b"preserve")
    result = subprocess.run(
        [
            str(POWERSHELL32), "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(TCP_GET_PROBE),
            "-CrioHost", "127.0.0.1", "-CrioPort", "1",
            "-OutputPath", str(output),
        ], text=True, capture_output=True, timeout=20, check=False,
    )
    assert result.returncode != 0
    assert "refusing to overwrite evidence" in result.stderr
    assert output.read_bytes() == b"preserve"


def test_tcp_proxy_preserves_working_vi_exchange_and_captures_only_crio_data(tmp_path: Path):
    response = b"live-record-1\n"
    crio_port, received, crio_thread = run_tcp_get_server(response)
    reserve = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    reserve.bind(("127.0.0.1", 0))
    proxy_port = reserve.getsockname()[1]
    reserve.close()
    output = tmp_path / "live.bin"
    proxy = subprocess.Popen(
        [
            sys.executable, str(TCP_PROXY), "--listen-port", str(proxy_port),
            "--crio-host", "127.0.0.1", "--crio-port", str(crio_port),
            "--output", str(output),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        assert proxy.stdout is not None
        assert json.loads(proxy.stdout.readline())["event"] == "listening"
        with socket.create_connection(("127.0.0.1", proxy_port), timeout=5) as vi:
            vi.sendall(b"GET")
            assert vi.recv(1024) == response
        crio_thread.join(timeout=5)
    finally:
        proxy.terminate()
        proxy.wait(timeout=5)
    assert received == [b"GET"]
    assert output.read_bytes() == response
    index = [json.loads(line) for line in Path(str(output) + ".index.jsonl").read_text().splitlines()]
    assert sum(item["bytes"] for item in index) == len(response)
