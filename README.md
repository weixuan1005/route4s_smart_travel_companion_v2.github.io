# Smart Commuter Companion

A phone-first web app that plans a door-to-door commute in Singapore and changes its advice
when the network does — a train disruption, a crowded platform, rain on the cycling leg, or
road works that were announced last week.

Built for the **LTA Smart Mobility Hackathon, Problem Statement 2**, around one commuter:
**Arjun**, who travels Punggol → one-north, cycles to the LRT, and would rather leave twenty
minutes later than stand in a crush.

---

## Quickest look: no installing anything

**<https://weixuan1005.github.io/route4s_smart_travel_companion_v2.github.io/>**

Open it on your phone. Route planning, the disruption rerouting, the sheltered walkways and
the demo scenarios all work there.

The street map is a large file the browser reads in pieces, which not every host serves. If
the map shows only coloured lines and stations on a plain background, that is what happened —
the version you run yourself, below, always has it.

What you will **not** get there: live LTA data. That needs the small server described below,
because the key that talks to LTA must not live in a web page. Everything on that page that
isn't live is labelled **Test data** or **simulated**, never dressed up as real.

---

## Full version on your own computer

This part uses **Terminal**, the app where you type commands instead of clicking. If you have
never opened it, that is fine — everything you need is below, in order.

**How to open Terminal (Mac):** press **Cmd + Space**, type `Terminal`, press **Enter**.
A window opens with a line of text ending in `%`. That is the prompt; it means it is waiting
for you.

**How to run a command:** copy a grey line from this page, paste it into Terminal
(**Cmd + V**), press **Enter**, and wait until the `%` prompt comes back before doing the next
one. Some commands print a lot, some print nothing — **printing nothing usually means it
worked**. Only stop if you see the word `error` or `fatal`.

Total time: about ten minutes, most of it waiting for downloads.

### Step 1 — check you have a recent Python

```bash
python3 --version
```

If it prints **3.10 or higher**, skip to Step 2.

If it prints **3.9** (what Macs come with) it is too old and the app will not start. Install a
newer one — the first line installs Homebrew, a tool that installs other tools, and it will
ask for your Mac password:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

```bash
brew install python@3.12
```

Then use `python3.12` everywhere this page says `python3`.

### Step 2 — download the app

```bash
mkdir -p ~/Developer && cd ~/Developer
```

```bash
git clone https://github.com/weixuan1005/route4s_smart_travel_companion_v2.github.io.git route4us
```

```bash
cd route4us
```

You now have a folder called **route4us** in your home folder, and Terminal is "inside" it.
Every later command assumes that. If you close Terminal and come back, get back there with
`cd ~/Developer/route4us`.

### Step 3 — install what the app needs

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

Your prompt now starts with `(.venv)`. That means the app's own private set of tools is
active. **Every new Terminal tab needs this line again.**

```bash
pip install -r backend/requirements.txt
```

This prints several pages and takes a minute.

### Step 4 — start it

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

You should see `Uvicorn running on http://0.0.0.0:8000`. **Leave this window alone** — this is
the app running. It stays there, and that is correct.

Open **<http://localhost:8000>** in your browser. That's it, the app is working.

To stop it later, click that Terminal window and press **Ctrl + C**.

### Step 5 — open it on your phone (optional)

With your phone on the same Wi-Fi, open a **new** Terminal tab (**Cmd + T**) and run:

```bash
cd ~/Developer/route4us && source .venv/bin/activate
```

```bash
ipconfig getifaddr en0 || ipconfig getifaddr en1
```

It prints an address like `192.168.1.42`. On your phone, browse to `http://192.168.1.42:8000`.
The first time, macOS asks whether to allow incoming connections — say yes, or the phone
cannot reach it.

---

## Making it show real data

The app already includes the street map, the real bus network and the covered walkways. Two
things are not included and need you: the LTA key, and street-level routing. Run these in the
second Terminal tab, from the `route4us` folder with `(.venv)` showing.

### Live LTA data (train disruptions, crowding, bus arrivals, bike racks)

Get a free AccountKey from **<https://datamall.lta.gov.sg>** — register, then request API
access; the key arrives by email.

```bash
cp .env.example .env
```

```bash
open -e .env
```

That opens a small settings file in TextEdit. Find the line starting `LTA_ACCOUNT_KEY=` and
paste your key straight after the `=`, with no spaces. Save (**Cmd + S**) and close.

> Type the key into the file rather than using a Terminal command, so it is not left behind
> in your command history. The file is never uploaded to GitHub.

Check LTA accepts it:

```bash
python tools/check_live.py
```

Every line should say `OK`. A brand-new key is sometimes refused for a while — if you get
`401` or `403`, wait and run it again. Then **restart the app**: click the first Terminal
window, press **Ctrl + C**, and start it again with the command from Step 4.

In the app, **Settings → Live data** now says *Key set*, and you can switch **Use test data**
off.

### The street map, bus routes and sheltered walkways: already included

These three ship with the download, so there is nothing to do:

| What | File | What it gives you |
|---|---|---|
| OpenStreetMap street map of Singapore | `frontend/map/singapore.pmtiles` | Real streets, water and parks under the route |
| LTA bus stops and routes | `frontend/busdata.json` | Real bus services instead of invented ones |
| Covered walkways | `frontend/covered.json` | How much of a walk is under shelter |

**Settings** shows a row for each, saying whether it is really installed — so what is on
screen is what you actually have.

They are snapshots, so run these only when you want fresher data:

```bash
python tools/get_map.py
```

```bash
python tools/fetch_bus_data.py --no-key --out frontend/busdata.json
```

```bash
python tools/get_covered.py
```

### Street-level walking and cycling routes (needs Docker)

