"""RECLAIM Edge Gateway — cRIO/scenario-to-Convene telemetry gateway.

Shared runtime used by the Windows live gateway and MacBook scenario host: receives
measured telemetry from the NI cRIO over the trusted LAN (newline-delimited JSON
frames), buffers it durably, and publishes source variables to Convene. Convene's
internal route owns cloud-engine delivery.

Author: LJW.
"""
__version__ = "0.1.0"
