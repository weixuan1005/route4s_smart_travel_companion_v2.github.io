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


def build_exists(url):
    """Is this build there? Asks for a single byte rather than sending HEAD, because some CDNs
    refuse HEAD outright - and a refused HEAD looks exactly like a missing file. Returns the
    status so the caller can tell "not there yet" (404) from "not allowed" (403/405)."""
    req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status in (200, 206), r.status
    except urllib.error.HTTPError as e:
        return False, e.code


def latest_build(days=14):
    """Find the newest daily build that exists (builds are named YYYYMMDD.pmtiles)."""
    today = datetime.date.today()
    seen = []
    for back in range(days):
        url = f"{BUILDS}{(today - datetime.timedelta(days=back)):%Y%m%d}.pmtiles"
        try:
            ok, status = build_exists(url)
        except urllib.error.URLError as e:
            sys.exit(f"Can't reach {BUILDS}: {e.reason}")
        if ok:
            return url
        seen.append(status)

    codes = sorted(set(seen))
    detail = f"every request came back {codes[0]}" if len(codes) == 1 else f"requests came back {codes}"
    hint = ("The server is refusing these requests rather than saying the file is missing, so the "
            "builds may have moved or your network may be blocking them."
            if codes and codes[0] in (401, 403, 405, 451) else
            "The daily builds may have been renamed or pruned.")
    sys.exit(f"No build found in the last {days} days ({detail}). {hint}\n"
             f"Open {BUILDS} in a browser, copy the newest .pmtiles file name, and pass it:\n"
             f"    python tools/get_map.py --source {BUILDS}YYYYMMDD.pmtiles")


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
