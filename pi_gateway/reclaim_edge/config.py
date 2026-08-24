"""RECLAIM Edge Gateway — configuration.

Typed config loaded from YAML (or defaults). One config object is threaded through
the whole service. Deployment secrets live in the YAML selected by
RECLAIM_EDGE_CONFIG with mode 0600, never in code.

Author: LJW.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List
from urllib.parse import urlparse

try:
    import yaml  # pyyaml
except Exception:  # pragma: no cover - yaml optional for defaults-only runs
    yaml = None

# The measurement-layer manifest field names. THIS IS THE CONTRACT.
# Must equal the engine ingest names == /manifest names == /state names.
# Flat per-channel scalars (one tag = one field), sent raw to the cloud where the
# engine fuses the TC banks. Bed core = sub-catalyst TC bank (TI 1003/1004/1008/1011);
# IR pyrometer (IR 1001) is the surface reference; wall bank = TI 1012/1013.
MANIFEST_MEASURED_FIELDS: List[str] = [
    "T_bed_tc1", "T_bed_tc2", "T_bed_tc3", "T_bed_tc4",   # bed-core TC bank -> T_bed_meas
    "T_bed_surf",                                          # IR pyrometer (surface)
    "T_wall_tc1", "T_wall_tc2",                            # wall TC bank -> T_wall_meas
    "P_fwd",
    "P_refl",
    "P_chamber",
    "O2_pct",                                              # OI 1007 (plastics only)
    "mass_in_g", "mass_out_g",                             # WI 1005 / WI 1004
]


@dataclass
class Config:
    # identity
    src: str = "reclaim-crio-01"
    run_id: str = ""                 # generated once at gateway start when empty
    mode: str = "live"                # live | replay | harness
    schema_version: str = "reclaim.telemetry.v1"

    # Seam A — source -> gateway/scenario receiver
    listen_host: str = "0.0.0.0"       # bind to LAN interface
    listen_port: int = 9070

    # Legacy direct cloud transport. Current deployments keep this on console;
    # Convene internal routing owns cloud-engine delivery.
    transport: str = "console"          # console | https | mqtts
    cloud_url: str = "https://vm.example/ingest"   # https mode
    mqtt_host: str = "vm.example"       # mqtts mode
    mqtt_port: int = 8883
    mqtt_topic: str = "reclaim/telemetry"
    auth_token: str = ""                # bearer token (https) / password (mqtts)
    tls_ca: str = ""                    # path to CA bundle (optional)
    verify_tls: bool = True

    # Independent best-effort raw telemetry tap -> Convene (exact source names).
    # This never participates in the durable VM queue or its acknowledgements.
    convene_enabled: bool = False
    convene_api: str = "https://reservation-backend-25386666460.us-central1.run.app/api"
    convene_credentials_path: str = "~/.convene_agent.json"
    convene_timeout_s: float = 10.0

    # buffer (store-and-forward)
    buffer_path: str = "/var/lib/reclaim-edge/queue.db"
    buffer_max_frames: int = 500_000    # drop-oldest beyond this

    # runtime
    publish_batch: int = 50             # frames per publish cycle
    publish_interval_s: float = 0.5
    health_interval_s: float = 10.0

    # Preserve the real LabVIEW schema until the cloud adapter normalizes it.
    # Set true only after the cRIO's complete raw field manifest is maintained here.
    strict_fields: bool = False

    # drop a silent cRIO connection after this many seconds so a half-open
    # socket (cRIO power-cycle without FIN) cannot wedge the receiver (fix H2).
    # Set to at least several telemetry periods; 0 disables the idle drop.
    conn_idle_timeout_s: float = 30.0

    # Maximum UTF-8 source line size including its terminating LF. The receiver
    # enforces this while buffering, before an LF is allowed to arrive.
    max_line_bytes: int = 8192

    # read-only loopback status endpoint; do not expose it through a tunnel; 0 = off
    status_port: int = 9080

    fields: List[str] = field(default_factory=lambda: list(MANIFEST_MEASURED_FIELDS))

    _VALID_TRANSPORTS = ("console", "https", "mqtts")
    _VALID_MODES = ("live", "replay", "harness")

    @classmethod
    def load(cls, path: str | None = None) -> "Config":
        """Load config, FAILING FAST on misconfiguration (review fix H7).

        The old behavior silently fell back to all-defaults (transport=console)
        when the file was missing or pyyaml absent — a typo'd path produced a
        healthy-looking gateway that published nothing to the cloud. Now:
          * an explicitly configured path (argument or RECLAIM_EDGE_CONFIG) that
            does not exist raises;
          * a file that exists but cannot be parsed raises;
          * unknown keys raise (they are almost always typos of real settings);
          * invalid transport/mode values raise;
          * only the implicit default path may be absent (dev convenience), and
            that is logged loudly.
        """
        import logging
        log = logging.getLogger("reclaim_edge.config")
        explicit = path or os.environ.get("RECLAIM_EDGE_CONFIG")
        path = explicit or "/etc/reclaim-edge/config.yaml"
        if not os.path.exists(path):
            if explicit:
                raise FileNotFoundError(
                    f"configured gateway config not found: {path} "
                    "(refusing to run on defaults — fix the path or create the file)")
            log.warning("no config at default %s — running on built-in defaults "
                        "(transport=console). This is a DEV mode only.", path)
            return cls()
        if yaml is None:
            raise RuntimeError(
                f"config file {path} exists but pyyaml is not installed — "
                "install pyyaml; refusing to silently ignore the configuration")
        with open(path) as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ValueError(f"config {path} must be a YAML mapping")
        unknown = sorted(k for k in data if k not in cls.__dataclass_fields__)
        if unknown:
            raise ValueError(
                f"unknown config key(s) in {path}: {unknown} — probably a typo; "
                f"valid keys: {sorted(cls.__dataclass_fields__)}")
        cfg = cls(**data)
        if cfg.transport not in cls._VALID_TRANSPORTS:
            raise ValueError(f"transport must be one of {cls._VALID_TRANSPORTS}, "
                             f"got '{cfg.transport}'")
        if cfg.mode not in cls._VALID_MODES:
            raise ValueError(f"mode must be one of {cls._VALID_MODES}, got '{cfg.mode}'")
        if (isinstance(cfg.max_line_bytes, bool) or
                not isinstance(cfg.max_line_bytes, int) or
                not 128 <= cfg.max_line_bytes <= 1_048_576):
            raise ValueError("max_line_bytes must be an integer from 128 through 1048576")
        if cfg.transport == "https":
            parsed_url = urlparse(cfg.cloud_url)
            if parsed_url.scheme != "https" or not parsed_url.hostname:
                raise ValueError("https transport requires an absolute https cloud_url")
            if parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment:
                raise ValueError("cloud_url must not contain credentials, query parameters, or a fragment")
            if parsed_url.path.rstrip("/") != "/ingest":
                raise ValueError("cloud_url must target the production /ingest path")

        if cfg.transport == "https" and cfg.mode == "live":
            placeholder_markers = ("placeholder", "changeme", "not_provisioned", "example")
            if not cfg.auth_token:
                raise ValueError("live https transport requires auth_token "
                                 "(the cloud ingest bearer token)")
            if any(marker in cfg.auth_token.lower() for marker in placeholder_markers):
                raise ValueError("live https auth_token is still a placeholder")
            if any(marker in cfg.cloud_url.lower() for marker in placeholder_markers):
                raise ValueError("live https cloud_url is still a placeholder")
            if not cfg.verify_tls:
                raise ValueError("live https transport requires verify_tls=true")
        elif not cfg.verify_tls:
            log.warning("verify_tls is DISABLED — acceptable only on an isolated "
                        "bench, never for the flight/production link")
        if cfg.convene_enabled:
            convene_url = urlparse(cfg.convene_api)
            if convene_url.scheme != "https" or not convene_url.hostname:
                raise ValueError("convene_enabled requires an absolute https convene_api")
            if (convene_url.username or convene_url.password or convene_url.query or
                    convene_url.fragment or convene_url.path.rstrip("/") != "/api"):
                raise ValueError("convene_api must be a credential-free HTTPS /api URL")
            if not cfg.convene_credentials_path:
                raise ValueError("convene_enabled requires convene_credentials_path")
            if cfg.convene_timeout_s <= 0:
                raise ValueError("convene_timeout_s must be positive")
        return cfg
