# Smart Commuter Companion — write-up

LTA Smart Mobility Hackathon, Problem Statement 2. This covers the persona, the
architecture, where every number comes from, and what the app cannot do. Anything below that
is an estimate rather than a measurement says so.

---

## 1. Persona: Arjun

Punggol to one-north. Cycles to the LRT, sometimes buses the whole way, start time flexible
within about an hour. He optimises for comfort and predictability over speed, and will leave
twenty minutes later to avoid a crush.

What that means concretely, and what we built because of it:

| Arjun cares about | What the app does |
|---|---|
| Crowding, not just delay | Station Crowd Density drives the ranking, not only the banner: a High boarding or interchange station costs an option 6 points, Moderate 2 |
| Leaving later to travel better | The morning check tries a departure every 10 minutes across his window and recommends one, with a small penalty per minute of delay so it only moves him when that clearly helps |
| Staying dry | Rain on a cycling leg is a ranking penalty, and walking legs report how much of the route runs under covered walkways |
| Bringing his bike | Folding versus not changes what is offered — a non-folding bike rules out the bus options, and the app says so rather than silently dropping them |
| Knowing before he leaves | Planned works, road openings, bus route changes and lift maintenance are shown against his route before departure, not after |

We did not build for Rachel or Mdm Lim. Some of the work helps them — the covered-walkway
data and the lift-maintenance feed are Mdm Lim's needs — but the ranking, the defaults and
the flexible-departure logic are Arjun's, and we would not claim the app serves her well
without an accessibility pass we have not done.

---

## 2. Architecture

```
  phone browser
        │
        │  one origin: the backend serves both the app and the API,
        │  so the frontend calls /api/* with a relative URL and there is no CORS
        ▼
  FastAPI (backend/main.py)
        ├── alerts.py    TrainServiceAlerts  → normalised segments, free bus, bridging bus
        ├── planned.py   RoadWorks, RoadOpenings, PlannedBusRoutes, FacilitiesMaintenance
        ├── live.py      v3/BusArrival, BicycleParkingv2, data.gov.sg 2-hour forecast
        ├── geo.py       OneMap search, OSRM foot/bicycle legs
        ├── linecodes.py one canonical line table
        └── datamall.py  DataMall client, key from .env, in-memory cache
        │
        ▼
  frontend/index.html   one file, plain JS, no build step
  frontend/sw.js        offline shell, API answers stamped with their age
  frontend/map/         singapore.pmtiles — OpenStreetMap via Protomaps
```

**Why one file and no build step.** A judge follows the README on a clean machine. Every
build step is a way for that to fail. The whole app is one HTML file with the map libraries
vendored next to it, so it runs from any static host, and the backend adds the live data.

**Why the backend exists at all.** The DataMall key must never reach the browser, and OneMap
and OSRM need a server anyway. The backend holds the key, caches upstream responses and
reports only *whether* a key is set, never its value.

**Line codes.** The same line has different codes in different feeds — `STL` vs `SLRT`,
`PTL` vs `PLRT`, `CCL` folding in `CEL`. `backend/linecodes.py` is the one canonical table
everything maps through; joining feeds without it silently loses stations.

### Data sources

| Source | Used for | Key |
|---|---|---|
| DataMall `TrainServiceAlerts` | Disruption, free bus, bridging bus | Yes |
| DataMall `PCDRealTime` / `PCDForecast` | Crowding now and in 30-minute slots | Yes |
| DataMall `v3/BusArrival` | Arrival times, bus load, deck type | Yes |
| DataMall `BicycleParkingv2` | Racks, and whether they are sheltered | Yes |
| DataMall `RoadWorks`, `RoadOpenings`, `PlannedBusRoutes`, `v2/FacilitiesMaintenance` | Planned events | Yes |
| DataMall `BusRoutes` / `BusStops` / `BusServices` | Real bus network | Yes, or BusRouter SG without one |
| data.gov.sg 2-hour forecast | Rain on cycling legs | No |
| OneMap | Address search | No |
| OpenStreetMap via Protomaps | Base map | No |
| OpenStreetMap via Overpass | Covered walkways | No |
| OSRM on an OSM extract | Walking and cycling legs | No |

OpenStreetMap data is ODbL and the credit is shown on every map. Tiles are served from our
own bundled extract, never from `tile.openstreetmap.org`. Overpass is queried once by
`tools/get_covered.py` into a file, not in a loop.

---

## 3. Assumptions, and where each number came from

**None of these are measured.** They are stated estimates, chosen to be defensible and
visible rather than precise, and they are in the README as well as here.

