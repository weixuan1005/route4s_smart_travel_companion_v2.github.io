#!/usr/bin/env python3
"""
Download the offline OpenStreetMap map for Singapore
====================================================

Creates frontend/map/singapore.pmtiles by cutting Singapore out of the
Protomaps daily world basemap (OpenStreetMap data). Only the Singapore
tiles are downloaded, not the whole world file.

    python tools/get_map.py                 # latest build, zoom 0-15
    python tools/get_map.py --maxzoom 14    # smaller file
    python tools/get_map.py --source URL    # use a specific .pmtiles build

It first downloads the `pmtiles` command-line tool (go-pmtiles) for your
system into tools/bin/. Needs Python 3.8+ and internet access.
Map data (c) OpenStreetMap contributors (ODbL), packaged by Protomaps.
"""
import argparse
import datetime
import io
import platform
import stat
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

PMTILES_VERSION = "1.31.2"
RELEASES = f"https://github.com/protomaps/go-pmtiles/releases/download/v{PMTILES_VERSION}/"
BUILDS = "https://build.protomaps.com/"
BBOX = "103.59,1.16,104.09,1.48"  # Singapore, including Tuas, Changi and the offshore islands

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "tools" / "bin"
OUT = ROOT / "frontend" / "map" / "singapore.pmtiles"


def asset_name():
    system = platform.system()
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
    if system == "Linux":
        return f"go-pmtiles_{PMTILES_VERSION}_Linux_{arch}.tar.gz"
    if system == "Darwin":
        return f"go-pmtiles-{PMTILES_VERSION}_Darwin_{arch}.zip"
    if system == "Windows":
        return f"go-pmtiles_{PMTILES_VERSION}_Windows_{arch}.zip"
    sys.exit(f"Unsupported system: {system} {machine}")


def get_tool():
    exe = BIN_DIR / ("pmtiles.exe" if platform.system() == "Windows" else "pmtiles")
    if exe.exists():
        return exe
    name = asset_name()
    print(f"Downloading pmtiles tool ({name})...")
    data = urllib.request.urlopen(RELEASES + name, timeout=120).read()
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            member = next(m for m in z.namelist() if m.split("/")[-1] in ("pmtiles", "pmtiles.exe"))
            exe.write_bytes(z.read(member))
    else:
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            member = next(m for m in t.getmembers() if m.name.split("/")[-1] == "pmtiles")
            exe.write_bytes(t.extractfile(member).read())
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


def latest_build(days=14):
    """Find the newest daily build that exists (builds are named YYYYMMDD.pmtiles)."""
    today = datetime.date.today()
    for back in range(days):
        url = f"{BUILDS}{(today - datetime.timedelta(days=back)):%Y%m%d}.pmtiles"
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status == 200:
                    return url
        except urllib.error.HTTPError:
            continue
        except urllib.error.URLError as e:
            sys.exit(f"Can't reach {BUILDS}: {e.reason}")
    sys.exit(f"No build found in the last {days} days. Check {BUILDS} and pass --source URL.")


def main():
    ap = argparse.ArgumentParser(description="Create frontend/map/singapore.pmtiles from OpenStreetMap data.")
    ap.add_argument("--source", help="URL or path of a Protomaps .pmtiles build (default: latest daily build)")
    ap.add_argument("--maxzoom", type=int, default=15, help="highest zoom level to keep (default 15)")
    args = ap.parse_args()

    tool = get_tool()
    source = args.source or latest_build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"Extracting Singapore from {source} (this downloads only the tiles needed)...")
    subprocess.run([str(tool), "extract", source, str(OUT), f"--bbox={BBOX}", f"--maxzoom={args.maxzoom}"], check=True)
    mb = OUT.stat().st_size / 1e6
    print(f"Wrote {OUT.relative_to(ROOT)} ({mb:.1f} MB)")
    if mb > 95:
        print("Warning: GitHub rejects files over 100 MB. Re-run with --maxzoom 14 to make it smaller.")


if __name__ == "__main__":
    main()
