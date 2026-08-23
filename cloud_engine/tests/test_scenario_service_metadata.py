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
    history_state = service.history(1)[0]
    assert history_state["events"] == []
    assert {key: value for key, value in history_state.items() if key != "events"} == state
    assert service.health()["cycle"] == 1
    assert service.health()["status"] == "running"


def test_stopped_stream_does_not_keep_reporting_running():
    """A finished driver must stop advertising `status: running`.

    Regression for the loss-of-data rehearsal: the service kept reporting
    `running` over a record that could no longer change, so a consumer polling
    /state or /health could not distinguish a live stream from a stalled one.
    """
    from reclaim_predictive_engine.service import TwinStateService

    svc = TwinStateService(scenario="nominal", environment="earth_lab",
                           speed=2.0, feed="harness", port=8181)
    svc.update({"T_bed_est": 600.0}, t_sim=400.0, events=[], cycle=1)
    assert svc.state()["status"] == "running"
    live_history_len = len(svc.history(600))

    svc.mark_stopped()
    assert svc.state()["status"] == "stopped"
    assert svc.health()["status"] == "stopped"
    # the frozen values themselves must still be readable, just not called live
    assert svc.state()["t_sim"] == 400.0

    # history records what was true at the time; it is not rewritten
    assert len(svc.history(600)) == live_history_len
    assert svc.history(600)[-1]["status"] == "running"

    # idempotent, and a later update revives it
    svc.mark_stopped()
    assert svc.state()["status"] == "stopped"
    svc.update({"T_bed_est": 601.0}, t_sim=401.0, events=[], cycle=2)
    assert svc.state()["status"] == "running"
