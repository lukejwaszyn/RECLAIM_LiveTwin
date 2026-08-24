from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "pi_gateway" / "macos" / "audit-scenario-host.sh"
RUNNER = ROOT / "pi_gateway" / "macos" / "start-rehearsal-scenario.sh"


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


def test_scenario_runner_defaults_to_one_fast_bounded_cycle():
    text = RUNNER.read_text(encoding="utf-8")
    assert 'speed=${RECLAIM_SCENARIO_SPEED:-}' in text
    assert 'emit_hz=${RECLAIM_SCENARIO_EMIT_HZ:-1}' in text
    assert 'cycles=${RECLAIM_SCENARIO_CYCLES:-1}' in text
    assert '--emit-hz "$emit_hz"' in text
    assert 'scenario=power_outage' in text
    assert 'environment=lunar_surface' in text
    assert 'speed=4.285714285714286' in text
    assert 'speed=1.3333333333333333' in text
