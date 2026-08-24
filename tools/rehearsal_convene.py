"""Direct-publish Convene bridge for the synthetic rehearsal scenarios.

Convene is *supposed* to read the rehearsal services (`127.0.0.1:8177`-`8181`)
by polling them through heartbeat-delivered collectors. That path is dead while
the backend is missing its `machineCommands` composite index: every heartbeat
500s, no `autoVars` are ever returned, and the agent therefore polls nothing.
See ``deployment/CONVENE_FIRESTORE_INDEX_HANDOVER.md``.

This module inverts the direction. Instead of waiting to be polled, it polls the
scenario locally and *pushes* to ``/machine/publish`` -- the same technique the
gateway's raw audit tap already proves under sustained load. It needs no
collector, so it is unaffected by the missing index.

**Isolation contract.** Per ``deployment/CONVENE_REINTEGRATION_HANDOFF.md``,
rehearsal data is synthetic and must never be mistakable for live state. Each
profile publishes under its own non-live identity and ``rehearsal_*`` prefix,
and this module refuses to emit a live ``sim_`` or legacy ``gw_`` name or to load the
production gateway credential. Those are hard failures, not warnings.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict

log = logging.getLogger("reclaim.rehearsal_convene")

#: Namespaces owned by the two live single-writers. Never emitted from here.
RESERVED_PREFIXES = ("sim_", "gw_")

#: The production gateway credential. A rehearsal identity must never hold a
#: production token, so loading this file is refused outright.
PRODUCTION_CREDENTIAL = r"C:\Windows\System32\config\systemprofile\.convene_agent.json"


@dataclass(frozen=True)
class Profile:
    """One rehearsal experience, exactly as the isolation contract defines it."""

    name: str
    identity: str
    prefix: str
    port: int


#: Transcribed from the isolation contract's table -- not invented here.
PROFILES: Dict[str, Profile] = {
    profile.name: profile
    for profile in (
        Profile("nominal", "reclaim-rehearsal-nominal", "rehearsal_nominal_", 8177),
        Profile("power-outage", "reclaim-rehearsal-outage", "rehearsal_outage_", 8178),
        Profile("lunar", "reclaim-rehearsal-lunar", "rehearsal_lunar_", 8179),
    )
}

#: `start-rehearsal-scenario.ps1` can also run the loss-of-data freshness
#: rehearsal on 8181, but the isolation contract grants it no identity or
#: prefix. Publishing it would mean inventing a non-live identity that nobody
#: has reviewed, so it is refused with an explanation instead.
UNCONTRACTED_PORTS = {"loss-of-data": 8181}


def _scalar(value: Any) -> bool:
    """Mirror the gateway tap: publish only finite scalars, never fabricate."""
    if value is None or not isinstance(value, (str, int, float, bool)):
        return False
    return not isinstance(value, float) or math.isfinite(value)


def state_to_variables(state: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    """Flatten one scenario ``/state`` document into one rehearsal namespace.

    ``/state`` is already a flat scalar surface (``service.py``), so this only
    filters and prefixes. Non-scalars and nulls are dropped rather than coerced:
    a frozen loss-of-data rehearsal must read as stale, not as a last-good value.
    """
    if not prefix.startswith("rehearsal_"):
        raise ValueError(f"rehearsal prefix must start with 'rehearsal_', got {prefix!r}")
    if not isinstance(state, dict):
        raise ValueError("scenario /state did not return a JSON object")

    variables: Dict[str, Any] = {}
    for name, value in state.items():
        if isinstance(name, str) and name and _scalar(value):
            variables[f"{prefix}{name}"] = value

    # Defense in depth. The prefix makes this unreachable, which is the point:
    # if it ever fires, the namespace guarantee broke and we stop rather than
    # write synthetic data into a live namespace.
    for name in variables:
        if name.startswith(RESERVED_PREFIXES):
            raise ValueError("rehearsal publisher must never write live or legacy-prefixed variables")
    return variables


def load_credential(path: str) -> tuple[str, str]:
    """Load a *rehearsal* agent credential, refusing the production one."""
    resolved = os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
    if os.path.normcase(resolved) == os.path.normcase(os.path.abspath(PRODUCTION_CREDENTIAL)):
        raise ValueError(
            "refusing the production gateway credential; a rehearsal identity "
            "must not hold a production token (isolation contract)"
        )
    with open(resolved, encoding="utf-8-sig") as handle:
        credential = json.load(handle)
    token = credential.get("agentToken")
    machine_id = credential.get("machineId")
    if not isinstance(token, str) or not token or not isinstance(machine_id, str):
        raise ValueError("credential must contain agentToken and machineId")
    return token, machine_id


class RehearsalPublisher:
    """Poll one scenario's ``/state`` and push it to one rehearsal identity."""

    def __init__(self, profile: Profile, api: str, credential_path: str,
                 timeout_s: float = 5.0, host: str = "127.0.0.1"):
        self.profile = profile
        self.api = api.rstrip("/")
        self.credential_path = credential_path
        self.timeout_s = timeout_s
        self.state_url = f"http://{host}:{profile.port}/state"
        self._token: str | None = None
        self.machine_id: str | None = None
        self.delivered = 0
        self.failed = 0

    def fetch_state(self) -> Dict[str, Any]:
        request = urllib.request.Request(
            self.state_url, headers={"Accept": "application/json"}, method="GET"
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            if response.status != 200:
                raise RuntimeError(f"scenario /state returned HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))

    def publish(self, variables: Dict[str, Any]) -> None:
        if self._token is None:
            self._token, self.machine_id = load_credential(self.credential_path)
        body = json.dumps({"variables": variables}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api}/machine/publish",
            data=body,
            headers={"Content-Type": "application/json", "X-Agent-Token": self._token},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError(f"HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                self._token = None  # allow a repaired/rotated credential on retry
            raise RuntimeError(f"HTTP {exc.code}") from exc

    def tick(self, dry_run: bool = False) -> Dict[str, Any]:
        """One poll/publish cycle; returns the variables it produced."""
        variables = state_to_variables(self.fetch_state(), self.profile.prefix)
        if not variables:
            raise RuntimeError("scenario /state produced no scalar rehearsal variables")
        if not dry_run:
            self.publish(variables)
        self.delivered += 1
        return variables


def resolve_profile(name: str) -> Profile:
    if name in PROFILES:
        return PROFILES[name]
    if name in UNCONTRACTED_PORTS:
        raise SystemExit(
            f"'{name}' runs on port {UNCONTRACTED_PORTS[name]} but the rehearsal "
            "isolation contract grants it no identity or prefix. Add it to the "
            "contract table in deployment/CONVENE_REINTEGRATION_HANDOFF.md and "
            "to PROFILES before publishing it."
        )
    raise SystemExit(f"unknown profile '{name}'; choose from {sorted(PROFILES)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Push a rehearsal scenario's /state into Convene (no collector needed)"
    )
    parser.add_argument("profile", help=f"one of {sorted(PROFILES)}")
    parser.add_argument("--api", default=os.environ.get("CONVENE_API", ""),
                        help="Convene API base, e.g. https://<backend>/api (or $CONVENE_API)")
    parser.add_argument("--credential", default=os.environ.get("REHEARSAL_CONVENE_CREDENTIAL", ""),
                        help="path to this rehearsal identity's agent credential JSON")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between pushes")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--once", action="store_true", help="single cycle, then exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the variables instead of publishing; mutates nothing")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    profile = resolve_profile(args.profile)

    # --dry-run proves the mapping without touching Convene, so it needs no
    # credential and no API base. Publishing requires both, stated up front
    # rather than failing halfway through the first cycle.
    if not args.dry_run:
        if not args.api:
            raise SystemExit("--api (or $CONVENE_API) is required unless --dry-run")
        if not args.credential:
            raise SystemExit(
                "--credential (or $REHEARSAL_CONVENE_CREDENTIAL) is required unless "
                "--dry-run; it must be this rehearsal identity's own credential, "
                "never the production gateway token"
            )

    publisher = RehearsalPublisher(profile, args.api, args.credential, args.timeout)
    log.info("rehearsal publisher: %s -> identity %s, prefix %s%s",
             publisher.state_url, profile.identity, profile.prefix,
             " [DRY RUN, publishing nothing]" if args.dry_run else "")

    while True:
        try:
            variables = publisher.tick(dry_run=args.dry_run)
            if args.dry_run:
                log.info("%d variables:\n%s", len(variables),
                         json.dumps(variables, indent=2, sort_keys=True))
            else:
                log.info("published %d variables (%d ok, %d failed)",
                         len(variables), publisher.delivered, publisher.failed)
        except Exception as exc:
            publisher.failed += 1
            log.warning("rehearsal publish cycle failed (%d total): %s",
                        publisher.failed, exc)
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(max(0.5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
