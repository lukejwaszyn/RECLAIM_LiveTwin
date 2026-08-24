from __future__ import annotations

from pathlib import Path

import yaml

from macos.configure_scenario_host import configure


def test_configure_locks_macbook_to_scenario_only(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "src": "live-source",
                "mode": "live",
                "listen_host": "0.0.0.0",
                "transport": "https",
                "cloud_url": "https://engine.example/ingest",
                "auth_token": "a-real-looking-token-value",
                "convene_enabled": False,
            }
        ),
        encoding="utf-8",
    )
    config.chmod(0o600)

    backup = configure(config)
    value = yaml.safe_load(config.read_text(encoding="utf-8"))

    assert backup.is_file()
    assert value["src"] == "reclaim-macbook-scenario-01"
    assert value["mode"] == "harness"
    assert value["listen_host"] == "127.0.0.1"
    assert value["transport"] == "console"
    assert value["cloud_url"] == "https://disabled.invalid/ingest"
    assert value["auth_token"] == ""
    assert value["convene_enabled"] is False
