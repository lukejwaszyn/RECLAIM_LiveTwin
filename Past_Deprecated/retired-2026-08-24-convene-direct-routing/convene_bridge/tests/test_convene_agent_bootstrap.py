from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[2] / "deployment" / "convene-setup-2.ps1"
).read_text(encoding="utf-8")


def test_headless_agent_bootstrap_carries_bridge_state_and_starts_at_boot():
    assert '[Parameter(Mandatory = $true)]' in SCRIPT
    assert '[string]$PairingCode,' in SCRIPT
    assert '[switch]$EnableDesktop' in SCRIPT
    assert 'SIM_VARS_FILE  = os.path.join(BASE_DIR, "sim_vars.json")' in SCRIPT
    assert 'payload["simVars"] = get_sim_vars()' in SCRIPT
    assert '"--pair-only" in sys.argv' in SCRIPT
    assert 'Register-ScheduledTask -TaskName $TaskName' in SCRIPT
    assert '$TaskName = "Convene-Agent"' in SCRIPT
    assert '-UserId "SYSTEM"' in SCRIPT


def test_default_install_does_not_start_desktop_streaming():
    assert '& $PythonExe convene_agent.py --code $PairingCode --pair-only' in SCRIPT
    assert 'python convene_agent.py --code 1079675C --desktop' not in SCRIPT
