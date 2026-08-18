"""Independent loopback state-to-file publication service."""

from __future__ import annotations

import argparse
from logging import Formatter, Logger, StreamHandler, getLogger
from logging.handlers import RotatingFileHandler
from pathlib import Path
import signal
import threading
import time

from . import __version__
from .client import StateClient
from .config import BridgeConfig, read_bearer_secret
from .contract import enrich, iso_utc, utc_now, validate_live_state
from .errors import BridgeFailure
from .writer import AtomicJSONWriter, AtomicWriteError, SingletonLock


LOG = getLogger("reclaim.convene_bridge")


class StateBridge:
    def __init__(
        self,
        config: BridgeConfig,
        client: StateClient,
        writer: AtomicJSONWriter,
        *,
        health_writer: AtomicJSONWriter | None = None,
        logger: Logger = LOG,
        now=utc_now,
    ):
        self.config = config
        self.client = client
        self.writer = writer
        self.health_writer = health_writer
        self.log = logger
        self._now = now
        self._last_good: dict = {}
        self._identity: tuple[str, str] | None = None
        self._last_seq: int | None = None
        self._last_success_at: str | None = None
        self._consecutive_failures = 0

    def publish_starting(self) -> bool:
        observed = self._now()
        payload = enrich(
            {},
            self.config,
            observed_at=observed,
            live=False,
            status="starting",
            error_code="BRIDGE_STARTING",
        )
        return self._publish(payload, "starting", "BRIDGE_STARTING", observed)

    def run_once(self) -> bool:
        observed = self._now()
        try:
            raw = self.client.fetch()
            state = validate_live_state(raw, self.config.freshness_limit_ms)
            identity = (state["run_id"], state["source_id"])
            seq = state["seq"]
            if self._identity == identity and self._last_seq is not None and seq < self._last_seq:
                raise BridgeFailure(
                    "sequence_regression",
                    "SEQUENCE_REGRESSION",
                    "sequence regressed within the active identity",
                )
            payload = enrich(
                state,
                self.config,
                observed_at=observed,
                live=True,
                status="ok",
                error_code="NONE",
            )
        except BridgeFailure as exc:
            self._consecutive_failures += 1
            payload = enrich(
                self._last_good,
                self.config,
                observed_at=observed,
                live=False,
                status=exc.status,
                error_code=exc.code,
            )
            self.log.warning(
                "poll failed status=%s code=%s consecutive_failures=%d",
                exc.status,
                exc.code,
                self._consecutive_failures,
            )
            return self._publish(payload, exc.status, exc.code, observed)

        if not self._publish(payload, "ok", "NONE", observed):
            return False
        if self._identity is not None and identity != self._identity:
            self.log.info(
                "accepted state identity transition old_run=%s old_source=%s "
                "new_run=%s new_source=%s",
                self._identity[0],
                self._identity[1],
                identity[0],
                identity[1],
            )
        self._identity = identity
        self._last_seq = seq
        self._last_good = state
        self._last_success_at = payload[
            "bridge_observed_at"
            if self.config.prefix_mode == "passthrough"
            else "sim_bridge_observed_at"
        ]
        self._consecutive_failures = 0
        self.log.info(
            "published live state run=%s source=%s seq=%d",
            identity[0],
            identity[1],
            seq,
        )
        return True

    def _publish(self, payload: dict, status: str, code: str, observed) -> bool:
        try:
            self.writer.write(payload)
        except (AtomicWriteError, OSError, ValueError):
            self._consecutive_failures += 1
            self.log.error(
                "atomic publication failed code=WRITE_FAILED consecutive_failures=%d; "
                "downstream lease will expire",
                self._consecutive_failures,
            )
            self._write_health("write_failed", "WRITE_FAILED", observed, live=False)
            return False
        self._write_health(status, code, observed, live=status == "ok")
        return True

    def _write_health(self, status: str, code: str, observed, *, live: bool) -> None:
        if self.health_writer is None:
            return
        record = {
            "bridge_status": status,
            "bridge_error_code": code,
            "bridge_observed_at": observed.isoformat().replace("+00:00", "Z"),
            "data_live": live,
            "last_successful_poll": iso_utc(observed) if live else self._last_success_at,
            "consecutive_failures": self._consecutive_failures,
        }
        try:
            self.health_writer.write(record)
        except (AtomicWriteError, OSError, ValueError):
            self.log.error("local health record write failed")

    def run_forever(self, stop_event: threading.Event) -> None:
        self.publish_starting()
        while not stop_event.is_set():
            started = time.monotonic()
            self.run_once()
            remaining = self.config.poll_interval_s - (time.monotonic() - started)
            if remaining > 0:
                stop_event.wait(remaining)


def configure_logging(config: BridgeConfig) -> None:
    log_path = Path(config.log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    console_handler = StreamHandler()
    console_handler.setFormatter(formatter)
    LOG.handlers.clear()
    LOG.addHandler(file_handler)
    LOG.addHandler(console_handler)
    LOG.setLevel("INFO")
    LOG.propagate = False


def build_bridge(config: BridgeConfig) -> StateBridge:
    token = read_bearer_secret(config)
    client = StateClient(config.engine_state_url, token, config.request_timeout_s)
    writer = AtomicJSONWriter(
        config.output_path,
        retry_timeout_s=config.replace_retry_timeout_s,
        retry_interval_s=config.replace_retry_interval_s,
    )
    health_writer = AtomicJSONWriter(config.health_path)
    return StateBridge(config, client, writer, health_writer=health_writer)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RECLAIM Convene state bridge")
    parser.add_argument("--config", required=True, help="non-secret YAML configuration path")
    args = parser.parse_args(argv)
    config = BridgeConfig.load(args.config)
    configure_logging(config)
    bridge = build_bridge(config)
    stop_event = threading.Event()

    def stop(_signum, _frame):
        stop_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, stop)
    LOG.info(
        "bridge start version=%s bridge_source_sha=%s engine_source_sha=%s config=%s",
        __version__,
        config.bridge_source_sha,
        config.engine_source_sha,
        args.config,
    )
    with SingletonLock(config.lock_path):
        bridge.run_forever(stop_event)
    LOG.info("bridge stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
