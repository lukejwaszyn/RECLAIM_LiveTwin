from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT = ROOT / "deployment"
WINDOWS_VM = DEPLOYMENT / "windows-vm"


def test_proven_windows_vm_operator_workflows_are_published() -> None:
    expected = {
        "Deploy-ConveneVariableBindings.ps1",
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


def test_convene_variable_deployer_is_type_safe_and_credential_safe() -> None:
    source = (WINDOWS_VM / "Deploy-ConveneVariableBindings.ps1").read_text(
        encoding="utf-8"
    )

    assert "SupportsShouldProcess" in source
    assert "Assert-ScalarType" in source
    assert 'if ($variable -ne "sim_$field")' in source
    assert "CONVENE_AGENT_TOKEN" in source
    assert "C:\\ConveneAgent\\agent.ps1" in source
    assert "Language.Parser]::ParseFile" in source
    assert "Invoke-Expression" not in source
    assert "x-agent-token" in source
    assert "<YOUR_AGENT_TOKEN>" not in source
    assert "42.5" not in source
    assert "Write-Host $agentToken" not in source


def test_publication_diagnostics_can_inventory_flat_scalar_handoff() -> None:
    script = (WINDOWS_VM / "Get-ConvenePublicationDiagnostics.ps1").read_text(
        encoding="utf-8"
    )

    assert "IncludeFieldInventory" in script
    assert "CURRENT CONVENE HANDOFF FIELD INVENTORY (NON-SECRET)" in script
    assert "ScalarType" in script
    assert "ExampleValue" in script
    assert "NestedCount" in script
    assert "ExistingSimPrefixCount" in script
