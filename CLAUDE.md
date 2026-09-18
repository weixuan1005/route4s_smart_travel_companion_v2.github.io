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
tools/                get_map.py, get_osm.py, fetch_bus_data.py, get_covered.py, check_live.py,
                      check_fares.py
```

## Commands

```bash
pip install -r backend/requirements.txt
python3 -m pytest -q                                   # 23 tests, all should pass
uvicorn backend.main:app --host 0.0.0.0 --port 8000   # app at http://localhost:8000
python3 tools/check_live.py                            # are the live feeds working?
python3 tools/get_map.py                               # offline OSM map (once)
python3 tools/fetch_bus_data.py --no-key --out frontend/busdata.json
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
  simulated trip every 120 ms. `S.clockMin` is the device clock between trips (a 1 s
  interval keeps it moving, since `tick()` returns early when idle) and the simulation's
  own clock during one, because every ETA on screen is derived from it. `fmt()` wraps to
  00:00-23:59, so a trip running past midnight reads 01:00 rather than 25:00.
- `samePlace()` is 50 m; `computeOptions()` returns no options when start and destination
  are the same, and the trip panel says so instead of offering a nought-minute walk.
- Service hours: `svcRunsAt()` for buses (real, from DataMall `BusRoutes` first/last, carried
  in `busdata.json` `services[key][4]`; absent from the no-key BusRouter SG build) and
  `railRunsAt()` for trains. There is no train timetable to have: LTA publishes none through
  DataMall and last trains vary by line AND direction (23:15-00:15), so `RAIL_HOURS` is an
  envelope (05:00-00:15) outside which nothing runs anywhere, and `RAIL_LAST_BAND` marks the
  window where `op.lateTrain` puts a **Check last train** tag on rail options instead of
  guessing. `frontend/trainhours.json` overrides both per line; it ships empty, and an empty
  `lines: {}` must not count as a table (`{}` is truthy - that bug hid the caution once).
  `computeOptions()` drops what has stopped; unknown hours never hide anything. It asks
  `appNowMin()` (the clock on screen, `S.clockMin`) rather than `nowMin()` (the device), or a
  trip simulated into the small hours gets planned against the real afternoon. Every rail leg
  is checked at its own boarding time via `railBoardings()`, not just the first: a change at
  00:40 is no good if that line's last train went at 23:50. When that empties the list,
  `PLAN_NOTE` says which of the two happened - "gone" (nothing ran at departure) or
  "connection" (you could start but not finish) - and `PLAN_AT` records the minute planned
  for, so the message does not drift as the clock moves.
  `withinHours()` handles windows ending after midnight, including DataMall's 24:xx times.
  Never fill trainhours.json from a GTFS feed without checking its provenance: the public
  Singapore ones document their MRT schedules as synthetic.
- `planTrip()` wraps `computeOptions()` in try/catch: anything thrown used to leave the
  screen on "Finding routes..." for ever, because `T.loading` was only cleared on the happy
  path. A visible error the user can retry beats a spinner that never resolves.
- `railKm()` measures rail only. A bus leg's `segments[].stations` are bus stop names, not
  entries in `STATIONS`, so `st()` read `[0]` off undefined and threw the whole plan away.
  It now skips bus lines and any name that is not a station, and `journeyKm()` does not ask
  it about a bus option at all. Same guard inside `railBoardings()`.
- Fares: `fareFor(km)` is the only place a price is decided, and it takes the whole
  journey's ridden distance (`journeyKm()`), because Singapore charges one distance fare per
  journey with transfers included - it used to be `1.09 + stops*0.1` in four places. Real
  bands live in `frontend/fares.json`, shipped with `bands: []`; while it is empty the app
  falls back to `FARE_EST` and tags every option **Fare estimated**. Never put guessed band
  values in that file.
- `endTrip()` stops navigation part-way: clears the timer, `freshTrip()`s the run and returns
  to the tab the trip came from (`S.itinerary.fromTrip` -> trip planner, else itinerary). The
  itinerary is deliberately kept - plans change, and losing the plan for it would be
  punishing. Guarded by `S.confirmEnd`, which a tab change clears so a forgotten half-asked
  confirmation cannot end a trip by accident. The clock returns to real time on its own,
  because `updateLive()` follows the device whenever no trip is active.
- One clock, everywhere. `dayStart()` (now, rounded up to five minutes) anchors the tourist
  itinerary, which used to start at a hardcoded 10:00 while the clock beside it read the real
  time - so the watch would say "Leave by 11:35" at 14:13. `startTrip()` takes its clock from
  `S.tripStartMin` (commute planner) or `S.itinerary.startTime` (tourist planner), so a
  simulated trip runs on the clock its plan was built for. Times are absolute minutes
  throughout and only wrap at display, so a plan crossing midnight stays ordered.

## Status

Done: phone layout, OSM map, door-to-door planning with time ranges, live disruptions with
bridging-bus rerouting, crowding, rain, bus arrivals, bike parking, Arjun's routine and
morning check, ending a trip part-way, live weather on screen (two-hour nowcast for both ends of the trip),
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
