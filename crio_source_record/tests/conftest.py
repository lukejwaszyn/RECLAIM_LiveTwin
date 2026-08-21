"""Put the sibling source packages on the path so the mapping tests exercise the
REAL gateway framer and the REAL cloud ingest/adapter — not a stub. This is what
makes the end-to-end assertions meaningful: a change in ``labview_map`` or the
gateway framer that breaks the source-record contract fails here."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _sub in ("", "pi_gateway", "cloud_engine"):
    _p = _REPO_ROOT / _sub if _sub else _REPO_ROOT
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
