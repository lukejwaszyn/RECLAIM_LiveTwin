#!/usr/bin/env python3
"""Fail CI when Git tracks common secret, runtime-state, or handoff artifacts."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = {
    ".db",
    ".jks",
    ".key",
    ".keystore",
    ".log",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
    ".zip",
}
FORBIDDEN_PARTS = {".venv", "__pycache__", ".pytest_cache", "artifacts", "test-results"}
TOKEN_PATTERNS = {
    "AWS access key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "GitHub token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    "private key": re.compile(rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / Path(raw.decode()) for raw in result.stdout.split(b"\0") if raw]


def main() -> int:
    findings: list[tuple[str, str]] = []
    for path in tracked_files():
        relative = path.relative_to(ROOT)
        lowered_parts = {part.lower() for part in relative.parts}
        name = relative.name.lower()

        if lowered_parts & FORBIDDEN_PARTS:
            findings.append((str(relative), "runtime/build directory is tracked"))
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            findings.append((str(relative), "forbidden secret/state/archive suffix is tracked"))
        if name == ".env" or (name.startswith(".env.") and not name.endswith(".example")):
            findings.append((str(relative), "environment file is tracked"))
        if name == "reclaim-ingest.env":
            findings.append((str(relative), "runtime secret environment file is tracked"))

        try:
            payload = path.read_bytes()
        except (OSError, UnicodeError):
            continue
        if len(payload) > 2_000_000:
            continue
        for label, pattern in TOKEN_PATTERNS.items():
            if pattern.search(payload):
                findings.append((str(relative), f"possible {label}"))

    if findings:
        print("Repository hygiene check failed:")
        for filename, reason in sorted(set(findings)):
            print(f"- {filename}: {reason}")
        return 1

    print("Repository hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
