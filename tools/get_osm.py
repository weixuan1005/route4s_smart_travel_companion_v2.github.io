#!/usr/bin/env python3
"""
Download OpenStreetMap data for the OSRM routing servers
========================================================

Saves the Geofabrik "Malaysia, Singapore and Brunei" extract (the source named in the
PS2 brief) as osrm/foot/sg.osm.pbf and osrm/bike/sg.osm.pbf, ready for `docker compose up`.

    python tools/get_osm.py            # download
    python tools/get_osm.py --clip     # also cut it down to Singapore with osmium (if installed),
                                       # which makes the first OSRM build much faster and lighter

Data (c) OpenStreetMap contributors, ODbL. Distributed by Geofabrik.
"""
import argparse
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

URL = "https://download.geofabrik.de/asia/malaysia-singapore-brunei-latest.osm.pbf"
# Identify the tool. Left to itself urllib sends "Python-urllib/x.y", which distribution
# servers routinely refuse with 403 - the same failure get_map.py hit against Protomaps.
UA = {"User-Agent": "smart-commuter-companion/1.0 (LTA hackathon entry)"}
BBOX = "103.59,1.16,104.09,1.48"
ROOT = Path(__file__).resolve().parent.parent
OSRM = ROOT / "osrm"


def download(dest):
    """Fetch the extract, and refuse to keep a partial one.

    A dropped connection ends the read loop quietly, so without this check the file looks
    finished, the progress bar reaches its last printed figure, and the failure only surfaces
    much later as "PBF error: unexpected EOF" from osmium or a broken OSRM build. A truncated
    download is deleted here instead, where the cause is still obvious."""
    print(f"Downloading {URL}")
    part = dest.with_suffix(dest.suffix + ".part")
    total = done = 0
    try:
        with urllib.request.urlopen(urllib.request.Request(URL, headers=UA), timeout=120) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length", 0))
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"  {done / 1e6:6.0f} / {total / 1e6:.0f} MB", end="\r", flush=True)
        print()
    except Exception as e:
        part.unlink(missing_ok=True)
        sys.exit(f"Download failed after {done / 1e6:.0f} MB: {e}\nRun the command again; nothing partial was kept.")

    if total and done != total:
        part.unlink(missing_ok=True)
        sys.exit(f"Download stopped at {done / 1e6:.0f} MB of {total / 1e6:.0f} MB. The connection dropped, "
                 f"so the file was incomplete and has been deleted.\nRun the command again.")
    if done < 50_000_000:
        part.unlink(missing_ok=True)
        sys.exit(f"The download is only {done / 1e6:.0f} MB, far smaller than this extract should be, "
                 f"so it is not usable. It has been deleted.\nRun the command again.")
    part.replace(dest)


def main():
    ap = argparse.ArgumentParser(description="Get OSM data for the OSRM routing servers.")
    ap.add_argument("--clip", action="store_true", help="cut the extract to Singapore with osmium-tool")
    args = ap.parse_args()

    OSRM.mkdir(exist_ok=True)
    raw = OSRM / "malaysia-singapore-brunei-latest.osm.pbf"
    if not raw.exists():
        download(raw)
    source = raw
    if args.clip:
        if not shutil.which("osmium"):
            sys.exit("osmium is not installed. Install osmium-tool, or run without --clip.")
        source = OSRM / "singapore.osm.pbf"
        subprocess.run(["osmium", "extract", "-b", BBOX, str(raw), "-o", str(source), "--overwrite"], check=True)
    for profile in ("foot", "bike"):
        folder = OSRM / profile
        folder.mkdir(exist_ok=True)
        for old in folder.glob("sg.osrm*"):
            old.unlink()                      # new data: force a rebuild
        (folder / ".ready").unlink(missing_ok=True)
        shutil.copyfile(source, folder / "sg.osm.pbf")
    print(f"Ready: osrm/foot/sg.osm.pbf and osrm/bike/sg.osm.pbf ({source.stat().st_size / 1e6:.0f} MB each)")
    print("Next: docker compose up -d   (the first start builds the routing files)")


if __name__ == "__main__":
    main()
