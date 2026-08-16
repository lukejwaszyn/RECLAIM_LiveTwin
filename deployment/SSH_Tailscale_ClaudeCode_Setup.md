# RECLAIM Laptop — Admin SSH + Claude Code Bootstrap

> **Stage:** 0 — Access base · **Status:** PARTIALLY SUPERSEDED. The inbound-SSH
> approach here does not work on this laptop (WDAC blocks inbound listeners); the
> access model is now outbound-only — TeamViewer + Tailscale + the Convene agent
> (GATEWAY_GO_LIVE §9.1). The Tailscale and Claude Code bootstrap steps remain
> valid; ignore the OpenSSH-server sections.

**Goal of this phase:** stand up Claude Code on the Windows 10 gateway laptop, and
enable secure SSH into the laptop from (a) a MacBook using native `ssh` and (b) a
Windows client using PuTTY — all over a **Tailscale** private network, no port
forwarding, no Cloudflare Tunnel.

**In scope:** admin SSH to *this laptop only*. The cloud VM and the preflight's
Cloudflare Tunnel are intentionally left alone in this phase.

**Deviations from `docs/RECLAIM_Remote_Gateway_Preflight.md` §1 (deliberate):**

- Transport is **Tailscale**, not Cloudflare Tunnel. Simpler for personal admin
  access; the laptop joins a private mesh and is reachable at a stable `100.x`
  address.
- The MacBook uses **native `ssh`** — PuTTY is not needed on macOS. PuTTY is only
  for the Windows client.
- Because Tailscale gives direct network reachability, PuTTY needs **no**
  `cloudflared access ssh` proxy command (the doc's version assumed the tunnel).

**Roles:** the *laptop* runs the OpenSSH **server** + Tailscale + Claude Code.
The *Mac* and the *Windows box* are **clients**.

**Prerequisites**

- Claude Pro or Max account (for Claude Code sign-in).
- A Tailscale account (separate login — Google/GitHub/Microsoft/email). Free tier
  is fine for a personal tailnet.
- Windows 10 build 1809 or later on the laptop.
- The laptop's Windows username (this repo lives under `C:\Users\latitude4`, so the
  account is assumed to be **`latitude4`** — confirm in Phase 0).

---

## Phase 0 — Confirm the ground truth (laptop, PowerShell)

```powershell
whoami                                   # confirm the SSH login user (expect ...\latitude4)
[System.Environment]::OSVersion.Version  # Build must be >= 17763 (1809)
$PSVersionTable.PSVersion                # PowerShell 5.1 is fine
```

**Gate 0:** username noted, build ≥ 17763. Then proceed.

---

## Phase 1 — Claude Code (laptop, native Windows)

Recommended: install Git for Windows first so Claude Code's Bash tools work.

```powershell
winget install --id Git.Git -e --source winget
winget install --id Anthropic.ClaudeCode -e --source winget   # if listed; else use the script below
```

If the winget package isn't found, use the official native installer:

```powershell
irm https://claude.ai/install.ps1 | iex
```

Close and reopen PowerShell (PATH refresh), then verify and sign in:

```powershell
claude --version
claude          # launches; at the auth prompt choose "Claude account (Pro/Max)" -> browser login
```

Inside Claude Code, confirm the session:

```
/status
/doctor
```

