"""Transparent localhost proxy for observing the working LabVIEW cRIO socket.

The proxy listens only on loopback, forwards bytes unchanged in both directions,
and records only cRIO-to-VI bytes. It does not connect to the RECLAIM gateway.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import select
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def relay_connection(
    vi: socket.socket,
    crio: socket.socket,
    capture,
    index,
    captured: int,
    max_capture_bytes: int,
) -> int:
    peers = {vi: crio, crio: vi}
    while True:
        readable, _, _ = select.select([vi, crio], [], [], 1.0)
        for source in readable:
            data = source.recv(65536)
            if not data:
                return captured
            peers[source].sendall(data)
            if source is crio:
                if captured + len(data) > max_capture_bytes:
                    raise RuntimeError(
                        f"capture exceeds {max_capture_bytes} bytes; stopping without truncation"
                    )
                offset = captured
                capture.write(data)
                capture.flush()
                captured += len(data)
                index.write(json.dumps({
                    "ts": utc_now(),
                    "offset": offset,
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest().upper(),
                }, separators=(",", ":")) + "\n")
                index.flush()
                print(json.dumps({
                    "event": "crio_data",
                    "bytes": len(data),
                    "total_bytes": captured,
                }, separators=(",", ":")), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-port", type=int, default=19070)
    parser.add_argument("--crio-host", default="192.168.1.2")
    parser.add_argument("--crio-port", type=int, default=9070)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-capture-bytes", type=int, default=64 * 1024 * 1024)
    args = parser.parse_args()

    if not 1 <= args.listen_port <= 65535 or not 1 <= args.crio_port <= 65535:
        parser.error("ports must be between 1 and 65535")
    if args.max_capture_bytes < 1:
        parser.error("--max-capture-bytes must be positive")

    output = args.output.resolve()
    index_path = Path(str(output) + ".index.jsonl")
    if output.exists() or index_path.exists():
        raise FileExistsError("capture or index already exists; refusing to overwrite evidence")

    output.parent.mkdir(parents=True, exist_ok=True)
    captured = 0
    with output.open("xb") as capture, index_path.open("x", encoding="utf-8", newline="\n") as index:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", args.listen_port))
            listener.listen(1)
            print(json.dumps({
                "event": "listening",
                "vi_endpoint": f"127.0.0.1:{args.listen_port}",
                "crio_endpoint": f"{args.crio_host}:{args.crio_port}",
                "capture": str(output),
                "index": str(index_path),
            }, separators=(",", ":")), flush=True)

            while True:
                vi, address = listener.accept()
                print(json.dumps({"event": "vi_connected", "peer": f"{address[0]}:{address[1]}"},
                                 separators=(",", ":")), flush=True)
                try:
                    with vi, socket.create_connection(
                        (args.crio_host, args.crio_port), timeout=5.0
                    ) as crio:
                        crio.settimeout(None)
                        captured = relay_connection(
                            vi, crio, capture, index, captured, args.max_capture_bytes
                        )
                except (ConnectionError, OSError) as exc:
                    print(json.dumps({"event": "connection_error", "error": str(exc)},
                                     separators=(",", ":")), file=sys.stderr, flush=True)
                finally:
                    print(json.dumps({"event": "vi_disconnected", "captured": captured},
                                     separators=(",", ":")), flush=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
