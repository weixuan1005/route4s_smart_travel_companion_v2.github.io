"""
Place search and street-level legs (Phase 2).

  * search():  OneMap Search API (Singapore's official geocoder). ONEMAP_TOKEN is optional;
               it is sent only if set in .env.
  * route():   OSRM on OpenStreetMap data, one server per profile (foot, bicycle),
               started with docker compose (see README). URLs come from .env.
               If OSRM is not running, an estimate is returned and clearly marked
               source="estimate" so the app never presents a guess as a street route.
Results are cached in memory.
"""
import math
import os
import time

import httpx

ONEMAP_SEARCH = "https://www.onemap.gov.sg/api/common/elastic/search"
SPEED_KMH = {"foot": 4.8, "bike": 15.0}          # used only for estimates
DETOUR = {"foot": 1.3, "bike": 1.35}              # streets are longer than straight lines
_cache = {}


async def _fetch_json(url, params=None, headers=None, timeout=8):
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        return r.json()


def _cached(key, ttl):
    hit = _cache.get(key)
    return hit[1] if hit and time.time() - hit[0] < ttl else None


def km_between(lat1, lon1, lat2, lon2):
    r = math.radians
    h = math.sin(r(lat2 - lat1) / 2) ** 2 + math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin(r(lon2 - lon1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


async def search(q):
    q = q.strip()
    if len(q) < 2:
        return {"results": [], "source": "none"}
    key = ("search", q.lower())
    if (hit := _cached(key, 24 * 3600)) is not None:
        return hit
    headers = {"Authorization": os.getenv("ONEMAP_TOKEN")} if os.getenv("ONEMAP_TOKEN") else None
    data = await _fetch_json(ONEMAP_SEARCH, {"searchVal": q, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1}, headers)
    results = []
    for row in data.get("results", [])[:8]:
        try:
            results.append({
                "name": (row.get("SEARCHVAL") or row.get("BUILDING") or "").title(),
                "address": (row.get("ADDRESS") or "").title(),
                "lat": float(row["LATITUDE"]),
                "lon": float(row["LONGITUDE"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    out = {"results": results, "source": "onemap"}
    _cache[key] = (time.time(), out)
    return out


def estimate(mode, a, b):
    km = km_between(*a, *b) * DETOUR[mode]
    return {
        "mode": mode, "distance_m": round(km * 1000), "duration_s": round(km / SPEED_KMH[mode] * 3600),
        "geometry": [list(a), list(b)], "source": "estimate",
    }


async def route(mode, a, b):
    """a, b are (lat, lon). Returns distance, duration and a [lat, lon] line."""
    base = os.getenv("OSRM_FOOT_URL" if mode == "foot" else "OSRM_BIKE_URL")
    key = ("route", mode, round(a[0], 5), round(a[1], 5), round(b[0], 5), round(b[1], 5))
    if (hit := _cached(key, 6 * 3600)) is not None:
        return hit
    if not base:
        return {**estimate(mode, a, b), "note": "OSRM URL not set in .env"}
    profile = "foot" if mode == "foot" else "bicycle"
    url = f"{base.rstrip('/')}/route/v1/{profile}/{a[1]},{a[0]};{b[1]},{b[0]}"
    try:
        data = await _fetch_json(url, {"overview": "full", "geometries": "geojson"}, timeout=6)
        best = data["routes"][0]
        out = {
            "mode": mode, "distance_m": round(best["distance"]), "duration_s": round(best["duration"]),
            "geometry": [[lat, lon] for lon, lat in best["geometry"]["coordinates"]], "source": "osrm",
        }
    except Exception as e:  # OSRM down or no route: say so, give an estimate
        return {**estimate(mode, a, b), "note": f"OSRM unavailable: {type(e).__name__}"}
    _cache[key] = (time.time(), out)
    return out
