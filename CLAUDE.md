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
frontend/vendor/      Leaflet + protomaps-leaflet, kept local so the app works offline
frontend/map/         singapore.pmtiles (OpenStreetMap via Protomaps), made by tools/get_map.py
backend/main.py       FastAPI: serves the app and /api/*
backend/linecodes.py  canonical line table: feeds disagree (STL vs SLRT, PTL vs PLRT, CEL/CGL)
backend/alerts.py     TrainServiceAlerts -> normalised segments, free bus, bridging bus
backend/live.py       bus arrivals, bike parking, weather
backend/geo.py        OneMap search, OSRM walking/cycling legs (falls back to labelled estimates)
backend/datamall.py   DataMall client, key from .env, in-memory cache
test_data/            labelled replays in each feed's real shape
tests/                pytest; upstream APIs replaced by fakes
tools/                get_map.py, get_osm.py, fetch_bus_data.py, check_live.py
```

## Commands

```bash
pip install -r backend/requirements.txt
python -m pytest -q                                   # 17 tests, all should pass
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
  for Arjun; `planTrip()` is the UI wrapper; `morningCheck()` tries departures every
  10 minutes across his window.
- `S` is the single state object; `render()` redraws the active tab; `tick()` runs the
  simulated trip every 120 ms.

## Status

Done: phone layout, OSM map, door-to-door planning with time ranges, live disruptions with
bridging-bus rerouting, crowding, rain, bus arrivals, bike parking, Arjun's routine and
morning check, privacy panel, test-data replays.

Next (was Phase 5 and 6):
1. **Offline and underground** — service worker for the app shell, map and current journey;
   "Last updated HH:MM · no signal".
2. **Accessibility pass** — contrast, text size, screen-reader labels, sunlight readability.
3. **Deliverables** — `WRITEUP.md` (persona, architecture, assumptions, limits, how numbers
   were measured), demo script, and a README check on a clean machine.
4. **Optional** — sheltered walkways (LTA CoveredLinkWay), planned works
   (`PlannedBusRoutes`, `RoadWorks`), and an LLM that turns alert free-text into structured
   advice with cached results and a rule-based fallback.

## Unverified, needs a real run

- Real DataMall responses: the crowd **forecast** shape and the `FreeMRTShuttle` route text
  are my best understanding, not copied from LTA samples. `tools/check_live.py` prints both.
- OSRM Docker build, Geofabrik download, Cloud Run deploy: never run in the build sandbox.
- Whether GitHub Pages serves the byte-range requests the `.pmtiles` map needs.
