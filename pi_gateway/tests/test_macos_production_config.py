from __future__ import annotations

from pathlib import Path
import sys

import pytest


MACOS = Path(__file__).resolve().parents[1] / "macos"
if str(MACOS) not in sys.path:
    sys.path.insert(0, str(MACOS))

from configure_production_interfaces import configure, main  # noqa: E402


def test_macbook_production_configuration_is_retired():
    with pytest.raises(RuntimeError, match="Windows 10 desktop"):
        configure()


def test_retired_cli_fails_closed(capsys):
    assert main() == 2
    assert "scenario-only" in capsys.readouterr().err
