"""Mac-side probe that emulates the LabVIEW Socket Test VI.

Connects to a cRIO TCP endpoint, sends the VI-style ASCII ``GET`` request,
and captures the raw response without interpreting or forwarding it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def probe(
    host: str,
    port: int,
    output: Path,
    request: bytes,
    max_capture_bytes: int,
    connect_timeout: float,
    idle_timeout: float,
) -> int:
    index_path = Path(str(output) + ".index.jsonl")
    if output.exists() or index_path.exists():
        raise FileExistsError("capture or index already exists; refusing to overwrite evidence")
    output.parent.mkdir(parents=True, exist_ok=True)

    with socket.create_connection((host, port), timeout=connect_timeout) as conn:
        conn.sendall(request)
        conn.settimeout(idle_timeout)
        captured = 0
        with output.open("xb") as capture, index_path.open(
            "x", encoding="utf-8", newline="\n"
        ) as index:
            while True:
                try:
                    data = conn.recv(8192)
                except socket.timeout:
                    break
                if not data:
                    break
                if captured + len(data) > max_capture_bytes:
                    raise RuntimeError(
                        f"response exceeds {max_capture_bytes} bytes; stopping without truncation"
                    )
                index.write(json.dumps({
                    "ts": utc_now(),
                    "offset": captured,
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest().upper(),
                }, separators=(",", ":")) + "\n")
                capture.write(data)
                capture.flush()
                index.flush()
                captured += len(data)
                print(json.dumps({"event": "crio_data", "bytes": len(data),
                                  "total_bytes": captured}, separators=(",", ":")),
                      flush=True)
    return captured


def timestamped_output(base: Path) -> Path:
    """Return a unique capture path derived from the requested base path."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    if base.suffix:
        return base.with_name(f"{base.stem}-{stamp}{base.suffix}")
    return base / f"crio-response-{stamp}.bin"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emulate the LabVIEW VI TCP client")
    parser.add_argument("--host", default="192.168.12.114")
    parser.add_argument("--port", type=int, default=9070)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request", default="GET",
                        help="ASCII request sent after connecting (default: GET)")
    parser.add_argument("--max-capture-bytes", type=int, default=8192)
    parser.add_argument("--connect-timeout", type=float, default=5.0)
    parser.add_argument("--idle-timeout", type=float, default=25.0)
    parser.add_argument("--repeat", type=int, default=1,
                        help="number of probes; 0 means run continuously")
    parser.add_argument("--interval", type=float, default=3.0,
                        help="seconds between probes in repeat mode")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.max_capture_bytes < 1 or args.connect_timeout <= 0 or args.idle_timeout <= 0:
        parser.error("capture limit and timeouts must be positive")
    if args.repeat < 0 or args.interval < 0:
        parser.error("--repeat must be non-negative and --interval cannot be negative")
    if any(ord(char) > 127 for char in args.request):
        parser.error("--request must contain ASCII characters")
    continuous = args.repeat == 0 or args.repeat > 1
    completed = 0
    while args.repeat == 0 or completed < args.repeat:
        output = timestamped_output(args.output) if continuous else args.output
        try:
            total = probe(args.host, args.port, output, args.request.encode("ascii"),
                          args.max_capture_bytes, args.connect_timeout, args.idle_timeout)
        except (ConnectionError, OSError, RuntimeError) as exc:
            print(json.dumps({"event": "probe_failed", "error": str(exc),
                              "host": args.host, "port": args.port},
                             separators=(",", ":")), file=sys.stderr, flush=True)
        else:
            completed += 1
            print(json.dumps({"event": "complete", "host": args.host, "port": args.port,
                              "capture": str(output), "total_bytes": total},
                             separators=(",", ":")), flush=True)
        if not continuous or (args.repeat and completed >= args.repeat):
            break
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
