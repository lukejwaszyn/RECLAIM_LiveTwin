from __future__ import annotations

from dataclasses import replace

import pytest

from convene_bridge.config import BridgeConfig, read_bearer_secret


def test_default_url_is_strict_loopback_state(bridge_config):
    bridge_config.validate()


def test_non_loopback_url_requires_separately_named_override(bridge_config, monkeypatch):
    monkeypatch.setattr(
        "convene_bridge.config.socket.getaddrinfo",
        lambda *_args: [(2, 1, 6, "", ("192.0.2.1", 8078))],
    )
    remote = replace(bridge_config, engine_state_url="http://engine.example:8078/state")
    with pytest.raises(ValueError, match="loopback"):
        remote.validate()
    replace(remote, allow_non_loopback_state_url=True).validate()


@pytest.mark.parametrize(
    "url",
    [
        "ftp://127.0.0.1/state",
        "http://127.0.0.1/command",
        "http://127.0.0.1/ingest",
        "http://user:secret@127.0.0.1/state",
        "http://127.0.0.1/state?mode=write",
    ],
)
def test_source_url_must_be_exact_read_surface(bridge_config, url):
    with pytest.raises(ValueError):
        replace(bridge_config, engine_state_url=url).validate()


def test_live_mode_refuses_missing_or_empty_secret(bridge_config, tmp_path):
    with pytest.raises(ValueError, match="requires"):
        read_bearer_secret(bridge_config)
    secret = tmp_path / "read-token.txt"
    secret.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        read_bearer_secret(replace(bridge_config, secret_file=str(secret)))


def test_secret_file_accepts_raw_or_named_value(bridge_config, tmp_path):
    secret = tmp_path / "read-token.txt"
    secret.write_text("test-read-credential\n", encoding="utf-8")
    assert read_bearer_secret(replace(bridge_config, secret_file=str(secret))) == "test-read-credential"
    secret.write_text("RECLAIM_READ_TOKEN=test-read-credential\n", encoding="utf-8")
    assert read_bearer_secret(replace(bridge_config, secret_file=str(secret))) == "test-read-credential"


def test_placeholder_sha_and_short_lease_are_rejected(bridge_config):
    with pytest.raises(ValueError, match="revision"):
        replace(bridge_config, engine_source_sha="REPLACE_WITH_FULL_SHA").validate()
    with pytest.raises(ValueError, match="bridge_source_sha"):
        replace(bridge_config, bridge_source_sha="REPLACE_WITH_FULL_SHA").validate()
    with pytest.raises(ValueError, match="lease"):
        replace(bridge_config, lease_duration_ms=4_000).validate()
