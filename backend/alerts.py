"""
TrainServiceAlerts -> one normalised shape the app can act on.

Live response shape (PS2 brief, 2.4):
  Status             1 = normal / minor delays, 2 = disrupted / major delays
  AffectedSegments   list, empty on a normal day. Each entry:
                       Line, Direction, Stations ("NE1,NE3,..."), FreePublicBus,
                       FreeMRTShuttle, MRTShuttleDirection
  Message            list of {Content, CreatedDate}, populated daily

Replays in test_data/ use exactly the same shape, so the same parser handles both,
and every replay result is flagged test_data=True for the UI to label.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from . import linecodes as lc

TEST_DATA = Path(__file__).resolve().parent.parent / "test_data"


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _stations(codes):
    out = []
    for code in codes:
        canon, app = lc.line_of_station_code(code)
        out.append({"code": code, "name": lc.station_name(code), "line": canon, "app_line": app})
    return out


def parse_segment(seg):
    line_code = str(seg.get("Line", "")).strip()
    canon = lc.canon_from_tsa(line_code)
    codes = [c.strip().upper() for c in str(seg.get("Stations", "")).split(",") if c.strip()]
    stations = _stations(codes)
    # app loop/branch keys actually touched, e.g. Punggol LRT codes PW* -> PGW
    app_lines = sorted({s["app_line"] for s in stations if s["app_line"]}) or (lc.CANON[canon]["app"] if canon else [])
    bus = str(seg.get("FreePublicBus", "") or "").strip()
    shuttle = str(seg.get("FreeMRTShuttle", "") or "").strip()
    return {
        "line_code": line_code,
        "line": canon,
        "line_name": lc.CANON[canon]["name"] if canon else line_code,
        "app_lines": app_lines,
        "direction": str(seg.get("Direction", "") or "Both").strip() or "Both",
        "stations": stations,
        "from": stations[0]["name"] if stations else None,
        "to": stations[-1]["name"] if stations else None,
        "free_public_bus": {
            "raw": bus,
            "islandwide": "island" in bus.lower(),
            "stations": _stations(lc.codes_in(bus)),
        },
        "free_mrt_shuttle": {
            "raw": shuttle,  # the shuttle route is encoded here; keep the original text
            "stations": _stations(lc.codes_in(shuttle)),
            "direction": str(seg.get("MRTShuttleDirection", "") or "").strip() or None,
        },
        "unknown_codes": [s["code"] for s in stations if not s["name"]],
    }


def parse(payload, source="live", test_data=False):
    body = payload.get("value", payload) if isinstance(payload, dict) else {}
    if isinstance(body, list):          # tolerate a list-wrapped value
        body = body[0] if body else {}
    try:
        status = int(body.get("Status", 1))
    except (TypeError, ValueError):
        status = None
    segments = [parse_segment(s) for s in _as_list(body.get("AffectedSegments")) if isinstance(s, dict)]
    messages = [{"content": m.get("Content", ""), "created": m.get("CreatedDate", "")}
                for m in _as_list(body.get("Message")) if isinstance(m, dict)]
    return {
        "status": status,
        "disrupted": status == 2 or bool(segments),
        "segments": segments,
        "messages": messages,
        "source": source,
        "test_data": test_data,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def replay_names():
    return sorted(p.stem for p in TEST_DATA.glob("tsa_*.json"))


def load_replay(name):
    path = TEST_DATA / f"{name}.json"
    if path.parent != TEST_DATA or not path.exists():   # no path tricks, known files only
        raise FileNotFoundError(name)
    return parse(json.loads(path.read_text(encoding="utf-8")), source=f"replay:{name}", test_data=True)