**Gate 1:** `claude --version` prints a version; `/status` shows you signed in on
the Pro/Max plan. If you see *"claude is not recognized"*, open a fresh terminal
(the installer updated PATH but the old shell hasn't picked it up).

---

## Phase 2 — OpenSSH Server on the laptop (elevated PowerShell)

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Set-Service sshd -StartupType Automatic
Start-Service sshd
Get-Service sshd                         # expect Status Running
```

Make PowerShell the default SSH shell (nicer remote sessions):

```powershell
New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell `
  -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" `
  -PropertyType String -Force
```

**Gate 2:** `sshd` is Running and set to Automatic. (We restrict *who* can reach
it to the tailnet in Phase 6 — don't expose it broadly yet.)

---

## Phase 3 — Tailscale on the laptop (elevated PowerShell)

```powershell
winget install --id Tailscale.Tailscale -e --source winget
tailscale up                             # opens a browser -> log in / create tailnet, authorize this device
tailscale ip -4                          # note the 100.x.y.z address  <-- LAPTOP_TS_IP
tailscale status                         # confirm this node is "active"
```

Also note the MagicDNS name if enabled (e.g. `reclaim-laptop.<tailnet>.ts.net`).

**Gate 3:** `tailscale ip -4` returns a `100.x` address; the device shows up in
the Tailscale admin console.

---

## Phase 4 — Key auth: MacBook client (native ssh)

On the **Mac**:

```bash
# 1. install + join the same tailnet (Mac App Store app, or:)
brew install tailscale && sudo tailscale up      # or use the GUI app

# 2. generate a dedicated key
ssh-keygen -t ed25519 -C "macbook-luke" -f ~/.ssh/id_ed25519_reclaim

# 3. print the PUBLIC key — copy this whole line
cat ~/.ssh/id_ed25519_reclaim.pub
```

On the **laptop** (elevated PowerShell), install that public key. This account is
an admin, so Windows uses the shared `administrators_authorized_keys` file with
strict ACLs — **not** `~/.ssh/authorized_keys`:

```powershell
Add-Content C:\ProgramData\ssh\administrators_authorized_keys "<paste the ssh-ed25519 ... line>"
icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r `
       /grant "Administrators:F" /grant "SYSTEM:F"
```

Back on the **Mac**, add an SSH config entry and connect:

```
# ~/.ssh/config
Host reclaim-laptop
    HostName <LAPTOP_TS_IP>        # or the MagicDNS name
    User latitude4
    IdentityFile ~/.ssh/id_ed25519_reclaim
```

```bash
ssh reclaim-laptop
```

**Gate 4:** the Mac lands a PowerShell prompt on the laptop **without** a password
(key only).

---

## Phase 5 — Key auth: Windows client (PuTTY)

On the **Windows client**:

1. Install Tailscale (`winget install Tailscale.Tailscale`), `tailscale up`, join
   the same tailnet.
2. Install PuTTY (`winget install PuTTY.PuTTY`).
3. Run **PuTTYgen** → key type **EdDSA / Ed25519** → *Generate* → *Save private
   key* (`reclaim.ppk`). Copy the "Public key for pasting into
   authorized_keys" box.
4. On the **laptop**, append that public key to
   `C:\ProgramData\ssh\administrators_authorized_keys` (same as Phase 4; re-run
   the `icacls` line after editing).
5. In **PuTTY**: Session → Host Name `<LAPTOP_TS_IP>`, Port 22 · Connection → Data
   → Auto-login username `latitude4` · Connection → SSH → Auth → Credentials →
   browse to `reclaim.ppk` · save the session as `reclaim-laptop`.

No proxy command is required — Tailscale already routes you to the laptop.

**Gate 5:** PuTTY connects with the key only.

---

## Phase 6 — Harden (laptop, elevated PowerShell) — only after Gates 4 & 5 pass

Restrict SSH to the tailnet, then turn off password auth:

```powershell
# Only allow inbound TCP 22 from the Tailscale CGNAT range; drop the broad rule
Get-NetFirewallRule -Name *OpenSSH-Server* | Disable-NetFirewallRule
New-NetFirewallRule -DisplayName "OpenSSH over Tailscale" -Direction Inbound `
  -Protocol TCP -LocalPort 22 -Action Allow -RemoteAddress 100.64.0.0/10

# Key-only auth
notepad C:\ProgramData\ssh\sshd_config
#   set:  PubkeyAuthentication yes
#         PasswordAuthentication no
Restart-Service sshd
```

**Gate 6:** SSH from the tailnet still works; SSH attempts from off-tailnet are
refused; password login is rejected.

---

## Rollback / safety

- Nothing here touches the cRIO link, the durable queue, Convene bindings, or the
  cloud engine — it is purely an access layer.
- To back out: `Stop-Service sshd; Set-Service sshd -StartupType Disabled`,
  `tailscale down`, and re-enable the original firewall rule. TeamViewer remains
  your fallback path throughout — keep it until Gate 6 is green.

## End-state verification checklist

- [ ] Phase 0: login user + OS build confirmed
- [ ] Phase 1: `claude --version` OK; signed in on Pro/Max
- [ ] Phase 2: `sshd` Running / Automatic
- [ ] Phase 3: laptop has a `100.x` Tailscale IP, visible in admin console
- [ ] Phase 4: Mac `ssh reclaim-laptop` works, key-only
- [ ] Phase 5: Windows PuTTY session works, key-only
- [ ] Phase 6: SSH locked to tailnet; password auth disabled
