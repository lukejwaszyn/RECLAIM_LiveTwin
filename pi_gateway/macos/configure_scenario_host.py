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


def configure(config_path: Path) -> Path:
    if not config_path.is_file():
        raise ValueError(f"gateway configuration does not exist: {config_path}")
    if stat.S_IMODE(config_path.stat().st_mode) & 0o077:
        raise ValueError("gateway configuration must be private (mode 0600)")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("gateway configuration must be a YAML mapping")

    raw.update(
        {
            "src": "reclaim-macbook-scenario-01",
            "run_id": "",
            "mode": "harness",
            "listen_host": "127.0.0.1",
            "transport": "console",
            "cloud_url": "https://disabled.invalid/ingest",
            "auth_token": "",
            "verify_tls": True,
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
    print("Direct cloud transport is disabled; Convene settings are unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
