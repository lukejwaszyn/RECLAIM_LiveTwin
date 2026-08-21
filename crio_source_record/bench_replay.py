"""crio_source_record/bench_replay.py — no-cRIO bench replay harness (backlog item 3).

Streams sanitized fixtures over a real TCP socket into a locally-run gateway
:class:`Receiver`, lets the receiver frame + validate + enqueue them exactly as it
would for the cRIO, then drains the durable buffer through the real cloud
:class:`DualPushEngine`. This exercises the whole seam — framing, the 8192-byte line
bound, degC->K / Torr->kPa conversion, the ``PL_bottom2`` quarantine, duplicate /
stale / reconnect handling, and absent-field gating — with no cRIO, no VI, and no
production endpoint. The only thing left unproven at the first cRIO window is the cRIO
itself.

Nothing here touches ``192.168.1.1:9070`` or any real endpoint: the receiver binds
loopback on an ephemeral port, and the buffer is a throwaway temp file.

Author: RECLAIM repository developer (offline).
"""
from __future__ import annotations

import contextlib
import json
import socket
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from reclaim_edge.buffer import Buffer
from reclaim_edge.config import Config
from reclaim_edge.framer import Framer
from reclaim_edge.receiver import Receiver

from push_ingest_dual import DualPushEngine

from .evidence_parser import ParsedRecord, QualityProfile, parse_records
from .frame_builder import build_frame
from .quality_policy import BankPolicy, apply_policy

__all__ = ["BenchResult", "build_stream", "replay", "ingest_all", "run_bench"]

_FX = Path(__file__).resolve().parent / "fixtures"


@dataclass
class BenchResult:
    sent: int
    received: int
    payloads: List[str] = field(default_factory=list)   # canonical frames off the buffer


def _fresh_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_stream(
    records: Sequence[ParsedRecord],
    *,
    meta: dict,
    profile: Optional[QualityProfile] = None,
    policy: BankPolicy = BankPolicy.REJECT,
    fresh_ts: bool = True,
    seq_hint: Optional[Iterable[int]] = None,
) -> List[bytes]:
    """Turn parsed records into ready-to-send source frames via the quality policy."""
    frames: List[bytes] = []
    for rec in records:
        res = apply_policy(rec, profile=profile, policy=policy)
        m = dict(meta)
        if fresh_ts:
            m["ts"] = _fresh_ts()
        frames.append(build_frame(res.vars, **m))
    return frames


def build_stream_from_fixture(fixture: str, **kw) -> List[bytes]:
    recs = parse_records((_FX / fixture).read_text(), profile=kw.get("profile"))
    return build_stream(recs, **kw)


def _wait(predicate, timeout=5.0, interval=0.02) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def replay(frames: Sequence[bytes], *, reconnect_after: Optional[int] = None,
           host: str = "127.0.0.1") -> BenchResult:
    """Stream ``frames`` over TCP into a loopback gateway receiver; return what the
    receiver enqueued. ``reconnect_after`` drops and reopens the client socket after
    that many frames, exercising the receiver's reconnect path."""
    # ephemeral port
    probe = socket.socket()
    probe.bind((host, 0))
    port = probe.getsockname()[1]
    probe.close()

    tmpdir = tempfile.mkdtemp(prefix="reclaim_bench_")
    cfg = Config(listen_host=host, listen_port=port,
                 buffer_path=str(Path(tmpdir) / "queue.db"),
                 conn_idle_timeout_s=2.0)
    buffer = Buffer(cfg.buffer_path, cfg.buffer_max_frames)
    framer = Framer(cfg)
    stop = threading.Event()
    recv = Receiver(cfg, framer, buffer, stop)
    recv.start()

    def _connect() -> socket.socket:
        holder: dict = {}

        def attempt() -> bool:
            s = socket.socket()
            if _try_connect(s, host, port):
                holder["s"] = s
                return True
            s.close()
            return False

        assert _wait(attempt, timeout=5.0), "receiver never came up"
        return holder["s"]

    sent = 0
    try:
        client = _connect()
        for i, fr in enumerate(frames):
            if reconnect_after is not None and i == reconnect_after:
                client.close()
                # give the receiver a beat to return to accept()
                time.sleep(0.1)
                client = _connect()
            client.sendall(fr)
            sent += 1
        client.close()
        _wait(lambda: buffer.depth() >= len(frames), timeout=5.0)
    finally:
        stop.set()
        recv.join(timeout=5.0)

    received = buffer.depth()
    payloads = [p for _id, p in buffer.dequeue_batch(len(frames) + 16)]
    buffer.close()
    return BenchResult(sent=sent, received=received, payloads=payloads)


def _try_connect(sock: socket.socket, host: str, port: int) -> bool:
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False


def ingest_all(payloads: Sequence[str], *, engine: Optional[DualPushEngine] = None
               ) -> Tuple[List[dict], DualPushEngine]:
    """Drain buffered canonical frames through the real cloud engine."""
    engine = engine or DualPushEngine(production=True)
    dispositions = [engine.ingest_line(json.loads(p)) for p in payloads]
    return dispositions, engine


def run_bench() -> dict:
    """A standard end-to-end scenario, summarized. Used by ``__main__``."""
    meta = dict(source_id="reclaim-crio-rt-01", cycle_id="bench-cycle-001",
                source_op_state="S_MicrowaveHeating", active_chamber="PL")
    signed = QualityProfile(signed_by="bench", quarantine=frozenset())
    recs = parse_records((_FX / "record_34_stream.txt").read_text(), profile=signed)
    frames = build_stream(recs, meta=meta, profile=signed,
                          policy=BankPolicy.SUPPRESS_INCOMPLETE)
    result = replay(frames)
    disps, engine = ingest_all(result.payloads)
    return {
        "sent": result.sent,
        "received": result.received,
        "max_frame_bytes": max(len(f) for f in frames),
        "accepted": sum(d["status"] == "accepted" for d in disps),
        "rejected": sum(d["status"] == "rejected" for d in disps),
    }


if __name__ == "__main__":  # pragma: no cover
    import pprint
    pprint.pprint(run_bench())
