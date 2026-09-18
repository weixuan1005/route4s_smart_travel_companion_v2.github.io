#!/usr/bin/env python3
"""
Smart Travel Companion - bus data downloader
============================================

Downloads Singapore bus stops, bus routes and bus services from LTA DataMall
and writes a compact `busdata.json` that the app (index.html) loads to show
REAL bus routes. Arrival times in the app stay simulated.

Usage
-----
1. Register for a free AccountKey at https://datamall.lta.gov.sg
2. Run (Python 3.8+, no extra packages needed):

       python fetch_bus_data.py --key YOUR_ACCOUNT_KEY

   or set the key once in your terminal:

       export LTA_ACCOUNT_KEY=YOUR_ACCOUNT_KEY        (macOS / Linux)
       set LTA_ACCOUNT_KEY=YOUR_ACCOUNT_KEY           (Windows cmd)
       python fetch_bus_data.py

3. Upload the generated busdata.json next to index.html in your GitHub repo.

No key? Use the republished LTA data from BusRouter SG instead:

       python fetch_bus_data.py --no-key

Optional:
   --embed index.html   also copies the data INTO index.html, so the page works
                        even when opened straight from your computer (file://).
   --out PATH           where to write the JSON (default: busdata.json)

Your AccountKey is only used on your computer. It is never written to the
output files, so it is safe to publish busdata.json.
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "https://datamall2.mytransport.sg/ltaodataservice/"
PAGE = 500  # DataMall returns at most 500 records per call


def fetch_all(endpoint, key):
    """Fetch every record of a DataMall dataset, following the $skip paging."""
    records, skip = [], 0
    while True:
        url = f"{BASE}{endpoint}?$skip={skip}"
        req = urllib.request.Request(url, headers={"AccountKey": key, "accept": "application/json"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    page = json.load(resp).get("value", [])
                break
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    sys.exit(f"DataMall refused the request ({e.code}). Check your AccountKey.")
                if attempt == 4:
                    raise
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                if attempt == 4:
                    raise
            time.sleep(2 * (attempt + 1))
        records.extend(page)
        print(f"  {endpoint}: {len(records)} records", end="\r", flush=True)
        if len(page) < PAGE:
            break
        skip += PAGE
        time.sleep(0.15)  # be polite to the API
    print(f"  {endpoint}: {len(records)} records")
    return records


def _num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _freq(svc):
    """Pick a representative headway like '08-12' from BusServices."""
    for field in ("AM_Offpeak_Freq", "PM_Offpeak_Freq", "AM_Peak_Freq", "PM_Peak_Freq"):
        v = (svc.get(field) or "").strip()
        if re.fullmatch(r"\d{1,2}(-\d{1,2})?", v) and v not in ("0", "00", "0-0", "00-00", "-"):
            return v
    return ""


def _hhmm(v):
    """DataMall writes first/last bus as "0530" or "2400"; blanks and dashes mean unknown."""
    t = str(v or "").strip()
    if len(t) != 4 or not t.isdigit():
        return None
    h, m = int(t[:2]), int(t[2:])
    if h > 28 or m > 59:            # 24xx and 25xx are normal here; 30xx is not
        return None
    return f"{h:02d}:{m:02d}"


def _service_hours(routes_raw):
    """First and last bus per service direction, taken at its first stop.

    BusRoutes carries these on every stop of the route. The one that answers "can I still
    catch this service?" for someone starting a journey is the origin's, so that is the row
    kept - the earliest StopSequence. It is an approximation further along the route, and the
    app says so rather than implying a per-stop timetable it does not have.
    """
    best = {}
    for r in routes_raw:
        key = f"{str(r.get('ServiceNo', '')).strip()}|{r.get('Direction', 1)}"
        try:
            seq = int(r.get("StopSequence") or 0)
        except (TypeError, ValueError):
            continue
        if key in best and best[key][0] <= seq:
            continue
        hours = {}
        for day, prefix in (("wd", "WD"), ("sat", "SAT"), ("sun", "SUN")):
            first = _hhmm(r.get(f"{prefix}_FirstBus"))
            last = _hhmm(r.get(f"{prefix}_LastBus"))
            if first and last:
                hours[day] = [first, last]
        best[key] = (seq, hours)
    return {k: v[1] for k, v in best.items() if v[1]}


def build(stops_raw, routes_raw, services_raw):
    """Turn raw DataMall records into the compact format used by the app."""
    stops = {}
    for s in stops_raw:
        code = str(s.get("BusStopCode", "")).zfill(5)
        lat, lon = _num(s.get("Latitude")), _num(s.get("Longitude"))
        if not code.strip("0") or not lat or not lon:
            continue  # skip stops without a usable position
        stops[code] = [
            (s.get("Description") or code).strip(),
            (s.get("RoadName") or "").strip(),
            round(lat, 6),
            round(lon, 6),
        ]

    grouped = {}
    for r in routes_raw:
        code = str(r.get("BusStopCode", "")).zfill(5)
        if code not in stops:
            continue
        key = f"{str(r.get('ServiceNo', '')).strip()}|{r.get('Direction', 1)}"
        grouped.setdefault(key, []).append((int(r.get("StopSequence") or 0), code, _num(r.get("Distance"))))

    routes = {}
    for key, rows in grouped.items():
        rows.sort()
        codes, dists = [], []
        for _, code, dist in rows:
            if codes and codes[-1] == code:
                continue  # drop repeated consecutive stops
            if dist is None:  # fill gaps with a typical 400 m between stops
                dist = (dists[-1] + 0.4) if dists else 0.0
            if dists and dist < dists[-1]:
                dist = dists[-1]  # distances must not go backwards
            codes.append(code)
            dists.append(round(dist, 2))
        if len(codes) >= 2:
            routes[key] = [codes, dists]

    hours = _service_hours(routes_raw)
    services = {}
    for s in services_raw:
        key = f"{str(s.get('ServiceNo', '')).strip()}|{s.get('Direction', 1)}"
        if key in routes:
            services[key] = [s.get("Operator", ""), s.get("Category", ""), _freq(s),
                             (s.get("LoopDesc") or "").strip(), hours.get(key) or None]

    return {
        "version": 1,
        "source": "LTA DataMall (BusStops, BusRoutes, BusServices)",
        "generated": datetime.date.today().isoformat(),
        "stops": stops,
        "routes": routes,
        "services": services,
    }


BUSROUTER_BASE = "https://raw.githubusercontent.com/cheeaun/sgbusdata/main/data/v1/"


def _get(url, as_json=True):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "smart-travel-companion"}), timeout=60) as resp:
                return json.load(resp) if as_json else resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


def _km(lat1, lon1, lat2, lon2):
    from math import asin, cos, radians, sin, sqrt
    h = sin(radians(lat2 - lat1) / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(lon2 - lon1) / 2) ** 2
    return 12742 * asin(sqrt(h))


def build_from_busrouter():
    """No key needed: LTA stops and routes republished by BusRouter SG (github.com/cheeaun/sgbusdata)."""
    print("Downloading from BusRouter SG (no key needed)...")
    services = _get(BUSROUTER_BASE + "services.min.json")
    stops_in = _get(BUSROUTER_BASE + "stops.min.json")
    try:
        updated = _get(BUSROUTER_BASE + "last-updated.txt", as_json=False).strip().strip('"')[:10]
    except Exception:
        updated = datetime.date.today().isoformat()
    stops = {code: [v[2] or code, v[3] or "", v[1], v[0]] for code, v in stops_in.items() if v[0] and v[1]}
    routes = {}
    for svc, info in services.items():
        for d, codes in enumerate(info.get("routes", [])):
            ok = []
            for c in codes:
                if c in stops and (not ok or ok[-1] != c):
                    ok.append(c)
            if len(ok) < 2:
                continue
            dists, km = [0.0], 0.0
            for a, b in zip(ok, ok[1:]):
                km += _km(stops[a][2], stops[a][3], stops[b][2], stops[b][3]) * 1.2  # road vs straight line
                dists.append(round(km, 2))
            routes[f"{svc}|{d + 1}"] = [ok, dists]
    return {
        "version": 1,
        "source": "LTA data via BusRouter SG (cheeaun/sgbusdata)",
        "label": "busdata.json (BusRouter SG)",
        "attribution": "LTA data via BusRouter SG",
        "generated": updated,
        "stops": stops,
        "routes": routes,
        "services": {},
    }


def embed(html_path, data_json):
    """Copy the data into index.html between the busdata script tags."""
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    safe = data_json.replace("</", "<\\/")  # keep the JSON from closing the tag early
    pattern = re.compile(r'(<script type="application/json" id="busdata">)(.*?)(</script>)', re.S)
    if not pattern.search(html):
        sys.exit(f"Couldn't find the busdata placeholder in {html_path}. Use the latest index.html.")
    html = pattern.sub(lambda m: m.group(1) + safe + m.group(3), html, count=1)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Embedded bus data into {html_path}")


def main():
    ap = argparse.ArgumentParser(description="Download LTA DataMall bus data for Smart Travel Companion.")
    ap.add_argument("--key", default=os.environ.get("LTA_ACCOUNT_KEY"), help="LTA DataMall AccountKey (or set LTA_ACCOUNT_KEY)")
    ap.add_argument("--out", default="busdata.json", help="output file (default: busdata.json)")
    ap.add_argument("--embed", metavar="HTML", help="also embed the data into this HTML file, e.g. index.html")
    ap.add_argument("--no-key", action="store_true", help="use LTA data republished by BusRouter SG (no AccountKey needed)")
    args = ap.parse_args()

    if args.no_key:
        data = build_from_busrouter()
    else:
        if not args.key:
            sys.exit("No AccountKey. Use --key YOUR_KEY, set LTA_ACCOUNT_KEY, or run with --no-key.")
        print("Downloading from LTA DataMall (this can take a minute or two)...")
        stops_raw = fetch_all("BusStops", args.key)
        services_raw = fetch_all("BusServices", args.key)
        routes_raw = fetch_all("BusRoutes", args.key)
        data = build(stops_raw, routes_raw, services_raw)
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    with_hours = sum(1 for v in data.get("services", {}).values() if len(v) > 4 and v[4])
    print(f"Wrote {args.out}: {len(data['stops'])} stops, {len(data['routes'])} service directions, "
          f"{len(text) / 1e6:.1f} MB")
    if with_hours:
        print(f"  first/last bus times for {with_hours} service directions")
    else:
        print("  no first/last bus times in this source: the app will not filter buses by hour")
    if args.embed:
        embed(args.embed, text)
    print("Done. Upload busdata.json (and index.html) to your GitHub repo.")


if __name__ == "__main__":
    main()
