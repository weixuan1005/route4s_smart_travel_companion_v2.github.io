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
    python tools/get_covered.py --tiles 4            # smaller requests if the server keeps timing out
    python tools/get_covered.py --server https://overpass.kumi.systems/api/interpreter

The whole island in one request is what makes the public Overpass instances answer 504,
so this asks tile by tile, retries while a server reports itself busy (429, 502, 503, 504)
and moves on to a mirror if one keeps failing. Ways that straddle a tile border are
returned twice and de-duplicated by way id.

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
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "covered.json"

# The public Overpass instances are donated infrastructure and the main one often answers 504
# under load. Ask the next one rather than hammering the first.
SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
BBOX = (1.16, 103.59, 1.48, 104.09)  # Singapore: south, west, north, east
TILES = 3        # the whole island in one request is what times out; ask tile by tile
RETRY = (2, 4, 8, 16)
BUSY = (429, 502, 503, 504)
# Kept client-side: an exact tag match is far cheaper for Overpass than a regex over the bbox.
KEEP = {"footway", "path", "pedestrian", "corridor", "steps", "cycleway", "living_street"}


def tile_query(south, west, north, east):
    box = f"{south:.4f},{west:.4f},{north:.4f},{east:.4f}"
    return f"""
[out:json][timeout:120];
(
  way["covered"="yes"]["highway"]({box});
  way["covered"="roof"]["highway"]({box});
  way["covered"="arcade"]["highway"]({box});
  way["tunnel"="building_passage"]["highway"]({box});
);
out geom;
"""


def tiles(bbox, n):
    south, west, north, east = bbox
    dlat, dlon = (north - south) / n, (east - west) / n
    for i in range(n):
        for j in range(n):
            yield (south + i * dlat, west + j * dlon, south + (i + 1) * dlat, west + (j + 1) * dlon)


def post(server, query, timeout=300):
    req = urllib.request.Request(server, data=query.encode("utf-8"),
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "User-Agent": "smart-commuter-companion/1.0 (hackathon entry)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fetch_tile(servers, query, label):
    """One tile, retried while the server says it is busy, then on the next server.

    `servers` is reordered in place: whichever endpoint answers moves to the front and a
    failing one moves to the back, so a dead or overloaded server is tried once, not once
    per tile. Waiting out a backoff only makes sense for a server that is up and busy, so
    an unreachable host is dropped immediately instead."""
    last = ""
    for server in list(servers):
        for wait in (0,) + RETRY:
            if wait:
                print(f"  {label}: {last}, retrying in {wait}s...")
                time.sleep(wait)
            try:
                data = post(server, query)
                servers.remove(server); servers.insert(0, server)
                return data
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                if e.code not in BUSY:
                    break          # a real error: another try will not help
            except urllib.error.URLError as e:
                last = str(e.reason)
                break              # unreachable: another server is the better bet
            except (TimeoutError, json.JSONDecodeError) as e:
                last = type(e).__name__
        servers.remove(server); servers.append(server)
        if len(servers) > 1:
            print(f"  {label}: {last} from {server.split('/')[2]}, trying another server...")
    raise RuntimeError(last or "no server answered")


def main():
    ap = argparse.ArgumentParser(description="Write frontend/covered.json from OpenStreetMap covered walkways.")
    ap.add_argument("--out", default=str(OUT), help=f"output file (default: {OUT.relative_to(ROOT)})")
    ap.add_argument("--server", action="append", help="Overpass endpoint; repeat to set the order "
                                                      "(default: overpass-api.de, then two mirrors)")
    ap.add_argument("--tiles", type=int, default=TILES, help=f"split the island into N x N requests (default {TILES})")
    args = ap.parse_args()
    servers = list(args.server or SERVERS)

    box = list(tiles(BBOX, args.tiles))
    print(f"Asking Overpass for Singapore's covered footways and cycleways, in {len(box)} tiles...")
    seen, skipped = {}, 0
    for n, t in enumerate(box, 1):
        try:
            data = fetch_tile(servers, tile_query(*t), f"tile {n}/{len(box)}")
        except RuntimeError as e:
            sys.exit(f"Tile {n} failed on every server ({e}). The public instances are busy; wait a few "
                     f"minutes and run this again, or pass --server with an endpoint of your own.")
        for el in data.get("elements", []):
            if el.get("id") in seen:
                continue           # ways on a tile border come back in both tiles
            if (el.get("tags") or {}).get("highway") not in KEEP:
                skipped += 1
                continue
            line = [[round(p["lat"], 6), round(p["lon"], 6)] for p in el.get("geometry") or [] if "lat" in p]
            if len(line) > 1:
                seen[el["id"]] = line
        print(f"  tile {n}/{len(box)}: {len(seen):,} covered ways so far")

    ways = list(seen.values())
    points = sum(len(w) for w in ways)
    if not ways:
        sys.exit("Overpass returned no covered ways. That is unexpected: check the query or try again later.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "generated": datetime.date.today().isoformat(),
        "source": "OpenStreetMap via Overpass API",
        "attribution": "© OpenStreetMap contributors (ODbL)",
        "bbox": list(BBOX),
        "ways": ways,
    }, separators=(",", ":")), encoding="utf-8")
    mb = out.stat().st_size / 1e6
    print(f"Wrote {out} - {len(ways):,} covered ways, {points:,} points, {mb:.1f} MB"
          + (f" ({skipped:,} non-path ways ignored)" if skipped else ""))
    print("Reload the app: Settings shows the sheltered walkway layer, and the map draws it.")


if __name__ == "__main__":
    main()
