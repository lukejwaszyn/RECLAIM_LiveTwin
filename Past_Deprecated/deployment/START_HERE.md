# START HERE — Claude Code gateway staging run

> **Archived platform notice (2026-08-23):** the authoritative edge gateway is now the MacBook. Any Windows, Linux, Raspberry Pi, desktop-gateway, address, service, or task instructions below are historical evidence only and must not be used for the competition deployment. Use `deployment/DEPLOYMENT_TOPOLOGY.md` and `pi_gateway/macos/README.md`.

> **Stage:** 0 — Offline staging (cRIO + cloud offline) · **Status:** HISTORICAL —
> that staging session is complete (see GATEWAY_GO_LIVE §1). Kept for context;
> for current pickup read `HANDOFF.md`, not this file.

Claude Code: read `deployment/ClaudeCode_Staging_Prompts.md` in this repo and use
it as your work plan for this session. Begin by executing its **Prompt 0** (read
the listed files, absorb every environment fact and hard guardrail, acknowledge,
and list what you reviewed). Then work through **Prompt 1 → Prompt 6** in order;
**Prompt 7 is optional — ask first.**

Rules while executing:

- Treat each numbered prompt as one unit of work. For each: first show the plan
  plus the exact commands and/or file diffs, then **STOP and wait for my explicit
  "go"** before writing files or running anything. Never chain multiple prompts
  without checking in.
- Honor the guardrails verbatim: **no** boot-task install, **no** inbound firewall
  changes, **no** POST to any live cloud, **no** publishing `sim_*` to Convene,
  **no** synthetic emitter into anything live. This machine blocks inbound
  listeners (WDAC) — do **not** propose SSH/RDP servers.
- The cRIO is offline and the cloud endpoint is a placeholder; keep everything to
  local staging plus the console shakedown.
- After each prompt, give a one-line status (done / what's next) before continuing.

Begin with Prompt 0 now.
