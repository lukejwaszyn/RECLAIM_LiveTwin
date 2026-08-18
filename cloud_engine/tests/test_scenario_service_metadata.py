from reclaim_predictive_engine.service import TwinStateService


def test_health_identifies_rehearsal_profile_before_first_frame():
    service = TwinStateService(
        scenario="power_outage",
        environment="earth_lab",
        speed=12.0,
        feed="harness",
        host="127.0.0.1",
        port=8178,
    )

    assert service.health() == {
        "ok": True,
        "service": "reclaim-predictive-engine",
        "mode": "harness",
        "scenario": "power_outage",
        "environment": "earth_lab",
        "speed": 12.0,
        "feed": "harness",
        "host": "127.0.0.1",
        "port": 8178,
        "cycle": 0,
        "status": "starting",
        "t_sim": None,
    }


def test_state_and_history_retain_rehearsal_identity():
    service = TwinStateService(
        scenario="nominal",
        environment="lunar_surface",
        speed=6.0,
        feed="harness",
        host="127.0.0.1",
        port=8179,
    )

    service.update(
        {"op_state": "S_MicrowaveHeating", "P_fwd": 2200.0},
        t_sim=12.0,
        events=[],
        cycle=1,
    )

    state = service.state()
    assert state["mode"] == "harness"
    assert state["scenario"] == "nominal"
    assert state["environment"] == "lunar_surface"
    assert state["speed"] == 6.0
    assert state["status"] == "running"
    assert service.history(1) == [state]
    assert service.health()["cycle"] == 1
    assert service.health()["status"] == "running"
