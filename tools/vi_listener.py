"""Bounded raw TCP listener for emulating a LabVIEW VI endpoint.

This is a diagnostic tool, not a telemetry gateway.  It binds one local
interface, accepts one peer at a time, optionally sends a caller-supplied
request, and records bytes received from the peer without interpreting them.
Capture files are never overwritten.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, TextIO


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def capture_connection(
    conn: socket.socket,
    address: tuple[str, int],
    capture: BinaryIO,
    index: TextIO,
    max_capture_bytes: int,
    idle_timeout: float,
    request: bytes = b"",
    chunk_size: int = 65536,
) -> int:
    """Capture one connection and return the number of bytes written.

    A request is opt-in because sending unknown bytes to a real control peer
    must be a deliberate operator action.  If the byte limit would be
    exceeded, the connection is stopped before writing a partial chunk.
    """
    if request:
        conn.sendall(request)
    conn.settimeout(idle_timeout)
    captured = 0
    while True:
        try:
            data = conn.recv(chunk_size)
        except socket.timeout:
            break
        if not data:
            break
        if captured + len(data) > max_capture_bytes:
            raise RuntimeError(
                f"capture exceeds {max_capture_bytes} bytes; stopping without truncation"
            )
        digest = hashlib.sha256(data).hexdigest().upper()
        capture.write(data)
        capture.flush()
        index.write(json.dumps({
            "ts": utc_now(),
            "peer": f"{address[0]}:{address[1]}",
            "offset": captured,
            "bytes": len(data),
            "sha256": digest,
        }, separators=(",", ":")) + "\n")
        index.flush()
        captured += len(data)
        print(json.dumps({"event": "peer_data", "bytes": len(data),
                          "total_bytes": captured}, separators=(",", ":")),
              flush=True)
    return captured


def serve(
    host: str,
    port: int,
    output: Path,
    max_capture_bytes: int,
    idle_timeout: float,
    request: bytes = b"",
    once: bool = False,
) -> int:
    """Run the listener until interrupted, or once when ``once`` is true."""
    index_path = Path(str(output) + ".index.jsonl")
    if output.exists() or index_path.exists():
        raise FileExistsError("capture or index already exists; refusing to overwrite evidence")
    output.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, port))
        listener.listen(1)
        with output.open("xb") as capture, index_path.open(
            "x", encoding="utf-8", newline="\n"
        ) as index:
            print(json.dumps({
                "event": "listening",
                "endpoint": f"{host}:{port}",
                "capture": str(output),
                "index": str(index_path),
            }, separators=(",", ":")), flush=True)
            while True:
                conn, address = listener.accept()
                print(json.dumps({"event": "peer_connected",
                                  "peer": f"{address[0]}:{address[1]}"},
                                 separators=(",", ":")), flush=True)
                try:
                    with conn:
                        total += capture_connection(
                            conn, address, capture, index, max_capture_bytes - total,
                            idle_timeout, request=request,
                        )
                except (ConnectionError, OSError, RuntimeError) as exc:
                    print(json.dumps({"event": "connection_error", "error": str(exc)},
                                     separators=(",", ":")), file=sys.stderr, flush=True)
                finally:
                    print(json.dumps({"event": "peer_disconnected",
                                      "total_bytes": total}, separators=(",", ":")),
                          flush=True)
                if once:
                    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded raw TCP VI-emulation listener")
    parser.add_argument("--host", default="192.168.12.114",
                        help="local interface to bind (default: 192.168.12.114)")
    parser.add_argument("--port", type=int, default=9070)
    parser.add_argument("--output", type=Path, required=True,
                        help="new binary capture path; existing files are refused")
    parser.add_argument("--max-capture-bytes", type=int, default=8192)
    parser.add_argument("--idle-timeout", type=float, default=25.0)
    parser.add_argument("--request", default="",
                        help="optional ASCII request sent after connect, e.g. GET")
    parser.add_argument("--once", action="store_true",
                        help="stop after the first peer disconnects")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.max_capture_bytes < 1 or args.idle_timeout <= 0:
        parser.error("capture limit must be positive and --idle-timeout must be greater than zero")
    if any(ord(char) > 127 for char in args.request):
        parser.error("--request must contain ASCII characters")
    try:
        serve(args.host, args.port, args.output, args.max_capture_bytes,
              args.idle_timeout, request=args.request.encode("ascii"), once=args.once)
    except OSError as exc:
        if exc.errno == errno.EADDRNOTAVAIL:
            print(
                f"error: {args.host} is not assigned to this computer; "
                "use this Mac's LAN address (currently likely 192.168.12.33) "
                "or --host 0.0.0.0 to listen on all interfaces",
                file=sys.stderr,
            )
            return 2
        raise
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
