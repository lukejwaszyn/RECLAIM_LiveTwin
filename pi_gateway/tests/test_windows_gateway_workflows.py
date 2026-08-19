from pathlib import Path


WINDOWS = Path(__file__).resolve().parents[1] / "windows"


def test_https_finalizer_prompts_for_secret_and_enforces_ingest_tls():
    script = (WINDOWS / "finalize-gateway-config.ps1").read_text(encoding="utf-8")
    assert 'Read-Host "Enter the VM RECLAIM_INGEST_TOKEN (input is hidden)" -AsSecureString' in script
    assert '$uri.Scheme -ne "https"' in script
    assert '$uri.AbsolutePath.TrimEnd(\'/\') -ne "/ingest"' in script
    assert '"*S-1-5-18:(F)"' in script
    assert '"*S-1-5-32-544:(F)"' in script
    assert "convene_enabled' -SerializedValue 'true'" in script
    assert "convene_credentials_path" in script


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


def test_commissioning_sender_is_one_frame_guarded_and_credential_free():
    script = (WINDOWS / "send-commissioning-frame.ps1").read_text(encoding="utf-8")
    assert "SupportsShouldProcess" in script
    assert "The real cRIO is already connected" in script
    assert "COMMISSIONING-NOT-CRIO-" in script
    assert "RECLAIM_INGEST_TOKEN" not in script
    assert "agentToken" not in script
    assert "VmIngestedAdvanced" in script
    assert "ConveneDeliveredAdvanced" in script
