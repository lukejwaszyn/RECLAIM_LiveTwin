"""RECLAIM Edge Gateway — cRIO frame receiver (Seam A).

Threaded TCP server on the trusted LAN. Accepts the cRIO's outbound connection,
reads line-delimited frames, parses + frames + validates each, and enqueues to the
durable buffer. Plaintext by design: this segment is the isolated OT network, and
TLS is handled on the WAN side by the publisher.

Author: LJW.
"""
from __future__ import annotations

import logging
import socket
import threading
import time

from .buffer import Buffer
from .config import Config
from .framer import Framer, parse_line

log = logging.getLogger("reclaim_edge.receiver")


class Receiver(threading.Thread):
    def __init__(self, cfg: Config, framer: Framer, buffer: Buffer, stop: threading.Event):
        super().__init__(name="receiver", daemon=True)
        self.cfg = cfg
        self.framer = framer
        self.buffer = buffer
        self.stop = stop
        self.received = 0
        self.last_frame = None   # most recent canonical frame (for the status endpoint)

    def run(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.cfg.listen_host, self.cfg.listen_port))
        srv.listen(1)
        srv.settimeout(1.0)
        log.info("listening for cRIO on %s:%d", self.cfg.listen_host, self.cfg.listen_port)
        while not self.stop.is_set():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            log.info("cRIO connected from %s", addr)
            self._serve(conn)
        srv.close()

    def _serve(self, conn: socket.socket) -> None:
        """Serve one cRIO connection.

        Hardened against half-open sockets (review fix H2): a cRIO power-cycle
        that never sends FIN used to leave this loop spinning on recv timeouts
        forever while the reconnecting cRIO waited in the backlog — telemetry
        silently stopped. Now: TCP keepalive is enabled, and a connection with
        no data for `conn_idle_timeout_s` is dropped so accept() can serve the
        reconnect."""
        conn.settimeout(1.0)
        try:
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            # Platform TCP keepalive defaults are a secondary half-open defense.
            if hasattr(socket, "TCP_KEEPIDLE"):
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 10)
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        except OSError:  # pragma: no cover - platform without keepalive tuning
            pass
        idle_limit = float(self.cfg.conn_idle_timeout_s)
        last_data = time.time()
        buf = b""
        with conn:
            while not self.stop.is_set():
                try:
                    chunk = conn.recv(4096)
                except socket.timeout:
                    if idle_limit > 0 and time.time() - last_data > idle_limit:
                        log.warning("cRIO connection idle for %.0fs — dropping so a "
                                    "reconnect can be served", idle_limit)
                        break
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                last_data = time.time()
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self._handle_line(line.decode("utf-8", "replace"))

    def _handle_line(self, line: str) -> None:
        try:
            raw = parse_line(line)
        except Exception as exc:  # malformed line — log and skip
            log.warning("bad frame: %s", exc)
            return
        if not raw:
            return
        frame, warnings = self.framer.build(raw)
        for w in warnings:
            log.warning("frame warning: %s", w)
        # frame + seq high-water mark persist in ONE transaction (fix M7)
        self.buffer.enqueue(self.framer.dumps(frame),
                            meta_key=f"seq:{frame['run_id']}",
                            meta_value=str(frame["seq"]))
        self.last_frame = frame
        self.received += 1
