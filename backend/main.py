"""
Smart Commuter Companion - backend (Phase 1)
============================================

What this does now:
  * serves the web app in ../frontend
  * serves the offline OpenStreetMap map file (frontend/map/singapore.pmtiles)
    with HTTP range requests, which the map needs
  * GET /api/health reports whether the map file and the DataMall key are present

Data endpoints (added after the PS2 participant brief):
  * GET /api/alerts            TrainServiceAlerts, normalised (live, needs LTA_ACCOUNT_KEY)
  * GET /api/alerts?replay=X   the same, from a labelled test file in test_data/
  * GET /api/replays           list of available test replays
  * GET /api/crowd?line=NEL&kind=realtime|forecast   Station Crowd Density (PCDRealTime / PCDForecast)

Door-to-door routing (Phase 2):
  * GET /api/geocode?q=fusionopolis          OneMap place search
  * GET /api/route?mode=foot|bike&from=lat,lon&to=lat,lon   OSRM street leg (or a labelled estimate)

Live conditions (Phases 3-4):
  * GET /api/bus-arrival?stop=83139          LTA v3 BusArrival
  * GET /api/bike-parking?lat=..&lon=..      LTA BicycleParkingv2
  * GET /api/weather?lat=..&lon=..           data.gov.sg 2-hour forecast for the nearest area
  * GET /api/status                          which live sources are available
Every data endpoint also takes ?replay=<test_data file> and then marks its answer test_data=true.

Run from the project folder:
    uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
MAP_FILE = FRONTEND / "map" / "singapore.pmtiles"

# Secrets live in .env (never committed). See .env.example.
load_dotenv(ROOT / ".env")

app = FastAPI(title="Smart Commuter Companion", version="0.1.0")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "map_file": MAP_FILE.exists(),
        "map_file_mb": round(MAP_FILE.stat().st_size / 1e6, 1) if MAP_FILE.exists() else 0,
        "datamall_key_set": bool(os.getenv("LTA_ACCOUNT_KEY")),  # never return the key itself
        "replays": alerts.replay_names(),
        "osrm_foot_url_set": bool(os.getenv("OSRM_FOOT_URL")),
        "osrm_bike_url_set": bool(os.getenv("OSRM_BIKE_URL")),
    }


from . import alerts, datamall, geo, linecodes, live  # noqa: E402  (after load_dotenv)

CROWD = {"l": "low", "m": "moderate", "h": "high"}


@app.get("/api/replays")
def replays():
    return {"replays": alerts.replay_names(), "note": "Test data for demonstrating disruptions. Not live."}


@app.get("/api/alerts")
async def train_alerts(replay: str | None = Query(None, description="name of a test_data/tsa_*.json file")):
    if replay:
        try:
            return alerts.load_replay(replay)
        except FileNotFoundError:
            raise HTTPException(404, f"No replay called {replay!r}. See /api/replays.")
    try:
        data = await datamall.get("TrainServiceAlerts", ttl=60)
    except datamall.NoKey as e:
        return {"status": None, "disrupted": False, "segments": [], "messages": [], "source": "unavailable",
                "test_data": False, "error": str(e)}
    except Exception as e:  # network or API error: say so, don't pretend all is well
        raise HTTPException(502, f"TrainServiceAlerts unavailable: {e}")
    return alerts.parse(data, source="live")


@app.get("/api/crowd")
async def crowd(line: str = Query(..., description="canonical line, e.g. NEL, CCL, PGLRT"),
                kind: str = Query("realtime", pattern="^(realtime|forecast)$"),
                replay: str | None = Query(None, description="test_data/pcd_*.json")):
    canon = line.upper()
    if canon not in linecodes.CANON:
        raise HTTPException(400, f"Unknown line {line!r}. Use one of {sorted(linecodes.CANON)}")
    endpoint = "PCDRealTime" if kind == "realtime" else "PCDForecast"
    ttl = 600 if kind == "realtime" else 6 * 3600
    rows = []
    replay_data = None
    if replay:
        try:
            replay_data = live.replay(replay, "pcd_")[kind]
        except (FileNotFoundError, KeyError):
            raise HTTPException(404, f"No crowd replay called {replay!r}")
    try:
        for code in linecodes.pcd_codes(canon):
            data = replay_data.get(code, {"value": []}) if replay_data is not None else await datamall.get(endpoint, {"TrainLine": code}, ttl=ttl)
            for item in data.get("value", []):
                # Real-time rows are flat; forecast rows nest per-station intervals. Keep both readable.
                for r in item.get("Stations", [item]) if isinstance(item, dict) else []:
                    # forecast: each station lists 30-minute intervals; real-time: one row per station
                    for slot in (r.get("Interval") if isinstance(r.get("Interval"), list) else [r]):
                        level = str(slot.get("CrowdLevel", "NA")).lower()
                        rows.append({
                            "station_code": r.get("Station"),
                            "station": linecodes.station_name(str(r.get("Station", ""))),
                            "level": CROWD.get(level, "no data"),
                            "start": slot.get("StartTime") or slot.get("Start"),
                            "end": slot.get("EndTime"),
                            "feed_line": code,
                        })
    except datamall.NoKey as e:
        return {"line": canon, "kind": kind, "rows": [], "source": "unavailable", "error": str(e)}
    except Exception as e:
        raise HTTPException(502, f"{endpoint} unavailable: {e}")
    return {"line": canon, "kind": kind, "rows": rows, "source": f"replay:{replay}" if replay else "live",
            "test_data": bool(replay)}


def _latlon(text, name):
    try:
        lat, lon = (float(v) for v in text.split(","))
    except ValueError:
        raise HTTPException(400, f"{name} must be 'lat,lon'")
    if not (1.1 <= lat <= 1.5 and 103.5 <= lon <= 104.2):
        raise HTTPException(400, f"{name} is outside Singapore")
    return lat, lon


@app.get("/api/geocode")
async def geocode(q: str = Query(..., min_length=1, max_length=80)):
    try:
        return await geo.search(q)
    except Exception as e:
        return {"results": [], "source": "unavailable", "error": f"OneMap search failed: {type(e).__name__}"}


@app.get("/api/route")
async def street_route(mode: str = Query(..., pattern="^(foot|bike)$"),
                       from_: str = Query(..., alias="from"), to: str = Query(...)):
    return await geo.route(mode, _latlon(from_, "from"), _latlon(to, "to"))


async def _live(call, label):
    try:
        return await call
    except FileNotFoundError as e:
        raise HTTPException(404, f"No replay called {e}")
    except datamall.NoKey as e:
        return {"source": "unavailable", "test_data": False, "error": str(e)}
    except Exception as e:
        raise HTTPException(502, f"{label} unavailable: {type(e).__name__}")


@app.get("/api/bus-arrival")
async def bus_arrival(stop: str = Query("", pattern=r"^\d{0,5}$"), replay: str | None = None):
    if not stop and not replay:
        raise HTTPException(400, "stop is required")
    return await _live(live.bus_arrival(stop, replay), "BusArrival")


@app.get("/api/bike-parking")
async def bike_parking(lat: float = Query(..., ge=1.1, le=1.5), lon: float = Query(..., ge=103.5, le=104.2),
                       dist: float = Query(0.3, gt=0, le=2), replay: str | None = None):
    return await _live(live.bike_parking(lat, lon, dist, replay), "BicycleParkingv2")


@app.get("/api/weather")
async def weather(lat: float = Query(..., ge=1.1, le=1.5), lon: float = Query(..., ge=103.5, le=104.2),
                  replay: str | None = None):
    return await _live(live.weather(lat, lon, replay), "Weather")


@app.get("/api/status")
def status():
    return {
        "datamall": datamall.has_key(),
        "weather": True,  # data.gov.sg works without a key
        "osrm": bool(os.getenv("OSRM_FOOT_URL") and os.getenv("OSRM_BIKE_URL")),
        "replays": {"alerts": alerts.replay_names(), "crowd": live.replays("pcd_"), "weather": live.replays("weather_"),
                    "bike_parking": live.replays("bikeparking_"), "bus_arrival": live.replays("busarrival_")},
    }


# Keep this last: everything that isn't /api/... is the web app.
# StaticFiles answers Range requests, so the PMTiles map works.
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
