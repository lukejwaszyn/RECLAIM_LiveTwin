"""Narrow authenticated client for the engine's loopback state read."""

from __future__ import annotations

import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import BridgeFailure


class StateClient:
    def __init__(self, url: str, bearer_token: str, timeout_s: float):
        if not bearer_token:
            raise ValueError("StateClient requires a bearer credential")
        self._url = url
        self._token = bearer_token
        self._timeout_s = timeout_s

    def fetch(self) -> object:
        request = Request(
            self._url,
            headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=self._timeout_s) as response:
                if response.status != 200:
                    raise BridgeFailure(
                        "engine_unavailable", "HTTP_STATUS", "engine returned non-success"
                    )
                body = response.read(2_000_001)
                if len(body) > 2_000_000:
                    raise BridgeFailure(
                        "invalid_json", "STATE_TOO_LARGE", "engine state exceeded size limit"
                    )
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise BridgeFailure(
                    "unauthorized", "ENGINE_UNAUTHORIZED", "engine rejected read credential"
                ) from exc
            raise BridgeFailure(
                "engine_unavailable", "HTTP_STATUS", "engine returned non-success"
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise BridgeFailure(
                "engine_unavailable", "ENGINE_TIMEOUT", "engine read timed out"
            ) from exc
        except (URLError, ConnectionError, OSError) as exc:
            raise BridgeFailure(
                "engine_unavailable", "ENGINE_UNAVAILABLE", "engine could not be reached"
            ) from exc
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeFailure(
                "invalid_json", "INVALID_JSON", "engine response was not valid JSON"
            ) from exc
