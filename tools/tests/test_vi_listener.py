from __future__ import annotations

import socket
import threading
from pathlib import Path

import pytest

from tools.vi_listener import capture_connection, serve


def test_capture_connection_records_chunks_and_hashes(tmp_path: Path) -> None:
    left, right = socket.socketpair()
    capture_path = tmp_path / "capture.bin"
    index_path = tmp_path / "capture.index.jsonl"
    try:
        with capture_path.open("wb") as capture, index_path.open("w") as index:
            right.sendall(b"abc")
            right.shutdown(socket.SHUT_WR)
            assert capture_connection(left, ("127.0.0.1", 1234), capture, index, 3, 1) == 3
        assert capture_path.read_bytes() == b"abc"
        assert '"bytes":3' in index_path.read_text()
        assert '"sha256":"BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD"' in index_path.read_text()
    finally:
        left.close()
        right.close()


def test_capture_refuses_partial_over_limit(tmp_path: Path) -> None:
    left, right = socket.socketpair()
    try:
        with (tmp_path / "capture.bin").open("wb") as capture, (tmp_path / "capture.index").open("w") as index:
            right.sendall(b"abcd")
            right.shutdown(socket.SHUT_WR)
            with pytest.raises(RuntimeError, match="without truncation"):
                capture_connection(left, ("127.0.0.1", 1), capture, index, 3, 1)
        assert (tmp_path / "capture.bin").read_bytes() == b""
    finally:
        left.close()
        right.close()


def test_serve_once_accepts_a_peer(tmp_path: Path) -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    output = tmp_path / "capture.bin"
    thread = threading.Thread(target=serve, args=("127.0.0.1", port, output, 32, 1), kwargs={"once": True})
    thread.start()
    for _ in range(100):
        try:
            client = socket.create_connection(("127.0.0.1", port), timeout=0.1)
            break
        except OSError:
            continue
    else:
        pytest.fail("listener did not start")
    with client:
        client.sendall(b"hello")
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert output.read_bytes() == b"hello"
