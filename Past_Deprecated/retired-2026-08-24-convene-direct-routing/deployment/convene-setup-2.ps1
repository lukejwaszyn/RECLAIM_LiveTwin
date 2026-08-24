# Convene one-click setup - Windows (PowerShell)
# Headless is the safe/default VM posture. Desktop streaming is opt-in only.
param(
  [Parameter(Mandatory = $true)]
  [ValidateNotNullOrEmpty()]
  [string]$PairingCode,
  [switch]$EnableDesktop
)
$ErrorActionPreference = "Stop"

Write-Host "=================================================="
Write-Host "  Convene Connected Machine - one-click setup"
Write-Host "=================================================="

# 1. Python 3
if (-not (Get-Command python -ErrorAction SilentlyContinue) -and
    -not (Get-Command py -ErrorAction SilentlyContinue)) {
  Write-Host "==> Installing Python 3 ..."
  try {
    winget install -e --id Python.Python.3.13 --scope machine --silent `
      --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + $env:Path
  }
  catch { Write-Host "    Please install Python from https://python.org then re-run."; exit 1 }
}
if (Get-Command py -ErrorAction SilentlyContinue) {
  $PythonExe = (& py -3.13 -c "import sys; print(sys.executable)").Trim()
} else {
  $PythonExe = (Get-Command python -ErrorAction Stop).Source
}
if (-not (Test-Path $PythonExe)) { throw "Python executable was not found after installation" }
Write-Host "==> Installing Python packages (requests, psutil) ..."
& $PythonExe -m pip install --quiet requests psutil

if ($EnableDesktop) {
Write-Host "==> Installing explicitly requested desktop-streaming tools ..."
try { winget install -e --id GlavSoft.TightVNC --silent --accept-package-agreements --accept-source-agreements } catch { Write-Host "    Install TightVNC manually from https://tightvnc.com if needed." }
& $PythonExe -m pip install --quiet websockify
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
  try { winget install -e --id Cloudflare.cloudflared --silent --accept-package-agreements --accept-source-agreements }
  catch {
    $cf = "$env:USERPROFILE\.convene\cloudflared.exe"
    Invoke-WebRequest "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $cf
    $env:Path += ";$env:USERPROFILE\.convene"
  }
}

# TightVNC blocks loopback (127.0.0.1) connections by default, which makes the
# websockify bridge fail with "loopback connections are not enabled". The silent
# install also leaves no VNC password, so leaving auth on would prompt for a
# password nobody knows. Enable loopback + disable VNC auth, then restart.
Write-Host "==> Configuring TightVNC (loopback on, password off) ..."
foreach ($key in @("HKLM:\SOFTWARE\TightVNC\Server", "HKLM:\SOFTWARE\WOW6432Node\TightVNC\Server")) {
  try {
    if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }
    New-ItemProperty -Path $key -Name "AllowLoopback"            -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $key -Name "LoopbackOnly"             -Value 0 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $key -Name "UseVncAuthentication"     -Value 0 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $key -Name "UseControlAuthentication" -Value 0 -PropertyType DWord -Force | Out-Null
  } catch { Write-Host "    (could not set $key - run as Administrator if it stays blocked)" }
}
try { Restart-Service -Name "tvnserver" -Force -ErrorAction SilentlyContinue } catch {}
try { & "$env:ProgramFiles\TightVNC\tvnserver.exe" -reload } catch {}
}

# 2. Write the agent
$dir = "C:\ConveneAgent"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$agent = @'
#!/usr/bin/env python3
"""Convene Connected Machine Agent v1.1
Install deps:  pip install requests psutil
Run (first time): python3 convene_agent.py --code 1079675C
Run (subsequent): python3 convene_agent.py
Add --desktop to auto-stream this machine's screen to Convene (no manual URL).
"""
import sys, time, json, platform, os, subprocess, threading, re, shutil
import requests
try:
    import psutil
except ImportError:
    psutil = None

BACKEND        = "https://reservation-backend-25386666460.us-central1.run.app/api"
HEARTBEAT_SEC  = 30
WS_PORT        = 6080          # websockify port (noVNC bridge)
VNC_PORT       = 5900          # local VNC server port
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE     = os.path.join(BASE_DIR, "agent-credentials.json")
SIM_VARS_FILE  = os.path.join(BASE_DIR, "sim_vars.json")
DESKTOP        = "--desktop" in sys.argv
VNC_URL        = None          # auto-filled when the public tunnel is up
IS_WIN         = platform.system() == "Windows"
IS_MAC         = platform.system() == "Darwin"

def _disk():
    return "C:\\" if IS_WIN else "/"

def _first_temp():
    """Best-effort CPU temperature (°C) across platforms; None if unavailable."""
    try:
        temps = psutil.sensors_temperatures()
        for key in ("coretemp", "cpu_thermal", "k10temp", "acpitz"):
            if temps.get(key):
                return round(temps[key][0].current, 1)
        for arr in temps.values():
            if arr:
                return round(arr[0].current, 1)
    except Exception:
        pass
    return None

# Convene-suggested metrics the agent can auto-collect and return each heartbeat.
# The backend tells the agent which of these to report (autoMetrics) based on the
# variables you added in the Variables tab.
METRIC_COLLECTORS = {
    "cpu_percent": lambda: psutil.cpu_percent(),
    "cpu_temp_c": lambda: _first_temp(),
    "cpu_freq_mhz": lambda: round(psutil.cpu_freq().current, 1),
    "load_avg_1m": lambda: round(psutil.getloadavg()[0], 2),
    "mem_percent": lambda: psutil.virtual_memory().percent,
    "mem_used_mb": lambda: round(psutil.virtual_memory().used / 1048576),
    "mem_available_mb": lambda: round(psutil.virtual_memory().available / 1048576),
    "swap_percent": lambda: psutil.swap_memory().percent,
    "disk_percent": lambda: psutil.disk_usage(_disk()).percent,
    "disk_free_gb": lambda: round(psutil.disk_usage(_disk()).free / 1073741824, 1),
    "net_sent_mb": lambda: round(psutil.net_io_counters().bytes_sent / 1048576, 1),
    "net_recv_mb": lambda: round(psutil.net_io_counters().bytes_recv / 1048576, 1),
    "process_count": lambda: len(psutil.pids()),
    "battery_percent": lambda: (round(psutil.sensors_battery().percent) if psutil.sensors_battery() else None),
    "uptime_s": lambda: int(time.time() - psutil.boot_time()),
}

# ── Generic integration collectors ────────────────────────────────────────────
# Beyond the psutil metrics above, Convene can tell the agent to sense values from
# specific programs, files, HTTP endpoints, processes and serial hardware. Each
# such variable carries a "collector" config the agent reads + pushes every beat.
try:
    import serial as _pyserial          # pip install pyserial (only for serial sources)
except ImportError:
    _pyserial = None

def _coerce(v):
    """Best-effort convert a captured string into a number/bool where sensible."""
    if v is None:
        return None
    if isinstance(v, (int, float, bool, dict, list)):
        return v
    s = str(v).strip()
    if s == "":
        return None
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        f = float(s)
        return int(f) if f.is_integer() else f
    except Exception:
        return s

def _apply_regex(text, pattern):
    if not pattern:
        return (text or "").strip()
    m = re.search(pattern, text or "", re.MULTILINE)
    if not m:
        return None
    return m.group(1) if m.groups() else m.group(0)

def _json_path(obj, path):
    if not path:
        return obj
    cur = obj
    for part in re.findall(r"[^.\[\]]+", path):
        try:
            if isinstance(cur, list):
                cur = cur[int(part)]
            elif isinstance(cur, dict):
                cur = cur.get(part)
            else:
                return None
        except Exception:
            return None
    return cur

def collect_from(c):
    """Run one collector config and return a value (or None)."""
    t = c.get("type")
    if t == "shell":
        out = subprocess.run(c.get("command", ""), shell=True, capture_output=True,
                             text=True, timeout=30).stdout
        return _coerce(_apply_regex(out, c.get("regex")))
    if t == "http":
        r = requests.get(c.get("url", ""), timeout=15)
        if c.get("jsonPath"):
            try:
                return _coerce(_json_path(r.json(), c["jsonPath"]))
            except Exception:
                pass
        return _coerce(_apply_regex(r.text, c.get("regex")))
    if t == "file":
        with open(os.path.expanduser(c.get("path", "")), "r", errors="ignore") as f:
            data = f.read()
        if c.get("jsonPath"):
            try:
                return _coerce(_json_path(json.loads(data), c["jsonPath"]))
            except Exception:
                pass
        return _coerce(_apply_regex(data, c.get("regex")))
    if t == "process":
        if psutil is None:
            return None
        name = (c.get("processName") or "").lower()
        field = c.get("field") or "running"
        procs = []
        for p in psutil.process_iter(["name"]):
            try:
                if name and name in (p.info.get("name") or "").lower():
                    procs.append(p)
            except Exception:
                pass
        if field == "running":
            return len(procs) > 0
        if not procs:
            return 0
        try:
            if field == "cpu":
                return round(sum(p.cpu_percent(interval=None) or 0 for p in procs), 1)
            if field == "mem":
                return round(sum(p.memory_percent() or 0 for p in procs), 1)
        except Exception:
            return None
    if t == "serial":
        if _pyserial is None:
            print("[serial] pyserial not installed - run: " + sys.executable + " -m pip install pyserial")
            return None
        with _pyserial.Serial(c.get("port", ""), int(c.get("baud") or 9600), timeout=5) as s:
            line = s.readline().decode(errors="ignore")
        return _coerce(_apply_regex(line, c.get("regex")))
    return None


def pair(code):
    data = {
        "pairingCode": code,
        "name":        platform.node(),
        "hostname":    platform.node(),
        "os":          platform.system().lower(),
        "arch":        platform.machine(),
        "agentVersion":"1.1.0",
    }
    r = requests.post(f"{BACKEND}/machine/pair", json=data, timeout=15)
    r.raise_for_status()
    result = r.json()
    with open(CREDS_FILE, "w") as f:
        json.dump(result, f)
    print(f"OK Paired! Machine ID: {result['machineId']}")
    return result

def get_stats():
    if psutil is None:
        return {"cpuPercent":0,"memoryPercent":0,"diskPercent":0,"uptime":0}
    try:
        return {
            "cpuPercent":    psutil.cpu_percent(interval=1),
            "memoryPercent": psutil.virtual_memory().percent,
            "diskPercent":   psutil.disk_usage(_disk()).percent,
            "uptime":        int(time.time() - psutil.boot_time()),
        }
    except Exception:
        return {"cpuPercent":0,"memoryPercent":0,"diskPercent":0,"uptime":0}

def get_sim_vars():
    """Read the bridge handoff without retaining a partial/invalid payload."""
    try:
        with open(SIM_VARS_FILE, "r", encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, OSError, ValueError):
        return {}

def push_variable(token, var_id, value):
    """Call from your simulation script to push a value."""
    try:
        r = requests.post(
            f"{BACKEND}/machine/agent-variable/{var_id}/value",
            json={"value": value},
            headers={"X-Agent-Token": token},
            timeout=10,
        )
        return r.ok
    except Exception as e:
        print(f"[push_variable] {e}")
        return False

def run_cmd(cmd_doc):
    try:
        if cmd_doc.get("type","shell") == "shell":
            result = subprocess.run(
                cmd_doc["command"], shell=True,
                capture_output=True, text=True, timeout=120
            )
            print(f"[CMD] exit={result.returncode}\n{result.stdout[:500]}")
    except Exception as e:
        print(f"[CMD ERROR] {e}")

# ── Interactive terminal (SSH-style remote shell) ─────────────────────────────
# A persistent working directory is kept across commands so "cd" behaves like a
# real shell session. Each command's combined stdout/stderr, exit code and the
# resulting cwd are posted back to Convene so the Terminal tab can display them.
SHELL_CWD = os.path.expanduser("~")

def run_terminal_cmd(token, cmd_doc):
    global SHELL_CWD
    cmd = (cmd_doc.get("command") or "").strip()
    cmd_id = cmd_doc.get("id")
    out, code = "", 0
    try:
        # Handle "cd" locally so the session directory persists between commands.
        if cmd == "cd" or cmd.startswith("cd ") or cmd.startswith("cd\t"):
            target = cmd[2:].strip() or os.path.expanduser("~")
            target = os.path.expanduser(os.path.expandvars(target))
            new_dir = target if os.path.isabs(target) else os.path.join(SHELL_CWD, target)
            if os.path.isdir(new_dir):
                SHELL_CWD = os.path.abspath(new_dir)
            else:
                out, code = f"cd: no such directory: {target}\n", 1
        elif cmd in ("pwd",):
            out = SHELL_CWD + "\n"
        else:
            result = subprocess.run(
                cmd, shell=True, cwd=SHELL_CWD,
                capture_output=True, text=True, timeout=120,
            )
            out = (result.stdout or "") + (result.stderr or "")
            code = result.returncode
    except subprocess.TimeoutExpired:
        out, code = "[command timed out after 120s]\n", 124
    except Exception as e:
        out, code = f"[error] {e}\n", 1
    try:
        requests.post(
            f"{BACKEND}/machine/command-result",
            json={"commandId": cmd_id, "output": out, "exitCode": code, "cwd": SHELL_CWD},
            headers={"X-Agent-Token": token}, timeout=15,
        )
    except Exception as e:
        print(f"[command-result] {e}")

def command_loop(token):
    """Poll for terminal commands every 2s so the remote shell feels responsive."""
    headers = {"X-Agent-Token": token}
    while True:
        try:
            r = requests.get(f"{BACKEND}/machine/commands", headers=headers, timeout=10)
            if r.ok:
                for cmd in r.json().get("commands", []):
                    run_terminal_cmd(token, cmd)
        except Exception as e:
            print(f"[command_loop] {e}")
        time.sleep(2)

def _spawn(args):
    """Launch a background process, swallowing its output."""
    try:
        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        return None

def _vnc_target_host():
    """Pick the host the bridge should use to reach the local VNC server.

    On Windows we connect over localhost AFTER enabling TightVNC's AllowLoopback
    (see _ensure_tightvnc_loopback). Connecting via the LAN IP does NOT help,
    because Windows routes connections to your own IP through the loopback
    adapter, so TightVNC still sees them as loopback."""
    return "localhost"

def _ensure_tightvnc_loopback():
    """Prepare TightVNC for the local websockify bridge:
      * AllowLoopback=1        - TightVNC blocks loopback (127.0.0.1) by default
                                 ("loopback connections are not enabled").
      * UseVncAuthentication=0 - the silent install never set a VNC password, so
                                 leaving auth on makes the viewer prompt for a
                                 password nobody knows. The random tunnel URL is
                                 the secret, so we disable the VNC password.
    HKLM needs admin, so if we are not elevated we relaunch just this step via a
    one-time UAC prompt."""
    if not IS_WIN:
        return
    keys = [r"SOFTWARE\TightVNC\Server", r"SOFTWARE\WOW6432Node\TightVNC\Server"]
    # 1. Try to write directly (works if this process is already elevated).
    wrote = False
    try:
        import winreg
        for sub in keys:
            try:
                k = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, sub, 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(k, "AllowLoopback",        0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(k, "LoopbackOnly",         0, winreg.REG_DWORD, 0)
                winreg.SetValueEx(k, "UseVncAuthentication", 0, winreg.REG_DWORD, 0)
                winreg.SetValueEx(k, "UseControlAuthentication", 0, winreg.REG_DWORD, 0)
                winreg.CloseKey(k)
                wrote = True
            except PermissionError:
                wrote = False
                break
            except OSError:
                continue
    except Exception:
        wrote = False
    if wrote:
        # Reload TightVNC so it picks up the new settings.
        _spawn(["net", "stop", "tvnserver"]); time.sleep(1)
        _spawn(["net", "start", "tvnserver"]); time.sleep(3)
        print("[desktop] Configured TightVNC (loopback on, password off).")
        return
    # 2. Not elevated: relaunch the reg + service-restart step with a UAC prompt.
    try:
        import ctypes
        reg_cmds = []
        for hive in ("HKLM\\SOFTWARE\\TightVNC\\Server",
                     "HKLM\\SOFTWARE\\WOW6432Node\\TightVNC\\Server"):
            reg_cmds.append('reg add "%s" /v AllowLoopback /t REG_DWORD /d 1 /f' % hive)
            reg_cmds.append('reg add "%s" /v UseVncAuthentication /t REG_DWORD /d 0 /f' % hive)
            reg_cmds.append('reg add "%s" /v UseControlAuthentication /t REG_DWORD /d 0 /f' % hive)
        cmd = " & ".join(reg_cmds) + " & net stop tvnserver & net start tvnserver"
        print("[desktop] Asking for admin to configure TightVNC (one-time UAC prompt) ...")
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", "/c " + cmd, None, 0)
        if rc > 32:
            time.sleep(6)  # give the elevated process time to restart the service
            print("[desktop] TightVNC configured (loopback on, password off).")
        else:
            print("[desktop] Could not elevate. Re-run the installer as Administrator.")
    except Exception as e:
        print(f"[desktop] TightVNC setup skipped: {e}")

def start_desktop():
    """Start a VNC bridge (websockify) + a free Cloudflare quick tunnel and
    report the resulting wss:// URL so the Convene desktop viewer connects with
    zero manual steps. Requires: websockify + cloudflared on PATH
    (and x11vnc on Linux). The one-click installer sets these up for you."""
    global VNC_URL
    # 0. On Windows, make sure TightVNC accepts the local (loopback) bridge.
    _ensure_tightvnc_loopback()
    # 1. On Linux, start x11vnc to expose the existing X session on :0.
    if not IS_WIN and not IS_MAC and shutil.which("x11vnc"):
        _spawn(["x11vnc", "-display", ":0", "-forever", "-shared",
                "-nopw", "-quiet", "-rfbport", str(VNC_PORT)])
        time.sleep(2)
    # 2. Bridge raw VNC -> WebSocket so the browser noVNC client can connect.
    #    pip-installed websockify is frequently NOT on PATH (especially on
    #    Windows/macOS), so fall back to running it as a Python module.
    #    NOTE: TightVNC on Windows rejects loopback (127.0.0.1) connections by
    #    default ("loopback connections are not enabled"). Connecting the bridge
    #    to the machine's real LAN IP avoids that without any registry changes.
    vnc_host = _vnc_target_host()
    ws_cmd = None
    if shutil.which("websockify"):
        ws_cmd = ["websockify", str(WS_PORT), f"{vnc_host}:{VNC_PORT}"]
    else:
        try:
            import websockify  # noqa: F401  (importable even when not on PATH)
            ws_cmd = [sys.executable, "-m", "websockify", str(WS_PORT), f"{vnc_host}:{VNC_PORT}"]
        except ImportError:
            ws_cmd = None
    if ws_cmd:
        print(f"[desktop] Bridging VNC {vnc_host}:{VNC_PORT} -> ws :{WS_PORT}")
        _spawn(ws_cmd)
        time.sleep(2)
    else:
        print("[desktop] websockify not found. Install it with:  " + sys.executable + " -m pip install websockify")
        return
    # 3. Cloudflare quick tunnel (no login/token) -> public https/wss URL.
    cf = shutil.which("cloudflared")
    if not cf:
        # The installer may have dropped cloudflared in ~/.convene without
        # updating PATH for this session; look there too.
        for cand in (
            os.path.join(os.path.expanduser("~/.convene"),
                         "cloudflared.exe" if IS_WIN else "cloudflared"),
        ):
            if os.path.exists(cand):
                cf = cand
                break
    if not cf:
        print("[desktop] cloudflared not found - run the one-click installer.")
        return
    proc = subprocess.Popen(
        [cf, "tunnel", "--url", f"http://localhost:{WS_PORT}", "--no-autoupdate"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    print("[desktop] Establishing public tunnel ...")
    for line in iter(proc.stdout.readline, ""):
        m = re.search(r"https://([a-z0-9-]+\.trycloudflare\.com)", line)
        if m:
            VNC_URL = "wss://" + m.group(1)
            print(f"[desktop] Screen sharing live: {VNC_URL}")
            break

def heartbeat_loop(token):
    headers = {"X-Agent-Token": token}
    print(f"Heartbeating every {HEARTBEAT_SEC}s ...")
    while True:
        try:
            payload = get_stats()
            payload["simVars"] = get_sim_vars()
            if VNC_URL:
                payload["vncUrl"] = VNC_URL
            r = requests.post(
                f"{BACKEND}/machine/heartbeat",
                json=payload, headers=headers, timeout=10
            )
            if r.ok:
                resp = r.json()
                for cmd in resp.get("commands", []):
                    threading.Thread(target=run_terminal_cmd, args=(token, cmd), daemon=True).start()
                # Auto-collect + return the Convene-suggested metrics the user added.
                for m in resp.get("autoMetrics", []):
                    key, vid = m.get("metricKey"), m.get("varId")
                    fn = METRIC_COLLECTORS.get(key)
                    if fn and vid and psutil is not None:
                        try:
                            val = fn()
                            if val is not None:
                                push_variable(token, vid, val)
                        except Exception as e:
                            print(f"[metric {key}] {e}")
                # Sense values from specific programs / files / endpoints / sensors.
                # Each collector runs in its own thread so a slow source (serial,
                # matlab, http) never blocks the heartbeat.
                for av in resp.get("autoVars", []):
                    vid, col = av.get("varId"), av.get("collector")
                    if not (vid and col):
                        continue
                    def _run(vid=vid, col=col):
                        try:
                            val = collect_from(col)
                            if val is not None:
                                push_variable(token, vid, val)
                        except Exception as e:
                            print(f"[source {col.get('type')}] {e}")
                    threading.Thread(target=_run, daemon=True).start()
            else:
                print(f"[Heartbeat] HTTP {r.status_code}; collectors were not returned")
        except Exception as e:
            print(f"[Heartbeat] {e}")
        time.sleep(HEARTBEAT_SEC)

if __name__ == "__main__":
    if "--code" in sys.argv:
        idx  = sys.argv.index("--code") + 1
        code = sys.argv[idx] if idx < len(sys.argv) else input("Pairing code: ")
        creds = pair(code)
    elif os.path.exists(CREDS_FILE):
        with open(CREDS_FILE) as f:
            creds = json.load(f)
        print(f"OK Using saved credentials ({creds['machineId']})")
    else:
        print("Run with --code YOUR_CODE to pair first.")
        sys.exit(1)
    if "--pair-only" in sys.argv:
        print("OK Pairing complete; exiting before heartbeat startup.")
        sys.exit(0)
    if DESKTOP:
        threading.Thread(target=start_desktop, daemon=True).start()
    # Fast poll for interactive Terminal commands (independent of the 30s telemetry heartbeat).
    threading.Thread(target=command_loop, args=(creds["agentToken"],), daemon=True).start()
    heartbeat_loop(creds["agentToken"])

'@
Set-Content -Path "$dir\convene_agent.py" -Value $agent -Encoding UTF8

# 3. Pair, lock down credentials, and register the headless startup task.
Write-Host "==> Connecting this machine to Convene ..."
Set-Location $dir
& $PythonExe convene_agent.py --code $PairingCode --pair-only
if ($LASTEXITCODE -ne 0) { throw "Convene pairing failed" }

$CredentialsPath = Join-Path $dir "agent-credentials.json"
if (-not (Test-Path $CredentialsPath)) { throw "Convene credentials were not created" }
& icacls.exe $dir /inheritance:r /grant:r `
  "SYSTEM:(OI)(CI)(F)" "BUILTIN\Administrators:(OI)(CI)(F)" | Out-Null

$TaskName = "Convene-Agent"
$Action = New-ScheduledTaskAction -Execute $PythonExe `
  -Argument ('"' + (Join-Path $dir "convene_agent.py") + '"') `
  -WorkingDirectory $dir
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Settings = New-ScheduledTaskSettingsSet -RestartCount 999 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" `
  -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
  -Settings $Settings -Principal $Principal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Convene agent paired and started headless as task '$TaskName'."
Write-Host "State handoff: $dir\sim_vars.json -> heartbeat simVars"
