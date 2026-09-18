# Smart Commuter Companion

LTA Smart Mobility Hackathon, Problem Statement 2. A mobile-first web app that plans
door-to-door commutes and reroutes around disruptions.

**Persona:** Arjun, a multi-modal commuter from Punggol to one-north who cycles to the LRT
and cares about crowding, sheltered routes and bringing his bike.

> Status: **Phase 4** — phone-first layout, OpenStreetMap map, door-to-door trip planning,
> live conditions (disruptions, crowding, rain, bus arrivals, bike parking) and Arjun's
> morning check with alerts. Offline caching, accessibility review and the write-up come next.
> Anything marked **Test data** in the app is injected for demonstration, not live.

## Run it (clean machine)

Requirements: **Python 3.10 or newer** and internet access. Steps 1-5 are the whole path
from a fresh clone to the app open in a browser. Everything after them is optional.

```bash
# 1. Get the code
git clone <your-repo-url> route4us
cd route4us

# 2. Check your Python before anything else
python3 --version                  # must be 3.10 or newer
```

macOS ships 3.9, which **cannot** run this code: `backend/main.py` uses `str | None` in
FastAPI signatures, so on 3.9 the server stops at import with
`TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'`. Install a current
Python first, then use `python3.12` wherever `python3` appears below:

```bash
brew install python@3.12           # macOS
```

```bash
# 3. Virtual environment and dependencies
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python --version                   # confirm 3.10+ INSIDE the venv before going on
pip install -r backend/requirements.txt

# 4. Settings file
cp .env.example .env               # Windows: copy .env.example .env
```

Put your LTA DataMall AccountKey in `.env` as `LTA_ACCOUNT_KEY=...`. Edit the file in an
editor rather than appending with `echo`, which would leave the key in your shell history.
The key is optional: without it the app runs on the labelled replays in `test_data/`.
Check that the key reaches LTA before starting the server — it prints OK or the exact error
per feed, and never prints the key itself:

```bash
python tools/check_live.py
```

