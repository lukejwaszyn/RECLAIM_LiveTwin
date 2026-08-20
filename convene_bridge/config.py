"""Strict non-secret configuration for the Windows VM state bridge."""

from __future__ import annotations

from dataclasses import dataclass, fields
import ipaddress
from pathlib import Path
import re
import socket
from urllib.parse import urlsplit

import yaml


_FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")


@dataclass(frozen=True)
class BridgeConfig:
    engine_state_url: str = "http://127.0.0.1:8078/state"
    poll_interval_s: float = 1.0
    request_timeout_s: float = 3.0
    freshness_limit_ms: int = 15_000
    publisher_heartbeat_ms: int = 30_000
    lease_duration_ms: int = 45_000
    output_path: str = r"C:\ConveneAgent\sim_vars.json"
    prefix_mode: str = "passthrough"
    environment: str = "earth_lab"
    engine_source_sha: str = "REPLACE_WITH_FULL_SHA"
    bridge_source_sha: str = "REPLACE_WITH_FULL_SHA"
    bridge_instance_id: str = "reclaim-engine-2-state-bridge"
    secret_file: str = (
        r"C:\ProgramData\RECLAIM\convene-bridge\secrets\read-token.txt"
    )
    lock_path: str = (
        r"C:\ProgramData\RECLAIM\convene-bridge\state\bridge.lock"
    )
    health_path: str = (
        r"C:\ProgramData\RECLAIM\convene-bridge\state\health.json"
    )
    log_path: str = (
        r"C:\ProgramData\RECLAIM\convene-bridge\logs\bridge.log"
    )
    replace_retry_timeout_s: float = 2.0
    replace_retry_interval_s: float = 0.05
    allow_non_loopback_state_url: bool = False
    live_mode: bool = True

    @classmethod
    def load(cls, path: str | Path) -> "BridgeConfig":
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        if not isinstance(raw, dict):
            raise ValueError("bridge configuration must be a YAML mapping")
        allowed = {field.name for field in fields(cls)}
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise ValueError(f"unknown bridge configuration keys: {unknown}")
        config = cls(**raw)
        config.validate()
        return config

    def validate(self) -> None:
        if self.poll_interval_s <= 0:
            raise ValueError("poll_interval_s must be positive")
        if self.request_timeout_s <= 0:
            raise ValueError("request_timeout_s must be positive")
        if isinstance(self.freshness_limit_ms, bool) or self.freshness_limit_ms < 0:
            raise ValueError("freshness_limit_ms must be a non-negative integer")
        if isinstance(self.lease_duration_ms, bool) or self.lease_duration_ms <= 0:
            raise ValueError("lease_duration_ms must be a positive integer")
        if (
            isinstance(self.publisher_heartbeat_ms, bool)
            or self.publisher_heartbeat_ms <= 0
        ):
            raise ValueError("publisher_heartbeat_ms must be a positive integer")
        minimum_lease = max(
            (self.poll_interval_s + self.request_timeout_s) * 1000,
            self.publisher_heartbeat_ms,
        )
        if self.lease_duration_ms <= minimum_lease:
            raise ValueError(
                "lease_duration_ms must exceed both the downstream publisher heartbeat "
                "and one poll interval plus request timeout"
            )
        if self.replace_retry_timeout_s < 0 or self.replace_retry_interval_s <= 0:
            raise ValueError("replacement retry settings must be positive")
        if self.prefix_mode not in {"passthrough", "sim"}:
            raise ValueError("prefix_mode must be 'passthrough' or 'sim'")
        for name in ("environment", "bridge_instance_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        for name in ("engine_source_sha", "bridge_source_sha"):
            if not _FULL_SHA.fullmatch(getattr(self, name)):
                raise ValueError(f"{name} must be an exact 40- or 64-hex revision")
        for name in ("output_path", "secret_file", "lock_path", "health_path", "log_path"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a non-empty path")
        self._validate_state_url()

    def _validate_state_url(self) -> None:
        parsed = urlsplit(self.engine_state_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("engine_state_url must use http or https")
        if not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("engine_state_url must contain a host and no credentials")
        if parsed.path.rstrip("/") != "/state" or parsed.query or parsed.fragment:
            raise ValueError("engine_state_url must target exactly /state without query data")
        if self.allow_non_loopback_state_url:
            return
        host = parsed.hostname
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port)}
        except socket.gaierror as exc:
            raise ValueError("engine_state_url host could not be resolved") from exc
        if not addresses or any(not ipaddress.ip_address(addr).is_loopback for addr in addresses):
            raise ValueError(
                "engine_state_url must resolve only to loopback unless "
                "allow_non_loopback_state_url is explicitly true"
            )


def read_bearer_secret(config: BridgeConfig) -> str:
    """Read the bearer credential without placing it in arguments or logs."""
    path = Path(config.secret_file)
    if not path.exists():
        if config.live_mode:
            raise ValueError("live mode requires the configured read-token file")
        return ""
    if path.stat().st_size > 8192:
        raise ValueError("read-token file is unexpectedly large")
    value = path.read_text(encoding="utf-8").strip()
    if value.startswith("RECLAIM_READ_TOKEN="):
        value = value.partition("=")[2].strip()
    if config.live_mode and not value:
        raise ValueError("live mode requires a non-empty read bearer credential")
    if any(char in value for char in "\r\n\0"):
        raise ValueError("read-token file must contain exactly one credential")
    return value
