"""RECLAIM Edge Gateway — retained direct publisher compatibility path.

Drains the durable buffer. Current deployments select ``console`` because Convene
internal routing owns engine delivery. Retained pluggable transports:
  - console : local testing (E0), prints frames, always "delivers"
  - https   : POST batched NDJSON to the cloud /ingest route (bearer token, TLS)
  - mqtts   : publish to a broker topic (paho, QoS 1, TLS)

Delivery follows the v1.1 ingest ack contract (review fix C1/H3):

    The cloud answers 200 with per-frame `results` [{i, status, code, final}].
    - accepted / duplicate  -> ack (remove from queue)
    - rejected + final=true -> DEAD-LETTER (remove from queue, keep auditable
      with the reason; e.g. timestamp_stale after an outage, run_superseded)
    - rejected + final=false-> keep queued and retry (transient engine error)
    - transport/HTTP failure-> keep everything queued, exponential backoff

    A server that predates `results` (pre-1.1) acks the whole batch on 2xx,
    matching the old behavior. Nothing is ever acked without a 2xx response,
    so at-least-once delivery is preserved; the cloud's persisted monotone
    sequence makes the retries idempotent.

Author: LJW.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import List, Optional, Tuple

from .buffer import Buffer
from .config import Config

log = logging.getLogger("reclaim_edge.publisher")

# One disposition per payload: ("ack" | "dead" | "retry", reason)
Disposition = Tuple[str, str]


class _Transport:
    def deliver(self, payloads: List[str]) -> Optional[List[Disposition]]:
        """Return one disposition per payload, or None on total transport failure."""
        raise NotImplementedError


class ConsoleTransport(_Transport):
    def deliver(self, payloads: List[str]) -> Optional[List[Disposition]]:
        for p in payloads:
            print("[deliver]", p, flush=True)
        return [("ack", "console")] * len(payloads)


class HttpsTransport(_Transport):
    def __init__(self, cfg: Config):
        import requests  # local import so mqtts-only installs don't need it
        self._requests = requests
        self.cfg = cfg
        self.headers = {"Content-Type": "application/json"}
        if cfg.auth_token:
            self.headers["Authorization"] = f"Bearer {cfg.auth_token}"
        self.verify = cfg.tls_ca or cfg.verify_tls
        # Latest ControlCommand returned by the digital twin in the /ingest
        # response — the gateway is the bidirectional relay: telemetry up,
        # CommandSignal back down to the control hub / HMI, which polls it from
        # the local status endpoint (GET /command).
        self.last_command: dict | None = None
        self.last_command_at: float = 0.0

    def deliver(self, payloads: List[str]) -> Optional[List[Disposition]]:
        body = "\n".join(payloads)   # NDJSON; cloud /ingest splits on \n
        try:
            r = self._requests.post(
                self.cfg.cloud_url, data=body, headers=self.headers,
                verify=self.verify, timeout=10,
            )
        except Exception as exc:
            log.warning("https deliver failed: %s", exc)
            return None
        if r.status_code == 401:
            # Auth failure is not transient — surface it loudly, keep frames.
            log.error("cloud rejected bearer token (401) — check RECLAIM_INGEST_TOKEN "
                      "on both ends; frames retained")
            return None
        if not (200 <= r.status_code < 300):
            log.warning("cloud returned HTTP %d; frames retained", r.status_code)
            return None
        try:
            resp = r.json()
            results = resp.get("results")
            cmd = resp.get("command")
            if isinstance(cmd, dict):
                self.last_command = cmd
                self.last_command_at = time.time()
        except ValueError:
            results = None
        if not isinstance(results, list) or len(results) != len(payloads):
            # pre-1.1 server: 2xx means the whole batch was processed.
            return [("ack", "http-2xx")] * len(payloads)
        out: List[Disposition] = []
        for res in results:
            status = res.get("status")
            if status in ("accepted", "duplicate"):
                out.append(("ack", status))
            elif res.get("final", True):
                out.append(("dead", str(res.get("code") or "rejected")))
            else:
                out.append(("retry", str(res.get("code") or "transient")))
        return out


class MqttsTransport(_Transport):
    """MQTT has no per-frame application ack; QoS 1 publish confirmation is the
    ack. Connection is LAZY (review fix M6): a broker that is down at boot must
    not kill the publisher thread — it becomes a retryable delivery failure."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = None

    def _connect(self):
        import paho.mqtt.client as mqtt
        client = mqtt.Client()
        if self.cfg.auth_token:
            client.username_pw_set(self.cfg.src, self.cfg.auth_token)
        client.tls_set(ca_certs=self.cfg.tls_ca or None)
        client.connect(self.cfg.mqtt_host, self.cfg.mqtt_port, keepalive=30)
        client.loop_start()
        self.client = client

    def deliver(self, payloads: List[str]) -> Optional[List[Disposition]]:
        try:
            if self.client is None:
                self._connect()
            out: List[Disposition] = []
            for p in payloads:
                info = self.client.publish(self.cfg.mqtt_topic, p, qos=1)
                info.wait_for_publish(timeout=5)
                if info.is_published():
                    out.append(("ack", "qos1"))
                else:
                    # stop at first unconfirmed publish; retry the remainder
                    out.extend([("retry", "unconfirmed")] * (len(payloads) - len(out)))
                    break
            return out
        except Exception as exc:
            log.warning("mqtts deliver failed: %s", exc)
            try:
                if self.client is not None:
                    self.client.loop_stop()
            except Exception:
                pass
            self.client = None       # force reconnect next cycle
            return None


