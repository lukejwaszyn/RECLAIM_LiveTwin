"""Best-effort Convene audit publisher for the Windows desktop gateway.

This path is deliberately independent of the durable cloud publisher. Each
canonical cRIO frame is flattened to ``gw_`` scalar variables and submitted to
Convene's connected-machine ``/machine/publish`` endpoint. A one-frame queue
coalesces during outages so Convene can never block cRIO receipt or VM delivery.
"""
from __future__ import annotations

import json
import logging
import math
import os
import queue
import threading
import time
from typing import Any, Dict

from .config import Config

log = logging.getLogger("reclaim_edge.convene")

_ENVELOPE_FIELDS = (
    "schema_version",
    "mode",
    "run_id",
    "source_id",
    "cycle_id",
    "seq",
    "ts",
    "source_op_state",
    "active_chamber",
)


def _scalar(value: Any) -> bool:
    if value is None or not isinstance(value, (str, int, float, bool)):
        return False
    return not isinstance(value, float) or math.isfinite(value)


def frame_to_variables(frame: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten one canonical frame to the desktop-only ``gw_`` namespace."""
    variables: Dict[str, Any] = {}
    for name in _ENVELOPE_FIELDS:
        value = frame.get(name)
        if _scalar(value):
            variables[f"gw_{name}"] = value

    raw = frame.get("vars")
    if isinstance(raw, dict):
        for name, value in raw.items():
            if isinstance(name, str) and name and _scalar(value):
                variables[f"gw_{name}"] = value

    if any(name.startswith("sim_") for name in variables):  # defense in depth
        raise ValueError("desktop Convene publisher must never produce sim_ variables")
    return variables


class ConvenePublisher(threading.Thread):
    """Nonblocking latest-frame publisher; never participates in VM acking."""

    def __init__(self, cfg: Config, stop: threading.Event):
        super().__init__(name="convene-audit", daemon=True)
        import requests

        self.cfg = cfg
        self.stop = stop
        self._requests = requests
        self._pending: queue.Queue[Dict[str, Any]] = queue.Queue(maxsize=1)
        self._token: str | None = None
        self.machine_id: str | None = None
        self.delivered = 0
        self.failed = 0
        self.coalesced = 0
        self.last_success_at = 0.0
        self._last_failure_log_at = 0.0

    def submit(self, frame: Dict[str, Any]) -> None:
        """Queue without waiting; replace an older pending audit frame if full."""
        try:
            self._pending.put_nowait(frame)
            return
        except queue.Full:
            pass
        try:
            self._pending.get_nowait()
            self.coalesced += 1
        except queue.Empty:  # consumer won the race
            pass
        try:
            self._pending.put_nowait(frame)
        except queue.Full:  # another producer won; receiver still never blocks
            self.coalesced += 1

    def _load_credential(self) -> None:
        path = os.path.expandvars(os.path.expanduser(self.cfg.convene_credentials_path))
        with open(path, encoding="utf-8-sig") as fh:
            credential = json.load(fh)
        token = credential.get("agentToken")
        machine_id = credential.get("machineId")
        if not isinstance(token, str) or not token or not isinstance(machine_id, str):
            raise ValueError("credential must contain agentToken and machineId")
        self._token = token
        self.machine_id = machine_id

    def _deliver(self, frame: Dict[str, Any]) -> bool:
        if self._token is None:
            self._load_credential()
        variables = frame_to_variables(frame)
        if not variables:
            raise ValueError("canonical frame produced no scalar gw_ variables")
        response = self._requests.post(
            f"{self.cfg.convene_api.rstrip('/')}/machine/publish",
            json={"variables": variables},
            headers={"X-Agent-Token": self._token},
            timeout=self.cfg.convene_timeout_s,
        )
        if response.status_code in (401, 403):
            self._token = None  # permit a repaired/rotated credential on retry
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"HTTP {response.status_code}")
        return True

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                frame = self._pending.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._deliver(frame)
                self.delivered += 1
                self.last_success_at = time.time()
            except Exception as exc:
                self.failed += 1
                now = time.time()
                if now - self._last_failure_log_at >= 30.0:
                    log.warning("gw_ audit publish failed (%d total): %s",
                                self.failed, exc)
                    self._last_failure_log_at = now

    @property
    def last_success_age(self) -> float | None:
        return time.time() - self.last_success_at if self.last_success_at else None
