"""RECLAIM Edge Gateway — service entrypoint.

Wires receiver -> framer -> buffer -> publisher and runs them as daemon threads
around the durable buffer. Emits a periodic health line and shuts down gracefully.

Run:  python -m reclaim_edge.main
Windows deployment sets RECLAIM_EDGE_CONFIG to config.windows.yaml.
      RECLAIM_EDGE_CONFIG=./config.yaml python -m reclaim_edge.main

Author: LJW.
"""
from __future__ import annotations

import logging
import signal
import sys
import threading
import time

from .buffer import Buffer
from .config import Config
from .convene import ConvenePublisher
from .framer import Framer
from .publisher import Publisher
from .receiver import Receiver
from .status import StatusServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("reclaim_edge")


def main() -> None:
    cfg = Config.load()
    stop = threading.Event()

    buffer = Buffer(cfg.buffer_path, cfg.buffer_max_frames)
    framer = Framer(cfg, seq_store=buffer)   # seq high-water persists across restarts
    convene = ConvenePublisher(cfg, stop) if cfg.convene_enabled else None
    receiver = Receiver(cfg, framer, buffer, stop, audit_publisher=convene)
    publisher = Publisher(cfg, buffer, stop)

    def _sig(*_):
        log.info("shutdown requested")
        stop.set()

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    status = None
    if cfg.status_port:
        status = StatusServer(cfg.status_port, receiver, publisher, buffer, cfg.src,
                              convene=convene)

    log.info("RECLAIM edge gateway starting — transport=%s src=%s", cfg.transport, cfg.src)
    receiver.start()
    publisher.start()
    if convene:
        convene.start()
    if status:
        status.start()

    next_health = time.time() + cfg.health_interval_s
    died = None
    while not stop.is_set():
        time.sleep(0.5)
        # Thread liveness supervision (fix M6): a dead receiver (port in use,
        # unhandled error) or dead publisher must not leave a healthy-looking
        # zombie service. Exit non-zero so the Windows task supervisor recovers it.
        for th in (receiver, publisher):
            if not th.is_alive():
                died = th.name
                log.critical("worker thread '%s' died — exiting for supervisor restart",
                             died)
                stop.set()
                break
        if time.time() >= next_health:
            log.info(
                "health: rx=%d tx=%d queue=%d drops=%d dead_letter=%d last_ack=%.1fs",
                receiver.received, publisher.delivered,
                buffer.depth(), buffer.drops, buffer.dead_letter_count(),
                publisher.last_ack_age,
            )
            next_health = time.time() + cfg.health_interval_s

    receiver.join(timeout=3)
    publisher.join(timeout=3)
    if convene:
        convene.join(timeout=3)
    buffer.close()
    log.info("stopped")
    if died:
        sys.exit(1)


if __name__ == "__main__":
    main()
