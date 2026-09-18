"""Place search and street legs, with OneMap and OSRM replaced by fakes."""
import pytest
from fastapi.testclient import TestClient

from backend import geo
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_cache():
    geo._cache.clear()


def test_geocode_parses_onemap(monkeypatch):
    async def fake(url, params=None, headers=None, timeout=8):
        assert params["searchVal"] == "fusionopolis"
        return {"found": 1, "results": [{"SEARCHVAL": "FUSIONOPOLIS ONE", "ADDRESS": "1 FUSIONOPOLIS WAY SINGAPORE 138632",
                                         "LATITUDE": "1.29913", "LONGITUDE": "103.78790"}, {"SEARCHVAL": "BAD"}]}
    monkeypatch.setattr(geo, "_fetch_json", fake)
    r = client.get("/api/geocode", params={"q": "fusionopolis"}).json()
    assert r["source"] == "onemap" and len(r["results"]) == 1
    assert r["results"][0]["name"] == "Fusionopolis One" and abs(r["results"][0]["lat"] - 1.29913) < 1e-6


def test_geocode_failure_is_reported(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(geo, "_fetch_json", boom)
    r = client.get("/api/geocode", params={"q": "punggol"}).json()
    assert r["source"] == "unavailable" and r["results"] == []


def test_route_uses_osrm(monkeypatch):
    monkeypatch.setenv("OSRM_BIKE_URL", "http://osrm-bike:5000")
    async def fake(url, params=None, headers=None, timeout=8):
        assert url == "http://osrm-bike:5000/route/v1/bicycle/103.8965,1.4102;103.8985,1.4085"
        return {"code": "Ok", "routes": [{"distance": 412.3, "duration": 101.6,
                "geometry": {"type": "LineString", "coordinates": [[103.8965, 1.4102], [103.8975, 1.4095], [103.8985, 1.4085]]}}]}
    monkeypatch.setattr(geo, "_fetch_json", fake)
    r = client.get("/api/route", params={"mode": "bike", "from": "1.4102,103.8965", "to": "1.4085,103.8985"}).json()
    assert r["source"] == "osrm" and r["duration_s"] == 102 and r["geometry"][1] == [1.4095, 103.8975]


def test_route_falls_back_to_labelled_estimate(monkeypatch):
    monkeypatch.setenv("OSRM_FOOT_URL", "http://nowhere:5000")
    async def boom(*a, **k):
        raise ConnectionError()
    monkeypatch.setattr(geo, "_fetch_json", boom)
    r = client.get("/api/route", params={"mode": "foot", "from": "1.2991,103.7876", "to": "1.2996,103.7872"}).json()
    assert r["source"] == "estimate" and "OSRM unavailable" in r["note"] and r["duration_s"] > 0


def test_route_validation():
    assert client.get("/api/route", params={"mode": "car", "from": "1.3,103.8", "to": "1.3,103.9"}).status_code == 422
    assert client.get("/api/route", params={"mode": "foot", "from": "40.7,-74.0", "to": "1.3,103.9"}).status_code == 400
    assert client.get("/api/route", params={"mode": "foot", "from": "abc", "to": "1.3,103.9"}).status_code == 400
