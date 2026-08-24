#!/usr/bin/env python3
"""Retired guard: the MacBook is not an authorized live/cloud gateway."""

from __future__ import annotations

import sys


MESSAGE = (
    "REFUSED: the MacBook is scenario-only. The Windows 10 desktop remains "
    "the live-data client/gateway. Use configure_scenario_host.py on macOS."
)


def configure(*_args, **_kwargs):
    raise RuntimeError(MESSAGE)


def main() -> int:
    print(MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
