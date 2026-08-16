#!/usr/bin/env python3
"""Build a deterministic, explicitly non-promotable release candidate."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path


VERSION_PATTERN = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?\Z")
ARCHIVE_PATHS = (
    "README.md",
    "cloud_engine",
    "convene",
    "deployment",
    "docs",
    "pi_gateway",
    "pyproject.toml",
    "uv.lock",
)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    parser.add_argument("--test-report", type=Path, action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not VERSION_PATTERN.fullmatch(args.version):
        raise SystemExit("--version must be a semantic version such as v0.1.0-rc.1")

    root = Path(__file__).resolve().parents[1]
    commit = git(root, "rev-parse", "HEAD")
    tree = git(root, "rev-parse", "HEAD^{tree}")
    commit_time = git(root, "show", "-s", "--format=%cI", "HEAD")
    if git(root, "status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("tracked files are dirty; commit the exact candidate source first")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"reclaim-livetwin-{args.version}"
    archive = args.output_dir / f"{stem}.tar.gz"

    with tempfile.TemporaryDirectory(prefix="reclaim-release-") as temp_dir:
        tar_path = Path(temp_dir) / f"{stem}.tar"
        subprocess.run(
            [
                "git",
                "archive",
                "--format=tar",
                f"--prefix={stem}/",
                f"--output={tar_path}",
                "HEAD",
                *ARCHIVE_PATHS,
            ],
            cwd=root,
            check=True,
        )
        with tar_path.open("rb") as source, archive.open("wb") as destination:
            with gzip.GzipFile(fileobj=destination, mode="wb", filename="", mtime=0) as zipped:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    zipped.write(chunk)

    reports = []
    for report in args.test_report:
        resolved = report if report.is_absolute() else root / report
        if not resolved.is_file():
            raise SystemExit(f"test report does not exist: {report}")
        reports.append({"name": report.name, "sha256": sha256(resolved)})

    manifest = {
        "schema": "reclaim.release-candidate.v1",
        "version": args.version,
        "source_commit": commit,
        "source_tree": tree,
        "built_at": commit_time,
        "artifact": {"name": archive.name, "sha256": sha256(archive)},
        "dependency_lock": {"name": "uv.lock", "sha256": sha256(root / "uv.lock")},
        "python_targets": ["3.11", "3.13"],
        "schemas": {
            "telemetry": "reclaim.telemetry.v1",
            "state": "reclaim.state.v1",
            "persistent_state_compatibility": "UNRESOLVED",
        },
        "test_reports": reports,
        "authority": "advisory",
        "signed": False,
        "production_promotable": False,
        "promotion_blockers": [
            "release signing identity and host trust policy are not approved",
            "persistent state and queue compatibility policy is not approved",
            "fixed pull-based production installers are not implemented",
        ],
    }
    manifest_path = args.output_dir / f"{stem}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    checksum_path = args.output_dir / f"{stem}.sha256"
    checksum_path.write_text(f"{manifest['artifact']['sha256']}  {archive.name}\n")

    print(archive)
    print(manifest_path)
    print(checksum_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
