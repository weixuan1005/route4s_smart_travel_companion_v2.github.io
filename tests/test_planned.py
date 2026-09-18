"""Planned events: the half of the brief that is known in advance."""
import datetime

from fastapi.testclient import TestClient

from backend import planned
from backend.main import app

client = TestClient(app)
TODAY = datetime.date.today().isoformat()


def test_replay_splits_today_from_soon():
    r = client.get("/api/planned", params={"replay": "planned_arjun_week"})
    assert r.status_code == 200
    body = r.json()
    assert body["test_data"] is True and body["source"] == "replay:planned_arjun_week"

    kinds = {e["kind"] for e in body["today"]}
    assert "roadworks" in kinds and "lift_maintenance" in kinds
    # The works that ended a month ago are not "today"
    assert all("Completed works" not in (e["detail"] or "") for e in body["today"])
    # The bus route change and road opening start in three days
    soon = {e["kind"] for e in body["soon"]}
    assert "bus_route_change" in soon and "road_opening" in soon
    assert all(e["starts"] > TODAY for e in body["soon"])


def test_fields_are_read_across_datamall_naming():
    """Each endpoint names its columns differently; the record shape must not depend on that."""
    rec = planned.normalise({"ServiceNo": "119", "EffectiveDate": "2026-09-21",
                             "Description": "Route amended"}, "bus_route_change", "live")
    assert rec["title"] == "119" and rec["starts"] == "2026-09-21" and rec["detail"] == "Route amended"

    lift = planned.normalise({"StationCode": "NE17", "StationName": "Punggol", "Line": "NEL",
                              "Remarks": "Lift B out", "StartDate": "21/09/2026"}, "lift_maintenance", "live")
    assert lift["station"] == "NE17" and lift["line"] == "NEL" and lift["starts"] == "2026-09-21"

    # An unrecognised column is kept rather than dropped, so a real response can be inspected.
    odd = planned.normalise({"SomethingNew": "value", "RoadName": "Punggol Way"}, "roadworks", "live")
    assert odd["raw"] == {"SomethingNew": "value"} and odd["where"] == "Punggol Way"


def test_dates_survive_datamall_formats_and_junk():
    assert planned._as_date("21/09/2026") == "2026-09-21"
    assert planned._as_date("2026-09-21") == "2026-09-21"
    assert planned._as_date("2026-09-21T08:30:00") == "2026-09-21"
    assert planned._as_date("not a date") == ""     # unreadable, not a crash
    assert planned._as_date("") == ""


def test_an_event_with_no_dates_counts_as_running():
    rec = planned.normalise({"RoadName": "Somewhere"}, "roadworks", "live")
    assert planned.active_on(rec, TODAY) is True
    assert planned.upcoming(rec, TODAY, 7) is False


def test_without_a_key_it_says_unavailable_rather_than_inventing():
    body = client.get("/api/planned").json()
    assert body["source"] == "unavailable" and body["today"] == [] and body["soon"] == []


def test_replay_name_cannot_escape_test_data():
    assert client.get("/api/planned", params={"replay": "../backend/main"}).status_code == 404
    assert client.get("/api/planned", params={"replay": "tsa_normal_day"}).status_code == 404
