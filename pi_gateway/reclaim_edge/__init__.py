"""RECLAIM Edge Gateway — cRIO-to-cloud IoT telemetry gateway.

Shared runtime used by the Windows live gateway and MacBook scenario host: receives
measured telemetry from the NI cRIO over the trusted LAN (newline-delimited JSON
frames), buffers it durably on the SD card, and pushes it outbound over TLS
through the Cloudflare Tunnel to the cloud predictive engine.

Author: LJW.
"""
__version__ = "0.1.0"
