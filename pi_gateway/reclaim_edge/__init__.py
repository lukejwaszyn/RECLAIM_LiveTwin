"""RECLAIM Edge Gateway — cRIO-to-cloud IoT telemetry gateway.

Runs on the Raspberry Pi 3 B+ flight computer at the OT/IT boundary: receives
measured telemetry from the NI cRIO over the trusted LAN (newline-delimited JSON
frames), buffers it durably on the SD card, and pushes it outbound over TLS
through the Cloudflare Tunnel to the cloud predictive engine.

Author: LJW.
"""
__version__ = "0.1.0"
