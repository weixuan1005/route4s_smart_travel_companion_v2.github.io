"""
Planned events -> one normalised shape the app can act on.

The brief treats planned and unplanned disruption as equally important: scheduled
works, early closures and maintenance windows are known in advance and are just as
disruptive to a commuter. These are the "known in advance" half.

  * RoadWorks                 approved road works, with a start and end date
  * RoadOpenings              planned road openings, same shape
  * PlannedBusRoutes          new and changed bus routes, published before they take effect
  * v2/FacilitiesMaintenance  ad hoc lift maintenance at MRT stations, down to the
                              individual lift and the exit it serves

Each becomes the same record:

    {kind, title, detail, where, station, line, starts, ends, source, test_data}

DataMall's field names differ between these endpoints and the guide does not always
match what the service returns, so every field is read defensively through a list of
candidate names: an endpoint that renames a column loses that column rather than
breaking the response. Anything genuinely unrecognised keeps its raw payload under
"raw" so a real response can be inspected without another deploy.

Replays in test_data/planned_*.json use the same shape as the live responses, and every
replay result is flagged test_data=True for the UI to label.
"""
import json
from datetime import date, datetime, timezone
from pathlib import Path

from . import datamall

TEST_DATA = Path(__file__).resolve().parent.parent / "test_data"

# endpoint -> the kind of event it describes
ENDPOINTS = {
    "RoadWorks": "roadworks",
    "RoadOpenings": "road_opening",
    "PlannedBusRoutes": "bus_route_change",
    "v2/FacilitiesMaintenance": "lift_maintenance",
}
TTL = 6 * 3600  # these change rarely; do not ask DataMall on every page load

# Candidate field names, most specific first. DataMall is not consistent between endpoints.
FIELDS = {
    "title": ("EventID", "Name", "ServiceNo", "StationName", "Station"),
    "detail": ("Other", "Description", "Remarks", "Message", "Reason", "Comments"),
    # "Direction" is deliberately not here: on a bus route it is 1 or 2, not a place.
    "where": ("RoadName", "Location", "StationName", "Landmark"),
    "station": ("StationCode", "Station", "StnCode"),
    "line": ("Line", "TrainLine", "LineCode"),
    "starts": ("StartDate", "EffectiveDate", "StartTime", "FromDate", "Date"),
    "ends": ("EndDate", "ExpiryDate", "EndTime", "ToDate"),
}


def _first(row, names):
    for n in names:
        v = row.get(n)
        if v not in (None, "", []):
            return str(v).strip()
    return ""


def _as_date(text):
    """DataMall dates arrive in several shapes. Return YYYY-MM-DD, or "" if unreadable."""
    text = (text or "").strip()
    if not text:
        return ""
    formats = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y",
               "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S")
    # Try the whole value first, then just its date part, so a timestamp in an unexpected
    # shape still yields a date rather than nothing.
    for candidate in (text, text.split("T")[0], text.split(" ")[0]):
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt).date().isoformat()
            except ValueError:
                continue
    return ""


def normalise(row, kind, source):
    """One DataMall row -> the record the app uses. Unknown fields are kept under "raw"."""
    known = {n for names in FIELDS.values() for n in names}
    rec = {
        "kind": kind,
        "title": _first(row, FIELDS["title"]) or kind.replace("_", " ").title(),
        "detail": _first(row, FIELDS["detail"]),
        "where": _first(row, FIELDS["where"]),
        "station": _first(row, FIELDS["station"]),
        "line": _first(row, FIELDS["line"]),
        "starts": _as_date(_first(row, FIELDS["starts"])),
        "ends": _as_date(_first(row, FIELDS["ends"])),
        "source": source,
        "test_data": source.startswith("replay"),
    }
    extra = {k: v for k, v in row.items() if k not in known and v not in (None, "", [])}
    if extra:
        rec["raw"] = extra
    return rec


def active_on(rec, day):
    """Is this event running on `day`? An event with no dates is treated as current,
    because a work item with no window is still something LTA has published."""
    if rec["starts"] and rec["starts"] > day:
        return False
    if rec["ends"] and rec["ends"] < day:
        return False
    return True


def upcoming(rec, day, within_days):
    """Starts later than `day` but within the window: the proactive half."""
    if not rec["starts"] or rec["starts"] <= day:
        return False
    start = date.fromisoformat(rec["starts"])
    return 0 < (start - date.fromisoformat(day)).days <= within_days


def replay_names():
    return sorted(p.stem for p in TEST_DATA.glob("planned_*.json"))


def load_replay(name):
    path = TEST_DATA / f"{name}.json"
    if not name.startswith("planned_") or path.parent != TEST_DATA or not path.exists():
        raise FileNotFoundError(name)
    raw = json.loads(path.read_text(encoding="utf-8"))
    return collect(raw, f"replay:{name}")


def collect(by_endpoint, source):
    """{endpoint: DataMall response} -> normalised records, newest start first."""
    out = []
    for endpoint, kind in ENDPOINTS.items():
        data = by_endpoint.get(endpoint) or {}
        for row in data.get("value", []):
            if isinstance(row, dict):
                out.append(normalise(row, kind, source))
    out.sort(key=lambda r: (r["starts"] or "9999-99-99", r["title"]))
    return out


async def fetch():
    """Ask DataMall for every planned-event endpoint. One failing endpoint does not sink
    the rest: it is reported in "unavailable" so the app can say what it could not check."""
    by_endpoint, unavailable = {}, {}
    for endpoint in ENDPOINTS:
        try:
            by_endpoint[endpoint] = await datamall.get(endpoint, ttl=TTL)
        except datamall.NoKey:
            raise
        except Exception as e:
            unavailable[endpoint] = type(e).__name__
    return collect(by_endpoint, "live"), unavailable


def summary(records, day=None, within_days=7):
    """Split into what is running today and what starts soon, which is what the app shows."""
    day = day or datetime.now(timezone.utc).date().isoformat()
    return {
        "day": day,
        "today": [r for r in records if active_on(r, day)],
        "soon": [r for r in records if upcoming(r, day, within_days)],
        "total": len(records),
    }
