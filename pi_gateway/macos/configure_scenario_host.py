#!/usr/bin/env python3
"""Lock a MacBook scenario host install to scenario-only operation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

import yaml


GATEWAY_ROOT = Path(__file__).resolve().parents[1]
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

from reclaim_edge.config import Config  # noqa: E402


DEFAULT_CONFIG = Path.home() / "Library/Application Support/RECLAIM/edge-gateway/config.yaml"
DEFAULT_FILE_WATCH = (
    Path.home()
    / "Library/Application Support/RECLAIM/scenarios/convene_file_watch.txt"
)


def configure(config_path: Path) -> Path:
    if not config_path.is_file():
        raise ValueError(f"gateway configuration does not exist: {config_path}")
    if stat.S_IMODE(config_path.stat().st_mode) & 0o077:
        raise ValueError("gateway configuration must be private (mode 0600)")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("gateway configuration must be a YAML mapping")

    for unused_convene_key in (
        "convene_api",
        "convene_credentials_path",
        "convene_timeout_s",
    ):
        raw.pop(unused_convene_key, None)

    raw.update(
        {
            "src": "reclaim-macbook-scenario-01",
            "run_id": "",
            "mode": "harness",
            "listen_host": "127.0.0.1",
            "transport": "console",
            "cloud_url": "https://disabled.invalid/ingest",
            "mqtt_host": "disabled.invalid",
            "auth_token": "",
            "verify_tls": True,
            "convene_enabled": False,
            "file_watch_enabled": True,
            "file_watch_path": str(DEFAULT_FILE_WATCH),
        }
    )

    descriptor, temporary_name = tempfile.mkstemp(
        dir=config_path.parent, prefix=".config.scenario.", suffix=".yaml"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            yaml.safe_dump(raw, handle, sort_keys=False)
        temporary.chmod(0o600)
        cfg = Config.load(str(temporary))
        if cfg.mode != "harness" or cfg.listen_host != "127.0.0.1":
            raise ValueError("scenario configuration did not fail closed")
        if cfg.transport != "console" or cfg.auth_token:
            raise ValueError("scenario host must not have direct cloud transport")
        if cfg.convene_enabled or not cfg.file_watch_enabled:
            raise ValueError("scenario host must use local File Watch only")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = config_path.with_name(f"{config_path.name}.bak.before-scenario.{stamp}")
        shutil.copy2(config_path, backup)
        backup.chmod(0o600)
        os.replace(temporary, config_path)
        config_path.chmod(0o600)
        return backup
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lock MacBook to scenario-only operation")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    backup = configure(args.config.expanduser().resolve())
    print("MacBook configured as a loopback-only scenario host.")
    print(f"Previous protected configuration: {backup}")
    print("Direct cloud/API publishing is disabled; Convene File Watch is enabled.")
    print(f"File Watch text file: {DEFAULT_FILE_WATCH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
