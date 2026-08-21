"""Gate 2 offline contract for the cRIO source-assembled USB record.

Modules:
    evidence_parser  strict fail-closed parser for the legacy name:value record
    frame_builder    build the one-object+LF JSON source frame (contract section 4)

This package is repository-only and side-effect free. It touches no cRIO, opens no
socket, and runs no VI. See ``README.md`` and the deployment decision record.
"""
