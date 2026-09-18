"""Live-condition endpoints, using the labelled replays in test_data/."""
from fastapi.testclient import TestClient

from backend import live
from backend.main import app

client = TestClient(app)


def test_crowd_replay_realtime_and_forecast():
    r = client.get("/api/crowd", params={"line": "NEL", "replay": "pcd_arjun_morning"}).json()
    levels = {x["station"]: x["level"] for x in r["rows"]}
    assert r["test_data"] and levels["Punggol"] == "high" and levels["Serangoon"] == "moderate"
    f = client.get("/api/crowd", params={"line": "CCL", "kind": "forecast", "replay": "pcd_arjun_morning"}).json()
    serangoon = [x for x in f["rows"] if x["station"] == "Serangoon"]
    assert [x["level"] for x in serangoon][:4] == ["moderate", "high", "high", "high"]
    assert serangoon[0]["start"].startswith("2026-09-18T07:00")
    p = client.get("/api/crowd", params={"line": "PGLRT", "replay": "pcd_arjun_morning"}).json()
    assert {x["feed_line"] for x in p["rows"]} == {"PLRT"}          # line-code mapping used
    assert client.get("/api/crowd", params={"line": "NEL", "replay": "nope"}).status_code == 404


def test_weather_nearest_area_and_rain():
    w = client.get("/api/weather", params={"lat": 1.4102, "lon": 103.8965, "replay": "weather_punggol_showers"}).json()
    assert w["area"] == "Punggol" and w["rain"] and w["forecast"] == "Showers" and w["test_data"]
    o = client.get("/api/weather", params={"lat": 1.2991, "lon": 103.7876, "replay": "weather_punggol_showers"}).json()
    assert o["area"] == "Queenstown" and not o["rain"]
    assert client.get("/api/weather", params={"lat": 40.7, "lon": -74}).status_code == 422


def test_weather_accepts_unwrapped_shape():
    raw = live.replay("weather_dry_morning", "weather_")["data"]
    w = live.parse_weather(raw, 1.40, 103.9, "live")
    assert w["area"] == "Punggol" and w["rain"] is False and w["valid_text"] == "7.30 am to 9.30 am"


def test_bike_parking_and_bus_arrival():
    b = client.get("/api/bike-parking", params={"lat": 1.4086, "lon": 103.8983, "replay": "bikeparking_sumang"}).json()
    assert b["parking"][0] == {"name": "Sumang Lrt Station", "lat": 1.40865, "lon": 103.8983, "racks": 40,
                               "rack_type": "Yellow Box", "sheltered": True}
    a = client.get("/api/bus-arrival", params={"replay": "busarrival_demo"}).json()
    svc = a["services"][0]
    assert svc["service"] == "83" and len(svc["next"]) == 2          # empty NextBus3 dropped
    assert svc["next"][0]["load"] == "SEA" and svc["next"][0]["wheelchair"] and svc["next"][1]["monitored"] is False


def test_live_without_key_says_unavailable():
    assert client.get("/api/bus-arrival", params={"stop": "65009"}).json()["source"] == "unavailable"
    assert client.get("/api/bike-parking", params={"lat": 1.4, "lon": 103.9}).json()["source"] == "unavailable"
    assert client.get("/api/bus-arrival", params={"stop": "abc"}).status_code == 422
    assert client.get("/api/bus-arrival").status_code == 400
    s = client.get("/api/status").json()
    assert s["datamall"] is False and "pcd_arjun_morning" in s["replays"]["crowd"]
    assert client.get("/api/bus-arrival", params={"replay": "../backend/main"}).status_code == 404