```bash
# 5. Start the server
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Now open **<http://localhost:8000>**.

Leave the server running, and use that address rather than opening `frontend/index.html`
directly: the same server answers both the app and `/api/*`, and the app calls the API with
a *relative* URL. Opened as a `file://` path, or from static hosting such as GitHub Pages,
you get the app but no live data at all.

To see what the server picked up:

```bash
curl -s http://localhost:8000/api/health    # datamall_key_set: true once your key is in .env
```

**Settings -> Live data** in the app shows the same thing. With a key set, the
**Use test data** switch becomes available; turn it off to use live feeds. Without a key it
stays on and says why.

### Optional extras

None of these are needed to open the app. Each replaces a labelled fallback with real data.
Restart the server after the first two so it serves the new files.

```bash
python tools/get_map.py                                             # offline OpenStreetMap basemap -> frontend/map/singapore.pmtiles
python tools/fetch_bus_data.py --no-key --out frontend/busdata.json  # real LTA bus stops and routes
python tools/get_osm.py                                             # OSM extract for OSRM (add --clip if osmium is installed)
docker compose up -d                                                # OSRM walking + cycling; the first start builds routing files and takes several minutes
curl "http://localhost:5001/route/v1/foot/103.8965,1.4102;103.9024,1.4053"   # should answer "code":"Ok"
```

Without the map file the map says so and draws lines and stations only. Without OSRM,
walking and cycling legs are straight-line estimates and the app labels them
**Street legs estimated**.

One thing to watch: `/api/health` reports `osrm_foot_url_set: true`, and Settings shows
street routing as "Configured", as soon as `.env` exists - `.env.example` already carries
both OSRM URLs. That reflects the URLs being set, not OSRM answering. The real check is a
street leg:

```bash
curl -s "http://localhost:8000/api/route?mode=bike&from=1.4102,103.8965&to=1.4053,103.9024"
```

`"source": "osrm"` is real street routing on OpenStreetMap; `"source": "estimate"` means
OSRM is not reachable and the app is saying so rather than guessing quietly.

### Check the data layer

```bash
pip install pytest
python -m pytest -q          # line-code mapping, TrainServiceAlerts parser, API endpoints
```

| Endpoint | What it returns |
|---|---|
| `/api/alerts` | Live TrainServiceAlerts, normalised (needs `LTA_ACCOUNT_KEY` in `.env`) |
| `/api/alerts?replay=tsa_nel_punggol_serangoon` | The same shape from a **test data** replay, flagged `"test_data": true` |
| `/api/replays` | Available test replays |
| `/api/crowd?line=NEL&kind=realtime` | Station Crowd Density (`PCDRealTime`), or `kind=forecast` for `PCDForecast` |
| `/api/geocode?q=fusionopolis` | Place search through OneMap |
| `/api/route?mode=bike&from=lat,lon&to=lat,lon` | Street leg from OSRM on OpenStreetMap, or an estimate marked `"source": "estimate"` |

Without a key, live endpoints answer `"source": "unavailable"` rather than inventing data.

### Open it on your phone

- **Same Wi-Fi, quick check:** find your computer's address on the network and open it on
  the phone:

  ```bash
  ipconfig getifaddr en0 || ipconfig getifaddr en1   # macOS, e.g. 192.168.1.42
  ```

  Then browse to `http://192.168.1.42:8000`. Enough to test the layout and live data.
  macOS asks to allow incoming connections the first time; allow it or the phone cannot
  reach the server.
- **For judging:** use HTTPS. Offline caching, location and notifications (later phases)
  only work over HTTPS. Deploy the backend to an HTTPS host (for example Google Cloud Run),
  or expose it through an HTTPS tunnel.

## Put the backend online (HTTPS, for phones and judges)

The `Dockerfile` runs the backend and the app together. On Google Cloud Run:

```bash
gcloud run deploy smart-commuter --source . --region asia-southeast1 --allow-unauthenticated \
  --set-env-vars LTA_ACCOUNT_KEY=YOUR_KEY
```

Cloud Run prints an `https://…run.app` address; open it on a phone. For a team project, store
the key in Secret Manager and use `--set-secrets LTA_ACCOUNT_KEY=lta-key:latest` instead.
OSRM is not part of this container; without it, walking and cycling legs are estimates
(labelled). Run the OSRM containers on a VM and set `OSRM_FOOT_URL` / `OSRM_BIKE_URL` if needed.

## Project layout

```
backend/             FastAPI server: serves the app, the map file and /api/*
frontend/index.html  the app (single file)
frontend/vendor/     Leaflet 1.9.4 and protomaps-leaflet 5.1.0 (kept locally so the app works offline)
frontend/map/        singapore.pmtiles, created by tools/get_map.py
backend/linecodes.py one canonical line table (TrainServiceAlerts, crowd feeds and app codes differ)
backend/alerts.py    TrainServiceAlerts parser (AffectedSegments, FreePublicBus, FreeMRTShuttle, Message)
backend/datamall.py  DataMall client with caching; key from .env
backend/data/        station codes (e.g. NE17 -> Punggol)
test_data/           labelled replays in the TrainServiceAlerts shape
tests/               automated tests
backend/geo.py       OneMap place search and OSRM street legs
docker-compose.yml   two OSRM servers (walking, cycling) on OpenStreetMap data
Dockerfile           backend + app in one container (e.g. Cloud Run)
backend/live.py      bus arrivals, bike parking, weather
tools/get_osm.py     downloads the OpenStreetMap extract for OSRM
tools/check_live.py  asks every live source for a sample and reports OK or the error
tools/get_map.py     cuts Singapore out of the Protomaps OpenStreetMap build
tools/fetch_bus_data.py  bus stops and routes (LTA DataMall key, or --no-key)
.env.example         copy to .env for secrets; .env is never committed
```

## Live data: what needs a key

| Source | Key | What the app does with it |
|---|---|---|
| LTA DataMall `TrainServiceAlerts` | `LTA_ACCOUNT_KEY` | Disruption banner, rerouting, free bus and bridging bus details |
| LTA DataMall `PCDRealTime`, `PCDForecast` | `LTA_ACCOUNT_KEY` | Platform crowding now and in 30-minute slots; ranking and the morning check |
| LTA DataMall `v3/BusArrival` | `LTA_ACCOUNT_KEY` | Real arrival times on the bus arrivals screen (with real bus routes loaded) |
| LTA DataMall `BicycleParkingv2` | `LTA_ACCOUNT_KEY` | Bike racks at the station Arjun cycles to |
| data.gov.sg 2-hour forecast | none (`DATAGOV_API_KEY` optional) | Rain on cycling legs |
| OneMap search | none | Address search |
| OSRM (your Docker) | none | Walking and cycling legs on OpenStreetMap |

Check every source in one go (after putting the key in `.env`):

```bash
python tools/check_live.py
```

**Settings → Live data** shows what is connected. Without a DataMall key the app uses the
labelled replays in `test_data/` and says **Test data** wherever they appear. With a key you
can still switch to test data there, for a repeatable demo.

### Test data (demo panel → 🧪 Demo)

| Button / file | Scenario |
|---|---|
| Replay: NEL down (`tsa_nel_punggol_serangoon`) | No trains Serangoon–Punggol, free buses and bridging bus |
| Replay: Punggol LRT down (`tsa_ptl_west_loop`) | Punggol LRT West Loop partly closed, free buses only |
| Stop replay | Service resumes |
| Run morning check | Arjun's 08:00–09:00 check |
| `pcd_arjun_morning` | Busy platforms at Punggol and Serangoon 07:30–08:30 |
| `weather_punggol_showers` | Showers over Punggol and Sengkang 07:30–09:30 |
| `bikeparking_sumang` | 40 sheltered racks at Sumang LRT |

## Using the app (Arjun's journey)

1. **Trip** (opens first): From is Home (near Sumang LRT), To is Work (Fusionopolis, one-north).
   Search any address, place or station, or use **📍 My location** (needs HTTPS).
2. Choose **Leave now**, **Leave at** or **Arrive by**, and whether Arjun brings his bike
   and whether it folds.
3. **Find routes** lists options with a time range, the arrival window, changes and tags
   such as **Best for Arjun** and **Fastest**. The map shows the chosen route in colour
   and the others in grey.
4. **Start this trip** hands over to **Navigate** with turn-by-turn steps on phone and watch.
5. **Today's conditions** lists disruptions, rain and busy platforms. Each option shows its
   reasons ("Busy platform at Punggol around 08:13 (High, forecast)"), and when conditions
   change the ranking the app says what it was ranked above and why.
6. During a disruption the planner avoids the closed stretch and, when the feed lists a free
   bridging bus, offers the usual route with the bridging bus in between.
7. **Morning check** (top of Trip) tries departures every 10 minutes in Arjun's window and
   either confirms the usual time or suggests another (e.g. "Leave at 08:50 instead of 08:00")
   with reasons. **My routine** sets the days, the window, the alert threshold and phone
   notifications. The check runs by itself 45 minutes before the window while the app is open.

Notifications are shown while the app is open (or in a background tab). Alerts when the app
is fully closed would need Web Push with a push server, which is not built.

The home and work locations are a demo profile for the persona: public places, not a real
person's address. Nothing about trips is sent anywhere except the start and end points
needed for place search and street routing on your own backend.

## Timing assumptions (trip planner)

| Part | Estimate | Range shown |
|---|---|---|
| Walking | OSRM foot profile; estimate: 4.8 km/h over 1.3 × straight-line distance | ±10% |
| Cycling | OSRM bicycle profile; estimate: 15 km/h over 1.35 × straight-line distance | ±15% |
| Bike at the station | 3 min to park, or 2 min to fold | included |
| Train ride | MRT 1.35 min/km + 0.6 min per stop; LRT 2.4 min/km + 0.5 min per stop | −5% to +10% |
| Waiting for a train | 3 min | 1–5 min |
| Changing lines | 4 min | 3–6 min |
| Bus | route from bus data; wait from (simulated) arrival times; ride about 19 km/h plus stops | wait up to the next bus, ride −15% to +25% |

Options are ranked for Arjun by: middle of the time range + 5 min per change + half the range
width + 4 min for buses, plus today's conditions: +12 for cycling into rain at the start,
+8 at the end, +6 for each High-crowd boarding or change station, +2 for Moderate.
The morning check adds 0.15 per minute of later departure, so it only moves Arjun later
when that clearly helps. So a slightly slower trip with fewer changes and a narrower range can
rank first. These are stated assumptions, not measured values.

## Map and attribution

- Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL,
  packaged by [Protomaps](https://protomaps.com). The app shows this credit on every map.
- Tiles come from our own server (`frontend/map/singapore.pmtiles`), so the app does not
  load the public OpenStreetMap tile servers.
- If the map file is missing, the app still shows MRT/LRT lines and stations and says how
  to install the file. **Line diagram** switches back to the schematic view at any time.

## Data sources

| Data | Source | Used for |
|---|---|---|
| Map | OpenStreetMap via Protomaps | Base map |
| MRT/LRT stations | cheeaun/sgraildata (OpenStreetMap-based) | Network, routing |
| Bus stops and routes | LTA DataMall, or LTA data via BusRouter SG (`--no-key`) | Bus options |
| Train disruptions | LTA DataMall `TrainServiceAlerts` (live) or `test_data/` replays (labelled) | Alerts, rerouting |
| Station crowding | LTA DataMall `PCDRealTime`, `PCDForecast` | Crowd levels, departure advice |
| Station codes | cheeaun/sgraildata (OpenStreetMap-based) | Matching feed codes to stations |
| In-app delays, crowding and bus arrival times | **Test data** until the app is wired to the endpoints above | Demo only |

## Secrets

The LTA DataMall AccountKey goes in `.env` only. `.gitignore` excludes `.env`, and
`/api/health` reports only whether a key is set, never the key itself.
