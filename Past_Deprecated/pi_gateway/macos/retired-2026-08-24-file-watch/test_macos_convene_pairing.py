from __future__ import annotations

import json
from pathlib import Path
import sys

import yaml


MACOS = Path(__file__).resolve().parents[1] / "macos"
if str(MACOS) not in sys.path:
    sys.path.insert(0, str(MACOS))

from pair_convene_gateway import (  # noqa: E402
    enable_gateway_convene,
    extract_pairing_code,
    pair,
    private_atomic_json,
)


def test_extract_pairing_code_requires_one_code(tmp_path):
    installer = tmp_path / "setup.sh"
    installer.write_text("python agent.py --code FC63229D --desktop\n", encoding="utf-8")
    assert extract_pairing_code(installer) == "FC63229D"


def test_pair_uses_restricted_mac_identity_shape():
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"machineId": "machine-1", "agentToken": "token-1"}

    class Session:
        call = None

        @classmethod
        def post(cls, url, **kwargs):
            cls.call = (url, kwargs)
            return Response()

    result = pair("FC63229D", "lukejwaszyn", session=Session)
    assert result["machineId"] == "machine-1"
    url, request = Session.call
    assert url.endswith("/api/machine/pair")
    assert request["json"]["name"] == "lukejwaszyn"
    assert request["json"]["os"] == "macos"
    assert request["json"]["agentVersion"] == "reclaim-gateway-1.0"


def test_private_credential_and_gateway_enable(tmp_path):
    credential = tmp_path / "credential.json"
    private_atomic_json(
        credential, {"machineId": "machine-1", "agentToken": "token-1"}
    )
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump({"transport": "console", "convene_enabled": False}),
        encoding="utf-8",
    )
    config.chmod(0o600)

    backup = enable_gateway_convene(config, credential)
    written = yaml.safe_load(config.read_text(encoding="utf-8"))

    assert credential.stat().st_mode & 0o077 == 0
    assert written["transport"] == "console"
    assert written["convene_enabled"] is True
    assert written["convene_credentials_path"] == str(credential)
    assert backup.exists()
    assert json.loads(credential.read_text())["machineId"] == "machine-1"
