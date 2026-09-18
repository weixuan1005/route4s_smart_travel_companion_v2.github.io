"""
Live conditions for the app (Phases 3-4): bus arrivals, bike parking, weather.
Every result says where it came from ("live", "replay:<file>" or "unavailable").

  * bus_arrival():  LTA DataMall v3/BusArrival  (Load SEA/SDA/LSD, Type SD/DD/BD, Feature WAB)
  * bike_parking(): LTA DataMall BicycleParkingv2 (Lat, Long, Dist in km)
  * weather():      data.gov.sg 2-hour forecast (no key needed; DATAGOV_API_KEY raises the rate limit)
"""
import json
import math
import os
import time
from pathlib import Path

import httpx

from . import datamall

TEST_DATA = Path(__file__).resolve().parent.parent / "test_data"
WEATHER_URL = "https://api-open.data.gov.sg/v2/real-time/api/two-hr-forecast"
RAIN_WORDS = ("rain", "shower", "thunder", "drizzle")
_cache = {}


def replay(name, prefix):
    """Load test_data/<name>.json, only for known file prefixes."""
    path = TEST_DATA / f"{name}.json"
    if not name.startswith(prefix) or path.parent != TEST_DATA or not path.exists():
        raise FileNotFoundError(name)
    return json.loads(path.read_text(encoding="utf-8"))


def replays(prefix):
    return sorted(p.stem for p in TEST_DATA.glob(f"{prefix}*.json"))


# ---------- bus arrivals ----------
def parse_bus_arrival(data, source):
    services = []
    for s in data.get("Services", []):
        nxt = []
        for key in ("NextBus", "NextBus2", "NextBus3"):
            b = s.get(key) or {}
            if not b.get("EstimatedArrival"):
                continue
            nxt.append({
                "eta": b["EstimatedArrival"],
                "load": b.get("Load") or None,            # SEA seats, SDA standing, LSD limited standing
                "type": b.get("Type") or None,            # SD single deck, DD double deck, BD bendy
                "wheelchair": b.get("Feature") == "WAB",
                "monitored": str(b.get("Monitored", "")) == "1",
            })
        services.append({"service": s.get("ServiceNo"), "operator": s.get("Operator"), "next": nxt})
    return {"stop": data.get("BusStopCode"), "services": services, "source": source,
            "test_data": source.startswith("replay"), "fetched_at": int(time.time())}


async def bus_arrival(stop, replay_name=None):
    if replay_name:
        return parse_bus_arrival(replay(replay_name, "busarrival_"), f"replay:{replay_name}")
    data = await datamall.get("v3/BusArrival", {"BusStopCode": stop}, ttl=20)
    return parse_bus_arrival(data, "live")


# ---------- bike parking ----------
def parse_bike_parking(data, source):
    rows = []
    for r in data.get("value", []):
        try:
            rows.append({
                "name": r.get("Description", "").title(), "lat": float(r["Latitude"]), "lon": float(r["Longitude"]),
                "racks": int(r.get("RackCount") or 0), "rack_type": r.get("RackType", ""),
                "sheltered": str(r.get("ShelterIndicator", "")).upper() == "Y",
            })
        except (KeyError, TypeError, ValueError):
            continue
    return {"parking": rows, "source": source, "test_data": source.startswith("replay")}


async def bike_parking(lat, lon, dist_km=0.3, replay_name=None):
    if replay_name:
        return parse_bike_parking(replay(replay_name, "bikeparking_"), f"replay:{replay_name}")
    data = await datamall.get("BicycleParkingv2", {"Lat": lat, "Long": lon, "Dist": dist_km}, ttl=24 * 3600)
    return parse_bike_parking(data, "live")


# ---------- weather ----------
def parse_weather(data, lat, lon, source):
    body = data.get("data", data)                         # v2 wraps the payload in "data"
    areas = body.get("area_metadata", [])
    items = body.get("items", [])
    if not areas or not items:
        raise ValueError("unexpected weather response")
    def d2(a):
        loc = a.get("label_location", {})
        return (loc.get("latitude", 0) - lat) ** 2 + (math.cos(math.radians(lat)) * (loc.get("longitude", 0) - lon)) ** 2
    area = min(areas, key=d2)["name"]
    item = items[-1]
    text = next((f.get("forecast", "") for f in item.get("forecasts", []) if f.get("area") == area), "")
    if isinstance(text, dict):                            # some versions nest the text
        text = text.get("text", "")
    period = item.get("valid_period", {})
    return {"area": area, "forecast": text, "rain": any(w in text.lower() for w in RAIN_WORDS),
            "valid_from": period.get("start"), "valid_to": period.get("end"), "valid_text": period.get("text"),
            "updated": item.get("update_timestamp") or item.get("timestamp"),
            "source": source, "test_data": source.startswith("replay")}


async def weather(lat, lon, replay_name=None):
    if replay_name:
        return parse_weather(replay(replay_name, "weather_"), lat, lon, f"replay:{replay_name}")
    hit = _cache.get("weather")
    if not hit or time.time() - hit[0] > 300:
        headers = {"x-api-key": os.getenv("DATAGOV_API_KEY")} if os.getenv("DATAGOV_API_KEY") else None
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(WEATHER_URL, headers=headers)
            r.raise_for_status()
            hit = (time.time(), r.json())
        _cache["weather"] = hit
    return parse_weather(hit[1], lat, lon, "live")
