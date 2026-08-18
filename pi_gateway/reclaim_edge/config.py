"""RECLAIM Edge Gateway — configuration.

Typed config loaded from YAML (or defaults). One config object is threaded through
the whole service. On the Windows 10 deployment, secrets (tokens/certs) live in
the YAML selected by RECLAIM_EDGE_CONFIG under a restricted NTFS ACL, never in
code.

Author: LJW.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

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

    # Seam A — cRIO -> Windows 10 gateway laptop (trusted LAN, plaintext TCP)
    listen_host: str = "0.0.0.0"       # bind to LAN interface
    listen_port: int = 9070

    # Seam B — Windows 10 gateway laptop -> cloud (TLS)
    transport: str = "console"          # console | https | mqtts
    cloud_url: str = "https://vm.example/ingest"   # https mode
    mqtt_host: str = "vm.example"       # mqtts mode
    mqtt_port: int = 8883
    mqtt_topic: str = "reclaim/telemetry"
    auth_token: str = ""                # bearer token (https) / password (mqtts)
    tls_ca: str = ""                    # path to CA bundle (optional)
    verify_tls: bool = True

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
        if cfg.transport == "https" and cfg.mode == "live" and not cfg.auth_token:
            raise ValueError("live https transport requires auth_token "
                             "(the cloud ingest bearer token)")
        if not cfg.verify_tls:
            log.warning("verify_tls is DISABLED — acceptable only on an isolated "
                        "bench, never for the flight/production link")
        return cfg