def make_transport(cfg: Config) -> _Transport:
    return {
        "console": ConsoleTransport,
        "https": HttpsTransport,
        "mqtts": MqttsTransport,
    }[cfg.transport](cfg) if cfg.transport != "console" else ConsoleTransport()


class Publisher(threading.Thread):
    def __init__(self, cfg: Config, buffer: Buffer, stop: threading.Event):
        super().__init__(name="publisher", daemon=True)
        self.cfg = cfg
        self.buffer = buffer
        self.stop = stop
        self.transport = make_transport(cfg)
        self.delivered = 0
        self.dead_lettered = 0
        self.last_ack = time.time()
        self._backoff = 1.0

    def run(self) -> None:
        while not self.stop.is_set():
            batch: List[Tuple[int, str]] = self.buffer.dequeue_batch(self.cfg.publish_batch)
            if not batch:
                time.sleep(self.cfg.publish_interval_s)
                continue
            payloads = [p for _, p in batch]
            disp = self.transport.deliver(payloads)
            if disp is None:
                time.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, 30.0)  # exp backoff, cap 30s
                continue
            ack_ids: List[int] = []
            dead: List[Tuple[int, str, str]] = []
            retry = 0
            for (fid, payload), (action, reason) in zip(batch, disp):
                if action == "ack":
                    ack_ids.append(fid)
                elif action == "dead":
                    dead.append((fid, payload, reason))
                else:
                    retry += 1
            if ack_ids:
                self.buffer.ack(ack_ids)
                self.delivered += len(ack_ids)
                self.last_ack = time.time()
            if dead:
                self.buffer.dead_letter(dead)
                self.dead_lettered += len(dead)
                reasons = {}
                for _, _, r in dead:
                    reasons[r] = reasons.get(r, 0) + 1
                log.warning("dead-lettered %d frame(s) rejected as final by cloud: %s",
                            len(dead), reasons)
            if retry:
                log.info("%d frame(s) transient-rejected; will retry", retry)
                time.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, 30.0)
            else:
                self._backoff = 1.0

    @property
    def last_ack_age(self) -> float:
        return time.time() - self.last_ack

    @property
    def last_command(self) -> dict | None:
        """Latest twin ControlCommand from the cloud (https transport only)."""
        return getattr(self.transport, "last_command", None)

    @property
    def last_command_age(self) -> float | None:
        at = getattr(self.transport, "last_command_at", 0.0)
        return (time.time() - at) if at else None
