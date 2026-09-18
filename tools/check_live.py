#!/usr/bin/env python3
"""
Check that the live data sources work
=====================================

Run this after putting your LTA AccountKey in .env:

    python tools/check_live.py

It asks each source for a small sample and prints OK or the error, so you can see
exactly which key or endpoint is the problem. It also checks the local backend
(http://localhost:8000) if it happens to be running.

Nothing is written anywhere, and your key is never printed.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATAMALL = os.environ.get("DATAMALL_BASE", "https://datamall2.mytransport.sg/ltaodataservice/")
WEATHER = "https://api-open.data.gov.sg/v2/real-time/api/two-hr-forecast"
BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8000")
OK, BAD, WARN = "  OK  ", " FAIL ", " WARN "


def load_env():
    """Read .env without needing extra packages."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def check(label, fn, key_based=True):
    mark = BAD if key_based else WARN
    try:
        print(f"[{OK}] {label}: {fn()}")
        return True
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            hint = " (key not accepted: check .env, and note a new key can take a while to work)" if key_based \
                   else " (blocked or rate limited; a DATAGOV_API_KEY in .env raises the limit)"
        elif e.code == 429:
            hint = " (rate limited: wait a minute and try again)"
        else:
            hint = ""
        print(f"[{mark}] {label}: HTTP {e.code}{hint}")
    except urllib.error.URLError as e:
        print(f"[{mark}] {label}: cannot reach the server ({e.reason})")
    except Exception as e:
        print(f"[{mark}] {label}: {type(e).__name__}: {e}")
    return False


def main():
    load_env()
    key = os.environ.get("LTA_ACCOUNT_KEY", "").strip()
    print(f"DataMall base : {DATAMALL}")
    print(f"AccountKey    : {'set (' + str(len(key)) + ' characters)' if key else 'MISSING - put it in .env'}\n")
    passed = True

    if key:
        h = {"AccountKey": key, "accept": "application/json"}

        def alerts():
            d = get(DATAMALL + "TrainServiceAlerts", h)
            v = d.get("value", {})
            v = v[0] if isinstance(v, list) and v else v
            segs = v.get("AffectedSegments") or []
            msgs = v.get("Message") or []
            return f"Status={v.get('Status')} · {len(segs)} affected segment(s) · {len(msgs)} message(s)"

        def crowd():
            d = get(DATAMALL + "PCDRealTime?TrainLine=NEL", h)
            rows = d.get("value", [])
            sample = rows[0] if rows else {}
            return f"{len(rows)} station rows · e.g. {sample.get('Station')}={sample.get('CrowdLevel')}"

        def forecast():
            d = get(DATAMALL + "PCDForecast?TrainLine=CCL", h)
            rows = d.get("value", [])
            stations = rows[0].get("Stations", []) if rows else []
            first = stations[0] if stations else {}
            return f"{len(stations)} stations · keys of a station row: {sorted(first)[:4]}"

        def bus():
            d = get(DATAMALL + "v3/BusArrival?BusStopCode=65009", h)
            svc = d.get("Services", [])
            nb = (svc[0].get("NextBus") if svc else {}) or {}
            return f"stop {d.get('BusStopCode')} · {len(svc)} services · e.g. {svc[0].get('ServiceNo') if svc else '-'} Load={nb.get('Load')} Type={nb.get('Type')}"

        def bikes():
            d = get(DATAMALL + "BicycleParkingv2?Lat=1.4087&Long=103.8983&Dist=0.5", h)
            rows = d.get("value", [])
            return f"{len(rows)} racks near Sumang LRT" + (f" · e.g. {rows[0].get('Description')}" if rows else "")

        for label, fn in [("TrainServiceAlerts", alerts), ("PCDRealTime (crowd now)", crowd),
                          ("PCDForecast (crowd later)", forecast), ("v3/BusArrival", bus),
                          ("BicycleParkingv2", bikes)]:
            passed &= check(label, fn)
    else:
        passed = False

    def weather():
        h = {"x-api-key": os.environ["DATAGOV_API_KEY"]} if os.environ.get("DATAGOV_API_KEY") else {}
        d = get(WEATHER, h)
        body = d.get("data", d)
        item = (body.get("items") or [{}])[-1]
        pg = next((f.get("forecast") for f in item.get("forecasts", []) if f.get("area") == "Punggol"), "?")
        return f"{len(body.get('area_metadata', []))} areas · Punggol: {pg}"

    if not check("Weather (data.gov.sg, no key needed)", weather, key_based=False):
        print("       Rain advice will be skipped until this works; everything else still runs.")

    try:
        st = get(BACKEND + "/api/status", timeout=5)
        print(f"\n[{OK}] Backend at {BACKEND}: DataMall key={st['datamall']} · OSRM={st['osrm']}")
        a = get(BACKEND + "/api/alerts", timeout=15)
        print(f"[{OK}] Backend /api/alerts: source={a['source']} · disrupted={a['disrupted']}")
    except Exception:
        print(f"\n[{WARN}] Backend not running at {BACKEND} (start it with: uvicorn backend.main:app --port 8000)")

    print("\n" + ("All LTA sources answered. Open the app and check Settings -> Live data." if passed
                  else "Some LTA sources failed. Fix the FAIL lines above, then run this again."))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
