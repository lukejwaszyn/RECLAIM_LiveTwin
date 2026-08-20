#!/usr/bin/env python3
"""
redteam_ingest.py — live acceptance harness for the RECLAIM cloud engine endpoint.

A fake edge gateway that emits `reclaim.telemetry.v1` envelopes carrying the REAL
cRIO/LabVIEW terminology (MW_power in provisionally W,
PL_bottom1..4 / PL_surface_temp in degC, PL_chamber_pressure in Torr), pushes them at the engine (ideally THROUGH the
Cloudflare tunnel), and asserts two things end to end:

  A. INGEST PIPELINE CONTRACT is intact — auth on /ingest, read-token gating on
     the GET routes, harness-mode refused under --production, stale rejection,
     duplicate / monotone-sequence dedup.
  B. AUTONOMOUS LIFECYCLE behaves — a mid-batch POWER CUT does NOT reset the
     engine (metrics freeze and resume in place), and a NEW batch (cycle_id
     turnover) DOES reset per-cycle analytics (charge mass recharges, active
     heating / energy zero). See docs/RECLAIM_Predictive_Engine_Lifecycle_Memo.md.

This is the go-live gate for the endpoint that previously required a reboot: run it
after deploy, before wiring Convene. A clean 20/20 means the reboot dependency is
gone and the pipeline is unchanged.

Usage (tokens are read from the environment so they do not enter the process list):
    RECLAIM_INGEST_TOKEN=<T> RECLAIM_READ_TOKEN=<T> \
      python3 redteam_ingest.py --url https://<host>
    # restricted-DNS networks (can't resolve the tunnel host): pin the visitor edge
    python3 redteam_ingest.py --url https://<host> ... --pin-ip 104.16.230.132

Exit code 0 iff every check passes.
"""
from __future__ import annotations
import argparse, json, os, sys, time, uuid
from datetime import datetime, timezone, timedelta

import requests


