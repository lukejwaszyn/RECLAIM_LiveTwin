"""RECLAIM Edge Gateway — read-only status HTTP endpoint.

Makes the gateway *readable* locally without opening additional inbound ports
in the production sense: this is a small localhost HTTP server that a tunnel
(cloudflared / ngrok / tailscale) exposes over an OUTBOUND-initiated connection.

Endpoints (GET, JSON):
    /health   gateway metrics — rx, tx, queue depth, drops, last-ack age, uptime
    /latest   the most recent canonical telemetry frame the gateway received
    /         index of the above

Stdlib only (http.server) so there is nothing extra to install on the gateway.

Author: LJW.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("reclaim_edge.status")


class StatusServer(threading.Thread):
    def __init__(self, port, receiver, publisher, buffer, src):
        super().__init__(name="status", daemon=True)
        self.port = port
        self.receiver = receiver
        self.publisher = publisher
        self.buffer = buffer
        self.src = src
        self.t0 = time.time()
        self._httpd = None

    def _payload(self, path):
        if path.startswith("/latest"):
            return self.receiver.last_frame or {"note": "no frame received yet"}
        if path.startswith("/command"):
            # Bidirectional relay: the digital twin's ControlCommand rides back
            # in each /ingest response; the control hub / HMI polls it here.
            # command_age_s lets the HMI treat a stale command as invalid the
            # same way Convene gates stale state.
            cmd = self.publisher.last_command
            age = self.publisher.last_command_age
            return {"command": cmd or {"note": "no command received yet"},
                    "command_age_s": round(age, 2) if age is not None else None}
        if path.startswith("/health"):
            return {
                "src": self.src,
                "uptime_s": round(time.time() - self.t0, 1),
                "received": self.receiver.received,
                "delivered": self.publisher.delivered,
                "queue_depth": self.buffer.depth(),
                "drops": self.buffer.drops,
                "dead_letter": self.buffer.dead_letter_count(),
                "dead_lettered_session": self.publisher.dead_lettered,
                "last_ack_age_s": round(self.publisher.last_ack_age, 2),
                "transport": self.publisher.cfg.transport,
            }
        return {
            "service": "reclaim-edge-gateway",
            "src": self.src,
            "endpoints": ["/health", "/latest", "/command"],
        }

    def run(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps(server._payload(self.path), indent=2).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):  # silence default access logging
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        log.info("status endpoint on http://127.0.0.1:%d (/health, /latest)", self.port)
        self._httpd.serve_forever(poll_interval=0.5)

    def shutdown(self):
        if self._httpd:
            self._httpd.shutdown()
