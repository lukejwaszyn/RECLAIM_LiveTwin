"""Atomic LabVIEW-style text publisher for Convene File Watch variables."""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
from typing import Any, Dict

from .config import Config
from .convene import LABVIEW_RAW_FIELDS

log = logging.getLogger("reclaim_edge.file_watch")


def _text_value(value: Any) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if value is None:
        return "NaN"
    if isinstance(value, float):
        return f"{value:.6f}" if math.isfinite(value) else "NaN"
    rendered = str(value)
    if "\n" in rendered or "\r" in rendered or "," in rendered:
        raise ValueError("File Watch scalar values cannot contain commas or newlines")
    return rendered


def frame_to_text(frame: Dict[str, Any]) -> str:
    """Render the current live-shaped record: chamber plus 34 raw fields."""
    active_chamber = frame.get("active_chamber")
    if active_chamber not in {"PL", "MT", "NONE"}:
        raise ValueError("File Watch frame requires active_chamber PL, MT, or NONE")
    items = [f"active_chamber: {active_chamber}"]
    raw = frame.get("vars")
    if not isinstance(raw, dict):
        raise ValueError("canonical frame must contain a vars object")
    if any(isinstance(name, str) and name.startswith("sim_") for name in raw):
        raise ValueError("raw telemetry must not contain cloud-owned sim_ names")
    # A File Watch heartbeat always sees the complete signed 34-field layout.
    # A scenario that does not model a channel marks it unavailable as NaN;
    # it never substitutes a measurement or silently removes the field.
    for name in LABVIEW_RAW_FIELDS:
        items.append(f"{name}: {_text_value(raw.get(name))}")
    return ", ".join(items) + "\n"


class FileWatchPublisher(threading.Thread):
    """Coalesce frames and atomically replace one owner-private text file."""

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
        record = frame_to_text(frame)
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
                handle.write(record)
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