def main() -> int:
    ap = argparse.ArgumentParser(description="RECLAIM cloud-engine live acceptance harness")
    ap.add_argument("--url", required=True, help="engine base URL (tunnel hostname), e.g. https://x.trycloudflare.com")
    ap.add_argument("--ingest-token", default=os.environ.get("RECLAIM_INGEST_TOKEN", ""),
                    help="POST /ingest bearer (prefer RECLAIM_INGEST_TOKEN environment variable)")
    ap.add_argument("--read-token", default=os.environ.get("RECLAIM_READ_TOKEN", ""),
                    help="GET bearer (prefer RECLAIM_READ_TOKEN environment variable)")
    ap.add_argument("--pin-ip", default=None, help="optional: force-resolve the URL host to this IP (restricted DNS)")
    ap.add_argument("--chamber", default="PL", choices=["PL", "MT"], help="chamber to exercise")
    args = ap.parse_args()

    if not args.ingest_token or not args.read_token:
        ap.error("RECLAIM_INGEST_TOKEN and RECLAIM_READ_TOKEN are required")

    base, ingest, read = args.url.rstrip("/"), args.ingest_token, args.read_token
    if args.pin_ip:
        import socket
        from urllib.parse import urlparse
        hn = urlparse(base).hostname
        orig = socket.getaddrinfo
        socket.getaddrinfo = lambda host, *a, **k: orig(args.pin_ip if host == hn else host, *a, **k)

    RUN, SRC, CH = "acc-" + uuid.uuid4().hex[:8], "cRIO-accept", args.chamber
    results: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))

    def now(off=0.0):
        return (datetime.now(timezone.utc) + timedelta(seconds=off)).isoformat().replace("+00:00", "Z")

    def lv(bed_c, wall_c, mw, process=True, p_torr=37.5031):
        # Raw LabVIEW names + degC/Torr/provisional-W, pre-normalization.
        # 37.5031 Torr retains the former fixture's physical intent of ~5 kPa.
        pre = "PL_" if CH == "PL" else "MT_"
        d = {"MW_power": mw, "MW_reverse": mw * 0.02, "MW_RF": True, "MW_status": True, "MW_freq": 2.45e9}
        if CH == "PL":
            d.update({"PL_bottom1": bed_c, "PL_bottom2": bed_c + 1, "PL_bottom3": bed_c - 1,
                      "PL_bottom4": bed_c, "PL_surface_temp": wall_c,
                      "PL_chamber_pressure": p_torr, "PL_output_pressure": p_torr * 1.02,
                      "PL_process": process, "PL_chamber_pump": True})
        else:
            d.update({"MT_bottom": bed_c, "MT_top": wall_c})
        return d

    def env(seq, cid, op, vars_, mode="live", ts=None):
        return {"schema_version": "reclaim.telemetry.v1", "mode": mode, "run_id": RUN,
                "source_id": SRC, "seq": seq, "ts": ts or now(), "cycle_id": cid,
                "source_op_state": op, "active_chamber": CH, "vars": vars_}

    def _retry(fn):
        last = None
        for _ in range(10):
            try:
                r = fn()
            except requests.exceptions.RequestException:
                time.sleep(1.5); continue
            if r.status_code >= 500:          # account-less quick-tunnel 530/5xx blip — retry
                last = r; time.sleep(1.5); continue
            return r
        return last

    def post(frames, token=ingest):
        body = "\n".join(json.dumps(f) for f in frames).encode()
        h = {"Content-Type": "application/x-ndjson"}
        if token:
            h["Authorization"] = "Bearer " + token
        return _retry(lambda: requests.post(base + "/ingest", data=body, headers=h, timeout=30))

    def get(path, token=None):
        h = {"Authorization": "Bearer " + token} if token else {}
        return _retry(lambda: requests.get(base + path, headers=h, timeout=30))

    def rj(r):
        try:
            return r.json()
        except Exception:
            return {}

    P = f"{CH}_"   # published-state prefix

    print(f"\n== A. Ingest pipeline / infrastructure integrity ({base}) ==")
    r = get("/health"); check("/health open (no auth) 200", r.status_code == 200 and rj(r).get("ok"), str(r.status_code))
    r = get("/state"); check("/state requires read token (401)", r.status_code == 401, str(r.status_code))
    r = get("/state", read); check("/state with read token (200)", r.status_code == 200, str(r.status_code))
    r = post([env(1, "A", "S_MicrowaveHeating", lv(300, 180, 2000))], token=""); check("POST /ingest no token -> 401", r.status_code == 401, str(r.status_code))
    res = {}
    for _ in range(5):
        res = rj(post([env(90001, "A", "S_MicrowaveHeating", lv(300, 180, 2000), mode="harness")])).get("results", [{}])[0]
        if res.get("code"): break
        time.sleep(1.0)
    check("harness mode rejected in --production", res.get("status") == "rejected" and res.get("code") == "mode_rejected", str(res.get("code")))
    res = rj(post([env(90002, "A", "S_MicrowaveHeating", lv(300, 180, 2000), ts=now(-60))])).get("results", [{}])[0]
    check("stale frame rejected/final", res.get("status") == "rejected" and res.get("code") == "timestamp_stale" and res.get("final"), str(res.get("code")))

    print("\n== B. Autonomous lifecycle through the full pipeline ==")
    seq = 1
    def drive(op, cid, mw, bed_c, wall_c, n=1):
        nonlocal seq
        for _ in range(n):
            st = rj(post([env(seq, cid, op, lv(bed_c, wall_c, mw))])).get("results", [{}])[0]
            assert st.get("status") == "accepted", f"seq {seq} {op}: {st}"
            seq += 1; time.sleep(0.05)

    drive("S_BatchLoad", "A", 0.0, 47, 40, 1)
    drive("S_MicrowaveHeating", "A", 2000.0, 327, 177, 12)
    s = rj(get("/state", read))
    check("state schema reclaim.state.v1", s.get("schema_version") == "reclaim.state.v1", str(s.get("schema_version")))
    check("mode=live, run_id present", s.get("mode") == "live" and s.get("run_id") == RUN, f"{s.get('mode')}/{s.get('run_id')}")
    check(f"{CH} phase ACTIVE while heating", s.get(P + "engine_phase") == "ACTIVE", str(s.get(P + "engine_phase")))
    heat = s.get(P + "active_heating_s"); mass = s.get(P + "charge_mass_kg")
    check("charge mass decayed within batch (<1.0)", mass is not None and mass < 1.0, str(mass))
    check("active_heating_s accumulating", heat and heat > 0, str(heat))
    res = rj(post([env(seq - 1, "A", "S_MicrowaveHeating", lv(327, 177, 2000))])).get("results", [{}])[0]
    check("duplicate seq -> duplicate", res.get("status") == "duplicate", str(res.get("status")))
    res = rj(post([env(1, "A", "S_MicrowaveHeating", lv(327, 177, 2000))])).get("results", [{}])[0]
    check("backward seq -> duplicate (monotone)", res.get("status") == "duplicate", str(res.get("status")))

    drive("S_PowerInterrupted", "A", 0.0, 287, 150, 6)
    s = rj(get("/state", read))
    check(f"{CH} phase SUSPENDED on power cut", s.get(P + "engine_phase") == "SUSPENDED", str(s.get(P + "engine_phase")))
    check("active_heating FROZEN across cut (no reset)", abs((s.get(P + "active_heating_s") or -1) - heat) < 1e-6, f"{s.get(P + 'active_heating_s')} vs {heat}")
    check("charge mass NOT recharged during suspend", (s.get(P + "charge_mass_kg") or 9) <= mass + 1e-9, str(s.get(P + "charge_mass_kg")))

    drive("S_MicrowaveHeating", "A", 2000.0, 337, 187, 8)
    s = rj(get("/state", read))
    check("resume -> ACTIVE, heating RESUMED (> pre-cut)", s.get(P + "engine_phase") == "ACTIVE" and (s.get(P + "active_heating_s") or 0) > heat, f"{s.get(P + 'active_heating_s')} > {heat}")

    drive("S_Complete", "A", 0.0, 250, 120, 1)
    drive("S_BatchLoad", "B", 0.0, 47, 40, 1)
    s = rj(get("/state", read))
    m2 = s.get(P + "charge_mass_kg"); a2 = s.get(P + "active_heating_s"); e2 = s.get(P + "consumed_energy_wh")
    check("new cycle_id -> charge mass RECHARGED (~mf_m0)", m2 is not None and m2 > mass, str(m2))
    check("new cycle_id -> active_heating RESET (~0)", a2 is not None and a2 < 1e-6, str(a2))
    check("new cycle_id -> energy RESET (~0)", e2 is not None and e2 < 1e-6, str(e2))

    n_pass = sum(1 for _, ok, _ in results if ok)
    print(f"\n==== ACCEPTANCE RESULT: {n_pass}/{len(results)} checks passed ====")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
