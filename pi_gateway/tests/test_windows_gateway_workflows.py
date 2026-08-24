from pathlib import Path


WINDOWS = Path(__file__).resolve().parents[1] / "windows"


def test_task_installer_is_guarded_and_does_not_start_by_default():
    script = (WINDOWS / "install-gateway-task.ps1").read_text(encoding="utf-8")
    assert '[switch]$Start' in script
    assert 'if ($Start and' not in script
    assert 'if ($Start -and $PSCmdlet.ShouldProcess' in script
    assert 'Assert-ConfigAcl -Path $configPath' in script
    assert 'exposes loopback-only status port 9080' in script
    assert 'Get-NetRoute -InterfaceAlias $InterfaceAlias' in script
    assert "c.convene_enabled" in script


def test_desktop_convene_repair_does_not_use_vm_binding_backend():
    script = (WINDOWS / "repair-convene-desktop-agent.ps1").read_text(encoding="utf-8")
    assert "reservation-backend-xczhrp2y6q-uc.a.run.app" not in script
    assert "Deploy-ConveneVariableBindings" not in script
    assert "MissingFirestoreIndex" in script
    assert "SystemCredentialPath" in script
    assert "autoVars" in script


def test_direct_vm_gateway_workflows_are_not_active():
    for name in (
        "finalize-gateway-config.ps1",
        "send-commissioning-frame.ps1",
        "send-commissioning-stream.ps1",
    ):
        assert not (WINDOWS / name).exists()
