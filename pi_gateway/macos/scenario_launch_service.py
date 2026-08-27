#!/usr/bin/env python3
"""Manage the MacBook scenario as a true one-shot per-user launchd service."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile


LABEL = "com.reclaim.scenario-runner"
DOMAIN = f"gui/{os.getuid()}"


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args], check=check, capture_output=True, text=True
    )


def stop() -> None:
    result = _run("bootout", f"{DOMAIN}/{LABEL}", check=False)
    if result.returncode != 0:
        _run("remove", LABEL, check=False)


def pid() -> int | None:
    result = _run("print", f"{DOMAIN}/{LABEL}", check=False)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        key, separator, value = line.strip().partition(" = ")
        if key == "pid" and separator and value.isdigit():
            return int(value)
    return None


def start(plist_path: Path, log_path: Path, command: list[str]) -> None:
    if not command:
        raise ValueError("scenario command is required")
    stop()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": command,
        "RunAtLoad": True,
        "KeepAlive": False,
        "ProcessType": "Background",
        "StandardOutPath": str(log_path),
        "StandardErrorPath": str(log_path),
    }
    fd, temporary = tempfile.mkstemp(
        dir=plist_path.parent, prefix=".scenario-launch.", suffix=".plist"
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            plistlib.dump(payload, stream)
        os.chmod(temporary, 0o600)
        os.replace(temporary, plist_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    _run("bootstrap", DOMAIN, str(plist_path))


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("pid")
    subparsers.add_parser("stop")
    starter = subparsers.add_parser("start")
    starter.add_argument("--plist", type=Path, required=True)
    starter.add_argument("--log", type=Path, required=True)
    starter.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if args.action == "pid":
        process_id = pid()
        if process_id is None:
            return 1
        print(process_id)
        return 0
    if args.action == "stop":
        stop()
        return 0
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    start(args.plist, args.log, command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
