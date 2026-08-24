from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

import yaml


def test_requested_sigterm_is_a_clean_shutdown(tmp_path):
    config = tmp_path / "gateway.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "listen_host": "127.0.0.1",
                "listen_port": 0,
                "status_port": 0,
                "transport": "console",
                "buffer_path": str(tmp_path / "queue.db"),
                "health_interval_s": 60,
            }
        ),
        encoding="utf-8",
    )
    gateway_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["RECLAIM_EDGE_CONFIG"] = str(config)
    env["PYTHONPATH"] = str(gateway_root)
    process = subprocess.Popen(
        [sys.executable, "-m", "reclaim_edge.main"],
        cwd=gateway_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        time.sleep(0.75)
        process.terminate()
        output, _ = process.communicate(timeout=8)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)

    assert process.returncode == 0, output
    assert "shutdown requested" in output
    assert "stopped" in output
    assert "worker thread" not in output
