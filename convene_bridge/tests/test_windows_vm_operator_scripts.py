from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT = ROOT / "deployment"
WINDOWS_VM = DEPLOYMENT / "windows-vm"


def test_proven_windows_vm_operator_workflows_are_published() -> None:
    expected = {
        "Deploy-ProvenScalarStateRelease.ps1",
        "Get-ConvenePublicationDiagnostics.ps1",
        "Register-ConveneAgentTask.ps1",
        "Test-ConveneLiveExpiry.ps1",
        "Test-EnginePublicAcceptance.ps1",
        "recovery/Reregister-EngineService.ps1",
        "recovery/Reregister-StateBridgeService.ps1",
    }
    actual = {
        path.relative_to(WINDOWS_VM).as_posix()
        for path in WINDOWS_VM.rglob("*.ps1")
    }
    assert actual == expected


def test_public_acceptance_scripts_require_operator_supplied_https_origin() -> None:
    for name in ("Test-ConveneLiveExpiry.ps1", "Test-EnginePublicAcceptance.ps1"):
        source = (WINDOWS_VM / name).read_text(encoding="utf-8")
        assert "[Parameter(Mandatory)]" in source
        assert "[ValidatePattern('^https://')]" in source
        assert "$PublicUrl" in source
        assert "trycloudflare.com" not in source


def test_no_codex_temporary_deployment_scripts_remain() -> None:
    assert not list(DEPLOYMENT.glob("codex-*.tmp.ps1"))


def test_recap_and_operator_index_reference_the_proven_workflows() -> None:
    recap = (DEPLOYMENT / "CONVENE_MISSION_OPERATIONS_RECAP.md").read_text(
        encoding="utf-8"
    )
    index = (WINDOWS_VM / "README.md").read_text(encoding="utf-8")
    assert "convene-live-b7856411f837" in recap
    assert "Test-ConveneLiveExpiry.ps1" in recap
    assert "Test-EnginePublicAcceptance.ps1" in index
    assert "Get-ConvenePublicationDiagnostics.ps1" in index
