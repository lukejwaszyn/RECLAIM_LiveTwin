"""Atomic local JSON publisher for Convene File Watch variables."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
from typing import Any, Dict

from .config import Config
from .convene import frame_to_variables

log = logging.getLogger("reclaim_edge.file_watch")


class FileWatchPublisher(threading.Thread):
    """Coalesce frames and atomically replace one flat, owner-private JSON file."""

    def __init__(self, cfg: Config, stop: threading.Event):
        super().__init__(name="file-watch", daemon=True)
        self.cfg = cfg
        self.stop = stop
        self.path = Path(
            os.path.expandvars(os.path.expanduser(cfg.file_watch_path))
        )
        self._pending: queue.Queue[Dict[str, Any]] = queue.Queue(maxsize=1)
        self.delivered = 0
        self.failed = 0
        self.coalesced = 0
        self.last_success_at = 0.0
        self._last_failure_log_at = 0.0

    def submit(self, frame: Dict[str, Any]) -> None:
        try:
            self._pending.put_nowait(frame)
            return
        except queue.Full:
            pass
        try:
            self._pending.get_nowait()
            self.coalesced += 1
        except queue.Empty:
            pass
        try:
            self._pending.put_nowait(frame)
        except queue.Full:
            self.coalesced += 1

    def _write(self, frame: Dict[str, Any]) -> None:
        variables = frame_to_variables(frame)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(variables, handle, allow_nan=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self.path.chmod(0o600)
        finally:
            temporary.unlink(missing_ok=True)

    @property
    def last_success_age(self) -> float | None:
        if not self.last_success_at:
            return None
        return max(0.0, time.time() - self.last_success_at)

    def run(self) -> None:
        retry: Dict[str, Any] | None = None
        while not self.stop.is_set() or retry is not None or not self._pending.empty():
            if retry is None:
                try:
                    retry = self._pending.get(timeout=0.25)
                except queue.Empty:
                    continue
            try:
                self._write(retry)
            except Exception as exc:
                self.failed += 1
                now = time.time()
                if now - self._last_failure_log_at >= 10.0:
                    log.warning("file-watch update failed for %s: %s", self.path, exc)
                    self._last_failure_log_at = now
                if self.stop.wait(0.5):
                    break
                continue
            self.delivered += 1
            self.last_success_at = time.time()
            retry = None
