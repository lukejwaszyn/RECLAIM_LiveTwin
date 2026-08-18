from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
WINDOWS = ROOT / "convene_bridge" / "windows"


def test_winsw_template_has_no_secret_argument_or_embedded_binary():
    template = WINDOWS / "reclaim-state-bridge.xml"
    root = ET.parse(template).getroot()
    arguments = root.findtext("arguments") or ""
    assert "--config" in arguments
    assert "token" not in arguments.lower()
    assert not list(WINDOWS.glob("*.exe"))


def test_installer_discovers_and_protects_existing_deployments():
    source = (WINDOWS / "install-state-bridge.ps1").read_text(encoding="utf-8")
    for required in (
        "Get-CimInstance Win32_Service",
        "Get-ScheduledTask",
        "Get-Acl",
        "Get-FileHash -Algorithm SHA256",
        ".reclaim-state-bridge-owned.json",
        "ConveneAgentIdentity",
        "icacls.exe",
    ):
        assert required in source
    for prohibited in (
        "Unregister-ScheduledTask",
        "Stop-ScheduledTask",
        "ConveneToken",
        "ReadToken",
        "IngestToken",
    ):
        assert prohibited not in source


def test_uninstaller_preserves_existing_agent_and_output_by_default():
    source = (WINDOWS / "uninstall-state-bridge.ps1").read_text(encoding="utf-8")
    assert "Unregister-ScheduledTask" not in source
    assert "Remove-Item $OutputPath" not in source
    assert "ArchiveSimVars" in source
    assert "PurgeBridgeData" in source
