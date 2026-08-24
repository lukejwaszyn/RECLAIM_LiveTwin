from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VM = ROOT / "deployment" / "windows-vm"


def test_only_current_vm_entry_points_are_active():
    assert sorted(path.name for path in VM.iterdir()) == [
        "Audit-ConveneRoutedEngine.ps1",
        "README.md",
        "Test-ConveneRoutedEngineContract.ps1",
    ]


def test_vm_audit_detects_known_competing_components_without_reading_secrets():
    text = (VM / "Audit-ConveneRoutedEngine.ps1").read_text(encoding="utf-8")
    for marker in (
        "RECLAIMStateBridge",
        "cloudflared",
        "sim_vars.json",
        "normalize_convene_frame",
        "_coerce_file_watch_value",
        "RawIngressMetadata",
        "convene-routed-frame",
        "convene_result_variables",
        "ReadyForSupervisedContractTest",
    ):
        assert marker in text
    assert "RECLAIM_INGEST_TOKEN" not in text
    assert "RECLAIM_READ_TOKEN" not in text


def test_endpoint_mutation_requires_an_explicit_switch_and_existing_tokens():
    text = (VM / "Test-ConveneRoutedEngineContract.ps1").read_text(encoding="utf-8")
    assert "[switch]$ExerciseEndpoint" in text
    assert "if (-not $ExerciseEndpoint)" in text
    assert "RECLAIM_INGEST_TOKEN" in text
    assert "RECLAIM_READ_TOKEN" in text
    assert "redteam_ingest.py" in text


def test_deprecated_state_bridge_is_not_importable_from_active_tree():
    assert not (ROOT / "convene_bridge").exists()
    assert not (ROOT / "tools" / "three_path_acceptance.py").exists()
    assert not (ROOT / "tools" / "rehearsal_convene.py").exists()
    assert not (ROOT / "cloud_engine" / "windows" / "start-rehearsal-scenario.ps1").exists()
