# Smart Commuter Companion — project context for Claude Code

Read this first. It carries over the decisions made while this project was built in a
chat session, so you don't have to re-derive them.

## What this is

Entry for the **LTA Smart Mobility Hackathon, Problem Statement 2 (Smart Commuter
Companion)**. A mobile-first web app that plans door-to-door commutes and reroutes around
disruptions. Judged on a real phone. `PS2_README.md` (the organisers' brief, not in this
repo) is the source of truth for data details.

**Persona: Arjun** — commutes Punggol → one-north, cycles to the LRT, flexible start within
about an hour, values comfort and predictability over raw speed, cares about crowding,
sheltered routes and whether he can bring his bike.

Mandatory capabilities from the brief, each capped at 3/5 if missing:
1. door-to-door route planning that reacts to live conditions,
2. OpenStreetMap as the base map,
3. visualisation that shows the affected portion and the alternatives.

## Hard rules

- **Never invent data.** Anything not from a real feed is labelled **Test data** or
  **simulated** in the UI. The brief caps scores for mocked data presented as live.
- **No credentials in the repo.** Keys live in `.env` (git-ignored). `/api/*` endpoints
  report only *whether* a key is set.
- **Don't break what works.** This app has many working features (MRT/LRT network, bus
  options, disruption rerouting, Apple Watch views, bus arrival board, tourist planner).
  Make surgical changes; keep existing behaviour unless asked.
- **Phone first.** Test at 390×844 or smaller: no sideways scrolling, touch targets ≥44 px,
  form fields ≥16 px text (or iOS zooms on focus).
- **State assumptions.** Every estimated number is listed in README "Timing assumptions".

## Layout

```
frontend/index.html   the whole app: one file, plain JS, no build step (~4k lines)
frontend/sw.js        service worker: app shell offline, API answers stamped with their age
frontend/vendor/      Leaflet + protomaps-leaflet, kept local so the app works offline
frontend/map/         singapore.pmtiles (OpenStreetMap via Protomaps), made by tools/get_map.py
backend/main.py       FastAPI: serves the app and /api/*
backend/linecodes.py  canonical line table: feeds disagree (STL vs SLRT, PTL vs PLRT, CEL/CGL)
backend/alerts.py     TrainServiceAlerts -> normalised segments, free bus, bridging bus
backend/live.py       bus arrivals, bike parking, weather
backend/planned.py    RoadWorks, RoadOpenings, PlannedBusRoutes, FacilitiesMaintenance -> one shape
backend/geo.py        OneMap search, OSRM walking/cycling legs (falls back to labelled estimates)
backend/datamall.py   DataMall client, key from .env, in-memory cache
test_data/            labelled replays in each feed's real shape
tests/                pytest; upstream APIs replaced by fakes
tools/                get_map.py, get_osm.py, fetch_bus_data.py, get_covered.py, check_live.py
```

## Commands

```bash
pip install -r backend/requirements.txt
python -m pytest -q                                   # 23 tests, all should pass
uvicorn backend.main:app --host 0.0.0.0 --port 8000   # app at http://localhost:8000
python tools/check_live.py                            # are the live feeds working?
python tools/get_map.py                               # offline OSM map (once)
python tools/fetch_bus_data.py --no-key --out frontend/busdata.json
docker compose up -d                                  # OSRM walking + cycling (optional)
```

Browser testing used Playwright (`pip install playwright && playwright install chromium`)
against `http://localhost:8000` at an iPhone viewport. There is no frontend test suite in the
repo; if you change `frontend/index.html`, drive it with Playwright and check the console for
errors before saying it works.

## How the frontend is organised

One IIFE in `index.html`. Key parts, in order:

- `STATIONS`, `LINES` — all MRT and LRT stations with real positions projected to map units
  (~35 units per km). `projLL`/`toLL` convert to and from latitude/longitude.
- `findRoute` / `stationRoute` — Dijkstra over the rail graph; `isBlocked` keeps closed
  stretches out of both.
- Bus module — simulated services, or real LTA routes if `busdata.json` is loaded
  (`BUSDATA`); arrival times are simulated unless a DataMall key is set.
