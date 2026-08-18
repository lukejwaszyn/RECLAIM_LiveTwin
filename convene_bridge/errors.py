"""Stable, non-secret bridge failure classifications."""

from __future__ import annotations


class BridgeFailure(Exception):
    """A failure safe to classify in the published bridge status."""

    def __init__(self, status: str, code: str, detail: str):
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail
