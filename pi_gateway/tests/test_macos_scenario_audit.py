from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "pi_gateway" / "macos" / "audit-scenario-host.sh"


def test_scenario_audit_checks_route_ownership_and_complete_text_frame():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'h.get("transport") != "console"' in text
    assert 'h.get("convene", {}).get("enabled")' in text
    assert 'fw.get("enabled")' in text
    assert 'permissions" = "600"' in text
    assert 'field_count" = "35"' in text
    assert 'line_count" = "1"' in text


def test_scenario_audit_rejects_competing_engine_ports_but_not_screen_share():
    text = SCRIPT.read_text(encoding="utf-8")
    for port in ("8078", "8177", "8178", "8179", "8180", "8181"):
        assert port in text
    assert "6080" not in text
