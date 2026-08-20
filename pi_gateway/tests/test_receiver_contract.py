from __future__ import annotations

import json
import threading

from reclaim_edge.buffer import Buffer
from reclaim_edge.config import Config
from reclaim_edge.framer import Framer
from reclaim_edge.receiver import Receiver


class _ChunkedConnection:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.recv_calls = 0

    def settimeout(self, _timeout):
        pass

    def setsockopt(self, *_args):
        pass

    def recv(self, size):
        self.recv_calls += 1
        if not self._chunks:
            return b""
        chunk = self._chunks[0]
        if len(chunk) <= size:
            return self._chunks.pop(0)
        self._chunks[0] = chunk[size:]
        return chunk[:size]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass


def _receiver(*, max_line_bytes=8192):
    cfg = Config(run_id="receiver-contract", strict_fields=False,
                 max_line_bytes=max_line_bytes)
    buffer = Buffer(":memory:", 100)
    receiver = Receiver(
        cfg,
        Framer(cfg, seq_store=buffer),
        buffer,
        threading.Event(),
    )
    return receiver, buffer


def _line(value=1.0):
    return json.dumps({
        "source_id": "contract-test",
        "cycle_id": "cycle-1",
        "ts": "2026-08-19T20:00:00Z",
        "source_op_state": "S_Evacuate",
        "active_chamber": "PL",
        "vars": {"PL_bottom1": value},
    }, separators=(",", ":")).encode("utf-8")


def test_invalid_utf8_and_bad_contract_are_line_local_then_valid_frame_enqueues():
    receiver, buffer = _receiver()
    try:
        connection = _ChunkedConnection([
            b'{"vars":{"PL_bottom1":23.0},"source_id":"bad-\xff"}\n'
            b'{"vars":{"PL_bottom1":null}}\n'
            + _line(0.0) + b"\n",
        ])

        receiver._serve(connection)

        assert receiver.received == 1
        assert buffer.depth() == 1
        assert receiver.last_frame["seq"] == 1
        assert receiver.last_frame["vars"]["PL_bottom1"] == 0.0
    finally:
        buffer.close()


def test_pre_lf_buffer_is_bounded_and_connection_drops_at_limit():
    receiver, buffer = _receiver(max_line_bytes=8192)
    try:
        connection = _ChunkedConnection([
            b"x" * 4096,
            b"x" * 4096,
            _line() + b"\n",
        ])

        receiver._serve(connection)

        assert connection.recv_calls == 2
        assert receiver.received == 0
        assert buffer.depth() == 0
    finally:
        buffer.close()


def test_line_exactly_at_including_lf_byte_limit_is_accepted():
    receiver, buffer = _receiver(max_line_bytes=8192)
    try:
        payload = _line(3.0)
        line = payload + (b" " * (8191 - len(payload))) + b"\n"
        assert len(line) == 8192

        receiver._serve(_ChunkedConnection([line]))

        assert receiver.received == 1
        assert buffer.depth() == 1
        assert receiver.last_frame["vars"]["PL_bottom1"] == 3.0
    finally:
        buffer.close()


def test_multiple_valid_lf_lines_on_one_connection_are_preserved():
    receiver, buffer = _receiver()
    try:
        connection = _ChunkedConnection([_line(1.0) + b"\n" + _line(2.0) + b"\n"])

        receiver._serve(connection)

        assert receiver.received == 2
        assert buffer.depth() == 2
        assert receiver.last_frame["vars"]["PL_bottom1"] == 2.0
    finally:
        buffer.close()