Without this, walking and cycling legs are straight lines between two points, drawn dashed
and labelled **Street legs estimated**. With it, they follow real streets and cycle paths.

Install Docker Desktop:

```bash
brew install --cask docker
```

Then **open Docker Desktop from Applications** and wait until it says the engine is running.
Installing it is not enough — nothing below works until that app is open. Check with:

```bash
docker --version
```

```bash
brew install osmium-tool
```

```bash
python tools/get_osm.py --clip
```

Downloads the OpenStreetMap data. `--clip` (which needs `osmium-tool` above) trims it to
Singapore and makes the next step far faster; without it you download 400+ MB.

```bash
docker compose up -d
```

Or run `docker compose up` without `-d` to watch it work instead of guessing.

The first run builds the routing data and takes several minutes, looking idle while it works.
Check it when it finishes:

```bash
curl "http://localhost:5001/route/v1/foot/103.8965,1.4102;103.9024,1.4053"
```

You want `"code":"Ok"` in the reply. Refresh the app and the note under the map changes to
*"Cycling and walking legs follow OpenStreetMap streets"*.

Turn the routing servers off again with `docker compose down`.

---

## If something goes wrong

| What you see | What to do |
|---|---|
| `command not found: python3` | Install Python — Step 1 |
| `TypeError: unsupported operand type(s) for \|` | Your Python is 3.9 — redo Step 1, then Step 3 |
| `command not found: uvicorn` | The `(.venv)` is missing — run `source .venv/bin/activate` |
| `Address already in use` | It is already running in another window. Use that one, or `lsof -ti:8000 \| xargs kill` |
| `externally-managed-environment` | You skipped the virtual environment — redo Step 3 |
| Browser says "can't connect" | The Terminal window running the app was closed or stopped — redo Step 4 |
| Settings says "No backend found" | You opened the file directly instead of `http://localhost:8000` |
| `zsh: command not found: docker` | Docker is not installed yet — `brew install --cask docker`, then open Docker Desktop from Applications |
| `Cannot connect to the Docker daemon` | Docker Desktop is installed but not open — launch it from Applications and wait for it to say the engine is running |
| `PBF error: unexpected EOF` from osmium | The extract download was cut short. `rm -rf osrm` and run `python tools/get_osm.py --clip` again |
| `unknown shorthand flag: 'd' in -d` | The hyphen was turned into a dash on its way into Terminal. Type `docker compose up -d` by hand, or run `docker compose up` without the flag |
| `no matching manifest for linux/arm64` | The OSRM image is Intel-only. In Docker Desktop, Settings → General, tick **Use Rosetta for x86/amd64 emulation**, then try again |

---

## Using the app

1. **Trip** opens first. From is Home (near Sumang LRT), To is Work (Fusionopolis). Search any
   address, place or station, or use **📍 My location**.
2. Pick **Leave now**, **Leave at** or **Arrive by**, and whether you are bringing a bike and
   whether it folds. A non-folding bike rules out the bus, and the app says so.
3. **Find routes** shows the options. The chips above the map — **All, Train, Bus, Cycle,
   Walk only** — filter to one way of travelling, each with how many options it has.
4. The map draws the chosen route in colour and the others in grey. Dashed cycling and walking
   lines mean straight-line estimates; solid means real street routing.
5. Each option lists **why**: "Busy platform at Punggol around 08:13 (High, forecast)". Tags
   like **Best for Arjun** and **Fastest** say what it was chosen for.
6. **Start this trip** hands over to **Navigate** for turn-by-turn steps.
7. **Morning check**, at the top, tries a departure every 10 minutes across your window and
   either confirms your usual time or suggests a better one, with reasons. **My routine** sets
   the days, the window and the alert threshold.
8. During a disruption the planner avoids the closed stretch, and when LTA's feed lists a free
   bridging bus it offers the usual route with that bus in between.
9. **Weather now** shows the two-hour forecast for both ends of the trip. **Planned works**
   shows road works, lift maintenance and bus route changes, marked **On your route** when a
   station, line or bus service you use is named, or **Named nearby** when only the name
   matches.

Notifications appear while the app is open or in a background tab. Alerts with the app fully
closed would need a push server, which is not built.

The home and work locations are a demo profile: public places, not anyone's address. Nothing
about a trip leaves your own server except the start and end points needed for place search
and street routing.

`WRITEUP.md` covers the persona, the architecture, where each estimated number came from, and
the limits we know about.

---

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
| `/api/planned` | Planned works: `RoadWorks`, `RoadOpenings`, `PlannedBusRoutes` and `v2/FacilitiesMaintenance`, split into what runs today and what starts soon |
| `/api/geocode?q=fusionopolis` | Place search through OneMap |
| `/api/route?mode=bike&from=lat,lon&to=lat,lon` | Street leg from OSRM on OpenStreetMap, or an estimate marked `"source": "estimate"` |

Without a key, live endpoints answer `"source": "unavailable"` rather than inventing data.

### Underground, with no signal

`frontend/sw.js` caches the app shell, the vendored map libraries and the bus and shelter
data, so the app opens between stations. Live endpoints are network-first with a six second
timeout and fall back to the last good answer, which carries the time it was fetched: the app
says **"No signal. Showing conditions saved at HH:MM"** rather than presenting stale data as
live, and says so differently when it has nothing saved at all.

`singapore.pmtiles` is deliberately **not** cached. It is tens of megabytes and is read with
byte-range requests, which the Cache API cannot serve usefully; the map keeps whatever tiles
the page already holds and the rest of the journey stays readable.

Service workers need HTTPS or localhost. On a plain-http address the app still runs, without
the offline cache.

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
| `planned_arjun_week` | A lift out at Punggol, works on Punggol Way, and a bus route change and road opening starting in three days |

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
