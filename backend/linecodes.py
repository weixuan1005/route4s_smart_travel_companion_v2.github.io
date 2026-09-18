"""
One canonical line table (PS2 brief, 2.4: "line codes are not consistent across endpoints").

Every line code from any feed is mapped through this table:
  * TrainServiceAlerts (TSA) codes:  STL, PTL, BPL ... Circle Line Extension is folded into CCL,
    Changi Extension into EWL
  * Station Crowd Density (PCD) codes: SLRT, PLRT, BPL ... with separate CEL and CGL
  * the app's own line keys (frontend LINES): NSL, EWL, CGL, NEL, CCL, DTL, TEL, BPL,
    SKE/SKW (Sengkang LRT loops), PGE/PGW (Punggol LRT loops)
  * station-code prefixes, e.g. NE17 -> NEL, PW3 -> Punggol LRT (PGW loop)
"""
import json
import re
from pathlib import Path

CANON = {
    "NSL":   {"name": "North-South Line",        "tsa": ["NSL"], "pcd": ["NSL"],        "app": ["NSL"]},
    "EWL":   {"name": "East-West Line",          "tsa": ["EWL"], "pcd": ["EWL", "CGL"], "app": ["EWL", "CGL"]},
    "NEL":   {"name": "North East Line",         "tsa": ["NEL"], "pcd": ["NEL"],        "app": ["NEL"]},
    "CCL":   {"name": "Circle Line",             "tsa": ["CCL"], "pcd": ["CCL", "CEL"], "app": ["CCL"]},
    "DTL":   {"name": "Downtown Line",           "tsa": ["DTL"], "pcd": ["DTL"],        "app": ["DTL"]},
    "TEL":   {"name": "Thomson-East Coast Line", "tsa": ["TEL"], "pcd": ["TEL"],        "app": ["TEL"]},
    "BPLRT": {"name": "Bukit Panjang LRT",       "tsa": ["BPL"], "pcd": ["BPL"],        "app": ["BPL"]},
    "SKLRT": {"name": "Sengkang LRT",            "tsa": ["STL"], "pcd": ["SLRT"],       "app": ["SKE", "SKW"]},
    "PGLRT": {"name": "Punggol LRT",             "tsa": ["PTL"], "pcd": ["PLRT"],       "app": ["PGE", "PGW"]},
}

# station-code prefix -> (canonical line, app line key)
PREFIX = {
    "NS": ("NSL", "NSL"), "EW": ("EWL", "EWL"), "CG": ("EWL", "CGL"), "NE": ("NEL", "NEL"),
    "CC": ("CCL", "CCL"), "CE": ("CCL", "CCL"), "DT": ("DTL", "DTL"), "TE": ("TEL", "TEL"),
    "BP": ("BPLRT", "BPL"), "SE": ("SKLRT", "SKE"), "SW": ("SKLRT", "SKW"),
    "PE": ("PGLRT", "PGE"), "PW": ("PGLRT", "PGW"),
}
# interchange codes without a number
SPECIAL = {"STC": ("SKLRT", None), "PTC": ("PGLRT", None)}

_TSA = {c: k for k, v in CANON.items() for c in v["tsa"]}
_PCD = {c: k for k, v in CANON.items() for c in v["pcd"]}

STATIONS = json.loads((Path(__file__).parent / "data" / "station_codes.json").read_text(encoding="utf-8"))["stations"]
CODE_RE = re.compile(r"\b(STC|PTC|[A-Z]{2}\d{1,2}|CG)\b")


def canon_from_tsa(code):
    return _TSA.get((code or "").strip().upper())


def canon_from_pcd(code):
    return _PCD.get((code or "").strip().upper())


def pcd_codes(canon):
    """TrainLine values to request from PCDRealTime / PCDForecast for a canonical line."""
    return CANON[canon]["pcd"]


def split_code(code):
    m = re.fullmatch(r"([A-Z]{2})(\d{0,2})", code)
    return (m.group(1), int(m.group(2) or 0)) if m else (code, 0)


def line_of_station_code(code):
    """(canonical line, app line key) for a station code; app key is None for shared interchange codes."""
    code = code.strip().upper()
    if code in SPECIAL:
        return SPECIAL[code]
    return PREFIX.get(split_code(code)[0], (None, None))


def station_name(code):
    row = STATIONS.get(code.strip().upper())
    return row["name"] if row else None


def codes_in(text):
    """All station codes found in a free-form field such as FreeMRTShuttle."""
    return [m.group(1) for m in CODE_RE.finditer((text or "").upper())]