- Breakdown module — `S.disruption` (MRT) and `S.lrtDisruption` (LRT) can both be active;
  `bridgeLeg` rebuilds a journey with a free bridging bus over the closed part.
- OSM map — one Leaflet instance reused across tabs; `mountOsm()` re-parents it after each
  render because the app re-renders by replacing `#app.innerHTML`.
- Trip planner — `computeOptions()` builds candidates, applies live conditions and ranks
  for Arjun; `planTrip()` is the UI wrapper and `planAndShow()` scrolls to the map after it;
  `morningCheck()` tries departures every 10 minutes across his window. `modesOf()` /
  `shownOptions()` back the All / Train / Bus / Cycle / Walk-only chips: cycling counts
  wherever it appears (cycling to the LRT is the journey), walking only when it is the
  whole trip, or the filter would match everything.
- `S` is the single state object; `render()` redraws the active tab; `tick()` runs the
  simulated trip every 120 ms.

## Status

Done: phone layout, OSM map, door-to-door planning with time ranges, live disruptions with
bridging-bus rerouting, crowding, rain, bus arrivals, bike parking, Arjun's routine and
morning check, live weather on screen (two-hour nowcast for both ends of the trip),
privacy panel, test-data replays, planned works (the "known in advance" half:
`/api/planned`, shown against the route and labelled "On your route" or "Named nearby"),
offline support (`frontend/sw.js`: shell cache-first, `/api/*` network-first with the fetch
time stamped so the UI can say "showing conditions saved at HH:MM"; the pmtiles map is
deliberately not cached), sheltered walkways (OpenStreetMap
`covered=yes` paths via `tools/get_covered.py` -> `frontend/covered.json`, drawn on the map
and measured per walking leg), watch navigation (page 2 of the watch is a second Leaflet
instance, `WMAP`/`mountWatchMap()`, re-parented after each `renderWatch()`; the old schematic
SVG stays as the fallback when Leaflet is missing).

Next:
1. **Accessibility pass** — contrast, text size, screen-reader labels, sunlight readability.
   Nothing claims to serve the accessibility persona until this is done.
2. **Deliverables** — `WRITEUP.md` is written (persona, architecture, assumptions and how each
   number was derived, limits). A demo script and a README check on a clean machine are not.
3. **Optional** — an LLM that turns alert free-text into structured advice with cached results
   and a rule-based fallback. LTA `CoveredLinkWay` would be the authoritative upgrade to the
   OpenStreetMap shelter data; it ships as a shapefile download, so it needs different tooling.

## Unverified, needs a real run

- Real DataMall responses: the crowd **forecast** shape is confirmed - a live `PCDForecast`
  answered with station rows keyed `['Interval', 'Station']`, which is what `/api/crowd`
  reads. The `FreeMRTShuttle` route text is still a guess: checking it needs a real
  disruption, and the feed reported `Status=1` with no affected segments.
  `tools/check_live.py` prints both.
- Cloud Run deploy is no longer unverified: `gcloud run deploy --source . --region
  asia-southeast1 --set-secrets LTA_ACCOUNT_KEY=lta-key:latest` was run on a real Mac and
  reached "has been deployed and is serving 100 percent of traffic", so the Dockerfile
  builds and the container starts under Cloud Run. Done against a Qwiklabs lab project,
  which is deleted when the lab ends - the steps are what carry over, not that URL.
  Still unbuilt in the sandbox itself: there is no Docker daemon here.
- OSRM and the Geofabrik download are no longer unverified: both were run on a real Mac, and
  the foot profile answered `/route/v1/foot/...` with `"code":"Ok"` and a real geometry. Two
  bugs in `tools/get_osm.py` were found doing it (a truncated download reported as success,
  and that broken file then being reused on every retry); both are fixed.
- Whether GitHub Pages serves the byte-range requests the `.pmtiles` map needs. The backend
  does (uvicorn answers 206), and the map renders locally from the committed 12.5 MB file
  (zoom 0-14); the Pages side is still unconfirmed.
