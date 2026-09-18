#!/usr/bin/env python3
"""
Smart Travel Companion - sheltered walkway downloader
=====================================================

Downloads Singapore's covered walkways, linkways and sheltered paths from
OpenStreetMap through the Overpass API and writes `frontend/covered.json`,
which the app draws on the map and uses to say whether a walking leg is
sheltered.

    python tools/get_covered.py                      # writes frontend/covered.json
    python tools/get_covered.py --out somewhere.json
    python tools/get_covered.py --server https://overpass.kumi.systems/api/interpreter

What it asks OpenStreetMap for, inside the Singapore bounding box:

  * foot and cycle ways tagged covered=yes / roof / arcade - the covered
    linkways, HDB void-deck walkways and sheltered cycling paths
  * foot and cycle ways tagged tunnel=building_passage, which is how a path
    running through a building is mapped

Only geometry is kept, rounded to six decimals (about 10 cm), so the file
stays small enough to serve from static hosting.

OpenStreetMap data is licensed under the ODbL: the app credits
"(c) OpenStreetMap contributors" wherever this data is shown. Overpass runs on
donated infrastructure, so this fetches once and writes a file rather than
querying in a loop - run it again when you want fresher data.

LTA DataMall's CoveredLinkWay layer is the authoritative source for covered
linkways and can be layered on top of this later; it ships as a shapefile
download rather than JSON, so it needs different tooling.

Needs Python 3.8+ and internet access. No extra packages.
"""
import argparse
import datetime
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "covered.json"
SERVER = "https://overpass-api.de/api/interpreter"
BBOX = "1.16,103.59,1.48,104.09"  # Singapore: south,west,north,east
WAYS = "^(footway|path|pedestrian|corridor|steps|cycleway|living_street)$"

QUERY = f"""
[out:json][timeout:180];
(
  way["highway"~"{WAYS}"]["covered"~"^(yes|roof|arcade)$"]({BBOX});
  way["highway"~"{WAYS}"]["tunnel"="building_passage"]({BBOX});
);
out geom;
"""


def fetch(server, query):
    req = urllib.request.Request(server, data=query.encode("utf-8"),
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "User-Agent": "smart-commuter-companion/1.0 (hackathon entry)"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser(description="Write frontend/covered.json from OpenStreetMap covered walkways.")
    ap.add_argument("--out", default=str(OUT), help=f"output file (default: {OUT.relative_to(ROOT)})")
    ap.add_argument("--server", default=SERVER, help="Overpass endpoint (default: overpass-api.de)")
    args = ap.parse_args()

    print(f"Asking {args.server} for Singapore's covered footways and cycleways...")
    try:
        data = fetch(args.server, QUERY)
    except urllib.error.HTTPError as e:
        sys.exit(f"Overpass answered HTTP {e.code}. It rate-limits heavy use; wait a minute and try again, "
                 f"or pass --server with another endpoint.")
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach Overpass ({e.reason}).")

    ways, points = [], 0
    for el in data.get("elements", []):
        line = [[round(p["lat"], 6), round(p["lon"], 6)] for p in el.get("geometry") or [] if "lat" in p]
        if len(line) > 1:
            ways.append(line)
            points += len(line)
    if not ways:
        sys.exit("Overpass returned no covered ways. That is unexpected: check the query or try again later.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "generated": datetime.date.today().isoformat(),
        "source": "OpenStreetMap via Overpass API",
        "attribution": "© OpenStreetMap contributors (ODbL)",
        "bbox": [float(v) for v in BBOX.split(",")],
        "ways": ways,
    }, separators=(",", ":")), encoding="utf-8")
    mb = out.stat().st_size / 1e6
    print(f"Wrote {out} - {len(ways):,} covered ways, {points:,} points, {mb:.1f} MB")
    print("Reload the app: Settings shows the sheltered walkway layer, and the map draws it.")


if __name__ == "__main__":
    main()
