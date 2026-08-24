#!/usr/bin/env python3
"""Replay a Windows 10 desktop data-stream capture into the MacBook scenario host.

The input is data, never instructions. Each non-empty telemetry line is parsed
as comma-separated ``name: value`` scalars and wrapped in the canonical scenario
envelope expected by the local gateway receiver.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import time
from pathlib import Path
from typing import Any, Iterator


NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
INTEGER_RE = re.compile(r"^[+-]?\d+$")


def scalar(text: str) -> bool | int | float | str | None:
    value = text.strip()
    upper = value.upper()
    if upper == "TRUE":
        return True
    if upper == "FALSE":
        return False
    if upper == "NAN":
        return None
    if INTEGER_RE.fullmatch(value):
        return int(value)
    number = float(value)
    if not (-float("inf") < number < float("inf")):
        raise ValueError("non-finite number")
    return number


def parse_record(line: str) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    for item in line.strip().split(","):
        if ":" not in item:
            raise ValueError(f"record item has no colon: {item!r}")
        name, value = item.split(":", 1)
        name = name.strip()
        if not NAME_RE.fullmatch(name):
            raise ValueError(f"invalid channel name: {name!r}")
        if name in variables:
            raise ValueError(f"duplicate channel: {name}")
        if name == "active_chamber":
            chamber = value.strip().upper()
            if chamber not in {"PL", "MT", "NONE"}:
                raise ValueError("active_chamber must be PL, MT, or NONE")
            variables[name] = chamber
            continue
        parsed = scalar(value)
        # NaN is LabVIEW's unavailable-sensor marker. It cannot be represented
        # in strict JSON or published to Convene, so omit only that reading.
        if parsed is not None:
            variables[name] = parsed
    if not variables:
        raise ValueError("empty record")
    return variables


def records(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="ascii") as handle:
        for line_number, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped or (line_number == 1 and "," not in stripped):
                continue
            try:
                yield parse_record(stripped)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc


def inferred_chamber(variables: dict[str, Any]) -> str:
    declared = variables.get("active_chamber")
    if declared in {"PL", "MT", "NONE"}:
        return str(declared)
    if any(variables.get(name) is True for name in (
        "PL_preprocess", "PL_process", "PL_postprocess"
    )):
        return "PL"
    return "NONE"


def replay(
    path: Path,
    host: str,
    port: int,
    rate_hz: float,
    speed: float,
    max_frames: int,
    source_op_state: str,
    active_chamber: str,
) -> int:
    if rate_hz <= 0 or speed <= 0 or max_frames < 0:
        raise ValueError("rate/speed must be positive and max_frames non-negative")
    source_id = f"reclaim-file-scenario:{path.stem}"
    cycle_id = f"file-replay-{path.stem}"
    sent = 0
    with socket.create_connection((host, port), timeout=5) as connection:
        for variables in records(path):
            payload = dict(variables)
            declared_chamber = payload.pop("active_chamber", None)
            if active_chamber == "auto":
                chamber = (str(declared_chamber) if declared_chamber is not None
                           else inferred_chamber(payload))
            else:
                chamber = active_chamber
            frame = {
                "source_id": source_id,
                "cycle_id": cycle_id,
                "source_op_state": source_op_state,
                "active_chamber": chamber,
                "vars": payload,
            }
            connection.sendall(
                (json.dumps(frame, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
            )
            sent += 1
            if max_frames and sent >= max_frames:
                break
            time.sleep(1.0 / (rate_hz * speed))
    return sent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay Windows capture as MacBook scenario data")
    parser.add_argument("capture", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9070)
    parser.add_argument("--rate-hz", type=float, default=1.0)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--source-op-state", default="S_Unknown")
    parser.add_argument("--active-chamber", choices=("auto", "PL", "MT", "NONE"), default="auto")
    args = parser.parse_args(argv)
    count = replay(
        args.capture.expanduser().resolve(), args.host, args.port,
        args.rate_hz, args.speed, args.max_frames,
        args.source_op_state, args.active_chamber,
    )
    print(f"Replayed {count} scenario frames from {args.capture}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
