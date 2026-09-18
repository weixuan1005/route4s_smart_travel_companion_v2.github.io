"""
Small LTA DataMall client. The AccountKey is read from the environment (.env), never from code.

Notes from the PS2 brief:
  * base URL https://datamall2.mytransport.sg/ltaodataservice/<endpoint>, AccountKey header
  * results page 500 rows at a time via $skip
  * PCDRealTime refreshes every 10 min, PCDForecast once a day, TrainServiceAlerts ad hoc
Responses are cached in memory so the app never hammers the API.
"""
import os
import time

import httpx

# DATAMALL_BASE is only for tests against a fake server
BASE = os.getenv("DATAMALL_BASE", "https://datamall2.mytransport.sg/ltaodataservice/")
_cache = {}


class NoKey(RuntimeError):
    pass


def has_key():
    return bool(os.getenv("LTA_ACCOUNT_KEY"))


async def get(endpoint, params=None, ttl=60):
    key = os.getenv("LTA_ACCOUNT_KEY")
    if not key:
        raise NoKey("LTA_ACCOUNT_KEY is not set in .env")
    cache_key = (endpoint, tuple(sorted((params or {}).items())))
    hit = _cache.get(cache_key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(BASE + endpoint, params=params, headers={"AccountKey": key, "accept": "application/json"})
        r.raise_for_status()
        data = r.json()
    _cache[cache_key] = (time.time(), data)
    return data
