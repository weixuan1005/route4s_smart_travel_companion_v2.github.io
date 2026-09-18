"""Run with:  python -m pytest -q   (from the project folder)"""
from fastapi.testclient import TestClient

from backend import alerts, linecodes as lc
from backend.main import app

client = TestClient(app)


def test_line_code_trap_is_handled():
    # PS2 brief 2.4: same line, different codes per endpoint
    assert lc.canon_from_tsa("STL") == lc.canon_from_pcd("SLRT") == "SKLRT"
    assert lc.canon_from_tsa("PTL") == lc.canon_from_pcd("PLRT") == "PGLRT"
    assert lc.canon_from_tsa("BPL") == lc.canon_from_pcd("BPL") == "BPLRT"
    assert lc.canon_from_pcd("CEL") == lc.canon_from_tsa("CCL") == "CCL"
    assert lc.canon_from_pcd("CGL") == lc.canon_from_tsa("EWL") == "EWL"
    assert lc.pcd_codes("PGLRT") == ["PLRT"]


def test_station_codes():
    assert lc.station_name("NE17") == "Punggol"
    assert lc.station_name("PTC") == "Punggol"
    assert lc.station_name("CC23") == "one-north"
    assert lc.station_name("CE1") == "Bayfront"          # older Circle Line Extension code
    assert lc.line_of_station_code("PW3") == ("PGLRT", "PGW")
    assert lc.line_of_station_code("CG1") == ("EWL", "CGL")


def test_normal_day_has_no_segments_but_keeps_messages():
    r = alerts.load_replay("tsa_normal_day")
    assert r["status"] == 1 and not r["disrupted"] and r["segments"] == []
    assert r["messages"] and r["test_data"] is True


def test_nel_disruption_is_parsed_with_mitigation():
    r = alerts.load_replay("tsa_nel_punggol_serangoon")
    seg = r["segments"][0]
    assert r["disrupted"] and seg["line"] == "NEL" and seg["app_lines"] == ["NEL"]
    assert (seg["from"], seg["to"]) == ("Serangoon", "Punggol")
    assert [s["name"] for s in seg["free_public_bus"]["stations"]][0] == "Serangoon"
    assert len(seg["free_mrt_shuttle"]["stations"]) == 6
    assert seg["unknown_codes"] == []


def test_lrt_alert_maps_to_the_right_loop():
    seg = alerts.load_replay("tsa_ptl_west_loop")["segments"][0]
    assert seg["line"] == "PGLRT" and seg["app_lines"] == ["PGW"]
    assert seg["free_mrt_shuttle"]["stations"] == []


def test_live_style_quirks():
    r = alerts.parse({"value": {"Status": "2", "AffectedSegments": [
        {"Line": "EWL", "Direction": "Pasir Ris", "Stations": "EW4, CG1,CG2", "FreePublicBus": "Free bus service island wide",
         "FreeMRTShuttle": "", "MRTShuttleDirection": ""}], "Message": {"Content": "x", "CreatedDate": "y"}}})
    seg = r["segments"][0]
    assert r["status"] == 2 and seg["app_lines"] == ["CGL", "EWL"]
    assert seg["free_public_bus"]["islandwide"] and seg["direction"] == "Pasir Ris"
    assert len(r["messages"]) == 1


def test_api_endpoints():
    assert "tsa_nel_punggol_serangoon" in client.get("/api/replays").json()["replays"]
    r = client.get("/api/alerts", params={"replay": "tsa_nel_punggol_serangoon"}).json()
    assert r["test_data"] and r["segments"][0]["from"] == "Serangoon"
    assert client.get("/api/alerts", params={"replay": "../backend/main"}).status_code == 404
    live = client.get("/api/alerts").json()      # no key in tests: says so instead of faking data
    assert live["source"] == "unavailable" and live["test_data"] is False
    assert client.get("/api/crowd", params={"line": "XYZ"}).status_code == 400
    assert client.get("/api/crowd", params={"line": "PGLRT"}).json()["source"] == "unavailable"
    h = client.get("/api/health").json()
    assert "datamall_key_set" in h and "LTA_ACCOUNT_KEY" not in str(h)