| Quantity | Value | Where it came from |
|---|---|---|
| Walking speed | 4.8 km/h | Ordinary adult walking pace; used only when OSRM is unavailable |
| Walking distance | 1.3 × straight line | Allowance for streets not being straight |
| Cycling speed | 15 km/h | Unhurried cycling on park connectors, not sport |
| Cycling distance | 1.35 × straight line | As above, slightly worse because cycle routes detour more |
| Park or fold the bike | 3 min / 2 min | Estimate |
| MRT ride | 1.35 min/km + 0.6 min per stop | Fitted by hand to published end-to-end times |
| LRT ride | 2.4 min/km + 0.5 min per stop | As above; the LRT is slower per km |
| Waiting for a train | 3 min, shown as 1–5 | Peak headway assumption |
| Changing lines | 4 min, shown as 3–6 | Estimate, interchange walk plus wait |
| Bus ride | about 19 km/h plus stops | Estimate |
| Ranking | middle of range + 5/change + half the range width + 4 for buses | Chosen to match Arjun's stated preference for predictability |
| Crowding penalty | +6 High, +2 Moderate at boarding or interchange | Chosen so crowding can outweigh a few minutes, which is the persona's whole point |
| Rain penalty | +12 cycling into rain at the start, +8 at the end | Start matters more: he would arrive wet and stay wet |
| Later-departure penalty | 0.15 per minute | Keeps the morning check from recommending a much later, marginally better trip |
| Sheltered | within 30 m of a covered way, sampled every 25 m | 30 m is a generous "you could duck under it"; the sampling interval bounds the error |

A time range is always shown rather than a single number, because a single number would be
more confident than the inputs justify.

---

## 4. What is real and what is not

The brief caps scores for mocked data presented as live, so the app labels everything.

**Real when a key is set:** train alerts, crowding, bus arrival times and loads, bike
parking and its shelter flag, planned works, weather, address search, and — with OSRM
running — walking and cycling geometry.

**Real without any key:** the OpenStreetMap base map, the covered walkway network, the bus
network from BusRouter SG, the rail graph, and the weather forecast.

**Simulated, and labelled as such in the UI:** bus arrival times when no key is set, the
bus services themselves when `busdata.json` has not been generated, fares, and the moving
vehicle in the trip simulation. Settings shows a row per dataset saying whether it is really
installed, and the "Use test data" switch is forced on and explained when no key is present.

**Test data:** the replays in `test_data/`, used to demonstrate the disruption path because
`AffectedSegments` is empty on a normal day. Every replay answer is flagged `test_data` by
the API and carries a **Test data** tag in the UI.

---

## 5. Underground, with no signal

The brief asks us to decide and state this. `frontend/sw.js`:

- The app shell, vendored map libraries, bus data and covered walkways are cached on install,
  so the app opens with no network.
- Live endpoints are network-first with a six second timeout, falling back to the last good
  answer. That answer carries the time it was fetched, and the app says **"No signal. Showing
  conditions saved at HH:MM"** — and says something different again when it has nothing
  saved, rather than looking identical to a live screen.
- `singapore.pmtiles` is deliberately not cached: tens of megabytes, read with byte-range
  requests that the Cache API cannot serve usefully. The map keeps the tiles the page holds.

Service workers need HTTPS or localhost; on a plain-http address the app runs without the
offline cache.

---

## 6. Privacy

Stored in the browser only: the routine, settings, and any bus data loaded. Sent to our own
server only: the start and end of a trip, for routing and weather, and search text for
OneMap. Nothing is stored server-side and nothing is shared. **Clear my data from this
device** in Settings removes it. The DataMall key lives in `.env`, is git-ignored, and
`/api/*` reports only whether it is set.

---

## 7. Limits we know about

1. **`FreeMRTShuttle` route text is unverified.** It is our reading of the guide rather than
   a copy of a live sample, and checking it needs a real disruption to be running. The
   `PCDForecast` station/interval shape *was* a guess and is now confirmed against a live
   response (station rows keyed `Interval` and `Station`). `tools/check_live.py` prints both.
2. **The planned-events field names are defensive guesses.** Each endpoint names its columns
   differently; we read through a list of candidate names and keep anything unrecognised
   under `raw` so a real response can be inspected. A renamed column loses that field rather
   than breaking.
3. **Fares are estimated**, not from a fare table.
4. **The trip simulation is a simulation.** There is no live vehicle position feed in it.
5. **Covered walkways are OpenStreetMap, not LTA.** `CoveredLinkWay` is authoritative and
   would be the upgrade; it ships as a shapefile download and needs different tooling.
6. **Road works are matched to a route by name.** An event is labelled "On your route" only
   when it names a bus service, line or station the journey uses; a name-only match is
   labelled "Named nearby" instead, because those are different claims.
7. **No accessibility pass yet.** Contrast, text scaling and screen-reader labels have not
   been reviewed, so we do not claim the app serves Mdm Lim.
8. **One persona, tested on one journey.** Punggol to one-north is what we have walked end
   to end.
9. **OSRM is optional and off by default.** Without Docker, street legs are straight-line
   estimates, labelled **Street legs estimated**.
10. **Browser testing is Playwright at 390×844**, plus hand checks. There is no automated
    frontend test suite; the 23 automated tests cover the backend.

---

## 8. Running it

`README.md` has the full path from a clean machine: Python 3.10+, a virtualenv, the
DataMall key in `.env`, then `uvicorn backend.main:app`. The optional downloads — the
OpenStreetMap basemap, real bus routes, covered walkways and OSRM — are each one command,
and the app says in Settings which of them are actually installed.
