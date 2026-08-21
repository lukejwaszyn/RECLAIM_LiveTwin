"""crio_source_record/conformance.py — frame conformance checker.

A self-test the cRIO producer team runs on candidate frames BEFORE the live window.
It validates each line against the exact contract our gateway enforces on receipt —
the same `parse_line` + `Framer.build` path the real receiver uses — so a producer can
confirm its output will be accepted without touching the gateway or the cRIO.

Two stages:

* GATEWAY (default, deterministic): the byte bound (<= max_line_bytes including the LF),
  strict UTF-8 decode, `parse_line` (a JSON object carrying a `vars` object), and
  `Framer.build` (finite-number/boolean vars). Passing this means the gateway receiver
  will accept and enqueue the line.
* CLOUD (`--cloud`, optional): additionally reports the real cloud disposition
  (`DualPushEngine.ingest_line`) — schema/mode, envelope completeness, timestamp
  freshness, known `source_op_state`, chamber, and bed-bank completeness. Because
  freshness is wall-clock relative, use `--refresh-ts` to stamp each frame with the
  current time when you only want to check structure and semantics of a canned file.

Usage:
    python -m crio_source_record.conformance frames.ndjson
    python -m crio_source_record.conformance --cloud --refresh-ts frames.ndjson
    some_producer | python -m crio_source_record.conformance -

Exit code 0 iff every non-empty line passes the gateway contract (and, with `--cloud`,
is not cloud-`rejected`; a `duplicate` is not a failure). This module opens no socket
and touches no cRIO.

Author: RECLAIM repository developer (offline).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Make the checker runnable standalone (no pytest/conftest): put the sibling
# source packages on the path so it binds the REAL framer and cloud.
_REPO_ROOT = Path(__file__).resolve().parents[1]
for _sub in ("pi_gateway", "cloud_engine"):
    _p = str(_REPO_ROOT / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from reclaim_edge.config import Config           # noqa: E402
from reclaim_edge.framer import Framer, FrameContractError, parse_line  # noqa: E402

DEFAULT_MAX_LINE_BYTES = 8192

__all__ = ["LineResult", "check_frames", "main"]


@dataclass
class LineResult:
    index: int
    ok: bool                       # passed the gateway contract
    stage: str                     # "gateway" | "cloud" | "ok"
    detail: str
    byte_len: int                  # payload bytes + 1 (LF)
    cloud_status: Optional[str] = None   # accepted | duplicate | rejected | None
    cloud_code: Optional[str] = None

    @property
    def cloud_failed(self) -> bool:
        return self.cloud_status == "rejected"


def check_frames(
    raw: bytes,
    *,
    cloud: bool = False,
    refresh_ts: bool = False,
    max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
) -> List[LineResult]:
    """Validate every LF-delimited frame in ``raw`` (the exact producer bytes)."""
    framer = Framer(Config())            # one framer -> seq increments, no false dupes
    engine = None
    if cloud:
        from push_ingest_dual import DualPushEngine
        engine = DualPushEngine(production=True)

    results: List[LineResult] = []
    segments = raw.split(b"\n")
    # A trailing LF yields a final empty segment; ignore empties (the receiver skips them).
    idx = 0
    for seg in segments:
        if seg.strip() == b"":
            continue
        idx += 1
        byte_len = len(seg) + 1          # include the terminating LF
        if byte_len > max_line_bytes:
            results.append(LineResult(idx, False, "gateway",
                                      f"line {byte_len} B exceeds {max_line_bytes} B bound",
                                      byte_len))
            continue
        try:
            text = seg.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            results.append(LineResult(idx, False, "gateway",
                                      f"not valid UTF-8: {exc}", byte_len))
            continue
        try:
            frame_in = parse_line(text)
            if refresh_ts and isinstance(frame_in, dict):
                frame_in["ts"] = datetime.now(timezone.utc).isoformat()
            frame, _warnings = framer.build(frame_in)
        except FrameContractError as exc:
            results.append(LineResult(idx, False, "gateway", str(exc), byte_len))
            continue

        if not cloud:
            results.append(LineResult(idx, True, "ok", "conforms", byte_len))
            continue

        disp = engine.ingest_line(frame)
        results.append(LineResult(
            idx, True, "ok", "conforms", byte_len,
            cloud_status=disp["status"], cloud_code=disp.get("code")))
    return results


def _format(r: LineResult, cloud: bool) -> str:
    if not r.ok:
        return f"line {r.index}: FAIL [{r.stage}] {r.detail}  ({r.byte_len} B)"
    if not cloud:
        return f"line {r.index}: PASS gateway  ({r.byte_len} B)"
    tag = r.cloud_status
    if r.cloud_status == "rejected":
        tag = f"rejected({r.cloud_code})"
    return f"line {r.index}: PASS gateway; cloud={tag}  ({r.byte_len} B)"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Validate candidate telemetry frames "
                                             "against the RECLAIM gateway contract.")
    ap.add_argument("path", help="file of LF-delimited frames, or '-' for stdin")
    ap.add_argument("--cloud", action="store_true",
                    help="also report the real cloud ingest disposition")
    ap.add_argument("--refresh-ts", action="store_true",
                    help="stamp each frame with the current UTC time before the cloud "
                         "check (structure/semantics only; ignores the sample's age)")
    ap.add_argument("--max-line-bytes", type=int, default=DEFAULT_MAX_LINE_BYTES)
    args = ap.parse_args(argv)

    raw = sys.stdin.buffer.read() if args.path == "-" else Path(args.path).read_bytes()
    results = check_frames(raw, cloud=args.cloud, refresh_ts=args.refresh_ts,
                           max_line_bytes=args.max_line_bytes)

    for r in results:
        print(_format(r, args.cloud))

    total = len(results)
    gateway_fail = sum(1 for r in results if not r.ok)
    cloud_fail = sum(1 for r in results if r.cloud_failed)
    print(f"\n{total} frame(s): {total - gateway_fail} conform, {gateway_fail} fail"
          + (f"; cloud rejected {cloud_fail}" if args.cloud else ""))
    return 1 if (gateway_fail or (args.cloud and cloud_fail)) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
