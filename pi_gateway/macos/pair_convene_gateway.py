#!/usr/bin/env python3
"""Pair this MacBook to Convene for unprefixed raw gateway publishing.

This intentionally does not install or run Convene's general-purpose agent,
remote terminal, command polling, VNC bridge, or public desktop tunnel.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import tempfile
from typing import Any

import requests
import yaml


BACKEND = "https://reservation-backend-25386666460.us-central1.run.app/api"
DEFAULT_CREDENTIAL = Path.home() / ".convene_agent.json"
DEFAULT_CONFIG = Path.home() / "Library/Application Support/RECLAIM/edge-gateway/config.yaml"


def extract_pairing_code(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    codes = set(re.findall(r"--code\s+([A-Fa-f0-9]{8})\b", text))
    if len(codes) != 1:
        raise ValueError("installer must contain exactly one eight-hex pairing code")
    return codes.pop().upper()


def pair(code: str, machine_name: str, *, session=requests) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Fa-f0-9]{8}", code):
        raise ValueError("pairing code must be eight hexadecimal characters")
    if not machine_name.strip():
        raise ValueError("machine name must not be empty")
    response = session.post(
        BACKEND + "/machine/pair",
        json={
            "pairingCode": code.upper(),
            "name": machine_name,
            "hostname": platform.node(),
            "os": "macos",
            "arch": platform.machine(),
            "agentVersion": "reclaim-gateway-1.0",
        },
        timeout=15,
    )
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise ValueError("pairing response was not a JSON object")
    if not isinstance(value.get("machineId"), str) or not value["machineId"]:
        raise ValueError("pairing response did not contain machineId")
    if not isinstance(value.get("agentToken"), str) or not value["agentToken"]:
        raise ValueError("pairing response did not contain agentToken")
    return value


def private_atomic_json(path: Path, value: dict[str, Any]) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ValueError("existing credential is accessible by group/others")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_name(f"{path.name}.bak.{stamp}")
        shutil.copy2(path, backup)
        backup.chmod(0o600)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".convene.")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, separators=(",", ":"))
            handle.write("\n")
        temporary.chmod(0o600)
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)
    return backup


def enable_gateway_convene(config_path: Path, credential_path: Path) -> Path:
    if not config_path.is_file():
        raise ValueError(f"gateway config does not exist: {config_path}")
    if stat.S_IMODE(config_path.stat().st_mode) & 0o077:
        raise ValueError("gateway config is accessible by group/others")
    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError("gateway config must be a YAML mapping")
    config.update(
        {
            "convene_enabled": True,
            "convene_api": BACKEND,
            "convene_credentials_path": str(credential_path),
        }
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = config_path.with_name(f"{config_path.name}.bak.before-convene.{stamp}")
    shutil.copy2(config_path, backup)
    backup.chmod(0o600)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=config_path.parent, prefix=".config.convene.", suffix=".yaml"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            yaml.safe_dump(config, handle, sort_keys=False)
        temporary.chmod(0o600)
        os.replace(temporary, config_path)
        config_path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)
    return backup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pair the MacBook raw-data publisher")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--installer", help="installer containing the supplied pairing code")
    source.add_argument("--pairing-code", action="store_true", help="prompt invisibly for code")
    parser.add_argument("--machine-name", default="lukejwaszyn")
    parser.add_argument("--credential", default=str(DEFAULT_CREDENTIAL))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(argv)

    code = (
        extract_pairing_code(Path(args.installer).expanduser().resolve())
        if args.installer
        else getpass.getpass("Convene pairing code (hidden): ").strip()
    )
    credential_path = Path(args.credential).expanduser().resolve()
    config_path = Path(args.config).expanduser().resolve()
    result = pair(code, args.machine_name)
    code = ""
    credential_backup = private_atomic_json(credential_path, result)
    config_backup = enable_gateway_convene(config_path, credential_path)
    print(f"Paired restricted MacBook scenario host machine: {result['machineId']}")
    print(f"Credential stored privately: {credential_path}")
    if credential_backup:
        print(f"Previous credential backup: {credential_backup}")
    print(f"Previous gateway config backup: {config_backup}")
    print("No remote terminal, command poller, screen sharing, or desktop tunnel was installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
