# services/destinations.py
from __future__ import annotations

import os
import time
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =========================
# Config & HTTP Session
# =========================
OPEN_TRIPMAP_KEY = os.getenv("OPEN_TRIPMAP_KEY", "").strip()
OTM_BASE = "https://api.opentripmap.com/0.1/en/places"
GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

_session = requests.Session()
_session.headers.update({"User-Agent": "TripMate/1.1 (support@example.com)"})
_retries = Retry(total=3, backoff_factor=0.4, status_forcelist=(500, 502, 503, 504))
_session.mount("https://", HTTPAdapter(max_retries=_retries))
_session.mount("http://", HTTPAdapter(max_retries=_retries))

# =========================
# Lightweight Caches
# =========================
# Per-process in-memory caches; OK for Render free services
_geo_cache: Dict[str, Tuple[float, float, float]] = {}  # key -> (lat, lon, ts)
_dest_cache: Dict[str, Tuple[List[str], float]] = {}     # state -> (names, ts)
_place_cache: Dict[str, Tuple[Dict, float]] = {}         # place -> (details, ts)

TTL_GEO = 24 * 3600       # 24h
TTL_DEST = 3600           # 1h
TTL_PLACE = 24 * 3600     # 24h


def _now() -> float:
    return time.time()


def _cache_get(cache: dict, key: str, ttl: int):
    row = cache.get(key)
    if not row:
        return None
    value, ts = row[0], row[1]
    if _now() - ts > ttl:
        cache.pop(key, None)
        return None
    return value


def _cache_set(cache: dict, key: str, value):
    cache[key] = (value, _now())


# =========================
# Helpers
# =========================
def _require_otm() -> bool:
    return bool(OPEN_TRIPMAP_KEY)


def geocode_place(q: str) -> Optional[Tuple[float, float]]:
    """
    Geocode with Nominatim (free). We add a small cache to avoid hammering it.
    """
    if not q:
        return None
    k = f"geo::{q.lower().strip()}"
    hit = _cache_get(_geo_cache, k, TTL_GEO)
    if hit:
        return hit

    try:
        r = _session.get(
            GEOCODE_URL,
            params={"q": f"{q}, USA", "format": "json", "limit": 1},
            timeout=8,
        )
        r.raise_for_status()
        arr = r.json()
        if not arr:
            return None
        lat, lon = float(arr[0]["lat"]), float(arr[0]["lon"])
        _cache_set(_geo_cache, k, (lat, lon))
        return lat, lon
    except Exception:
        return None


def otm_radius_names(lat: float, lon: float, limit: int = 20, radius_km: int = 250) -> List[str]:
    """
    Query OpenTripMap /radius around lat/lon and return unique place names.
    """
    if not _require_otm():
        return []

    try:
        r = _session.get(
            f"{OTM_BASE}/radius",
            params={
                "apikey": OPEN_TRIPMAP_KEY,
                "lat": lat,
                "lon": lon,
                "radius": radius_km * 1000,  # meters
                "limit": limit,
                "rate": 2,  # prioritize higher-rated places
                "kinds": "natural,interesting_places,parks,beaches,museums,historic,architecture",
                "format": "json",
            },
            timeout=12,
        )
        r.raise_for_status()
        names: List[str] = []
        for row in r.json():
            name = (row or {}).get("name")
            if name and name not in names:
                names.append(name)
        return names
    except Exception:
        return []


def otm_autosuggest(query: str, limit: int = 10) -> List[str]:
    """
    Search names using OpenTripMap autosuggest.
    """
    if not _require_otm() or not query:
        return []
    try:
        r = _session.get(
            f"{OTM_BASE}/autosuggest",
            params={"apikey": OPEN_TRIPMAP_KEY, "name": query, "limit": limit},
            timeout=10,
        )
        r.raise_for_status()
        out: List[str] = []
        for it in r.json():
            name = (it or {}).get("name")
            if name and name not in out:
                out.append(name)
        return out
    except Exception:
        return []


def wiki_enrich(title: str) -> Dict:
    """
    Return {summary, image_url, lat?, lon?} from Wikipedia summary endpoint.
    """
    if not title:
        return {}
    try:
        url = WIKI_SUMMARY_URL.format(requests.utils.quote(title))
        resp = _session.get(url, timeout=8)
        if resp.status_code != 200:
            return {}
        d = resp.json()
        return {
            "summary": d.get("extract") or d.get("description"),
            "image_url": (d.get("thumbnail") or {}).get("source"),
            "lat": (d.get("coordinates") or {}).get("lat"),
            "lon": (d.get("coordinates") or {}).get("lon"),
        }
    except Exception:
        return {}


def weather_brief(lat: float, lon: float) -> Optional[str]:
    """
    Tiny 3-day snapshot using Open-Meteo. Returns a single-line weekend brief.
    """
    try:
        r = _session.get(
            OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,weathercode",
                "forecast_days": 3,
                "timezone": "auto",
            },
            timeout=8,
        )
        if r.status_code != 200:
            return None
        d = r.json().get("daily", {})
        tmax = d.get("temperature_2m_max") or []
        tmin = d.get("temperature_2m_min") or []
        if not (tmax and tmin):
            return None
        return f"This weekend: {round(tmax[0])}°/{round(tmin[0])}°."
    except Exception:
        return None


# =========================
# Public API (used by app.py)
# =========================
def get_top_destinations_by_state(state: str) -> List[str]:
    """
    LIVE: returns top place names for a US state via OpenTripMap (no hardcoding).
    Fallback: [] if API/key fails.
    """
    key = (state or "").strip()
    if not key:
        return []

    # cache
    ck = f"dest::{key.lower()}"
    hit = _cache_get(_dest_cache, ck, TTL_DEST)
    if hit is not None:
        return hit

    coords = geocode_place(key)
    if not coords:
        _cache_set(_dest_cache, ck, [])
        return []
    lat, lon = coords

    names = otm_radius_names(lat, lon, limit=24, radius_km=300)
    _cache_set(_dest_cache, ck, names)
    return names


def get_place_details(name: str) -> Optional[Dict]:
    """
    LIVE: returns details for a place using Wikipedia + Open-Meteo.
    Shape:
      {
        "name": str,
        "summary": str,
        "best_time": str | None,
        "activities": list[str],
        "image_url": str | None,
        "maps_url": str,
        "weather": str | None
      }
    """
    title = (name or "").strip()
    if not title:
        return None

    # cache
    ck = f"place::{title.lower()}"
    hit = _cache_get(_place_cache, ck, TTL_PLACE)
    if hit:
        return hit

    enriched = wiki_enrich(title) or {}
    lat = enriched.get("lat")
    lon = enriched.get("lon")
    if lat is None or lon is None:
        geo = geocode_place(title)
        if geo:
            lat, lon = geo

    wx = weather_brief(lat, lon) if (lat is not None and lon is not None) else None

    details = {
        "name": title,
        "summary": enriched.get("summary") or f"{title} is a notable destination.",
        "best_time": None,  # we’re not hardcoding; leave None
        "activities": [],   # no hardcoding; callers can omit/ignore if empty
        "image_url": enriched.get("image_url"),
        "maps_url": f"https://www.google.com/maps/search/?api=1&query={requests.utils.quote(title)}",
        "weather": wx,
    }
    _cache_set(_place_cache, ck, details)
    return details


def search_places(query: str, limit: int = 8) -> List[str]:
    """
    LIVE: uses OpenTripMap autosuggest to return place names.
    """
    q = (query or "").strip()
    if not q:
        return []
    return otm_autosuggest(q, limit=limit)


def get_place_details_cached(name: str) -> Optional[Dict]:
    """
    Thin caching wrapper; kept for compatibility with older code paths.
    """
    return get_place_details(name)


def get_destinations_with_details(state: str) -> List[Dict]:
    """
    LIVE: For a given state, return compact detail objects for each destination:
      [
        { "name": ..., "summary": ..., "best_time": ..., "activities": [...] },
        ...
      ]
    """
    names = get_top_destinations_by_state(state)
    out: List[Dict] = []
    for n in names:
        d = get_place_details(n)
        if d:
            out.append(
                {
                    "name": d["name"],
                    "summary": d.get("summary"),
                    "best_time": d.get("best_time"),
                    "activities": d.get("activities") or [],
                }
            )
    return out


# ---------------------------
# Backward-compat alias
# ---------------------------
def get_destinations(state: str) -> List[str]:
    """
    Deprecated alias for older modules that import get_destinations.
    """
    return get_top_destinations_by_state(state)


__all__ = [
    "get_top_destinations_by_state",
    "get_destinations_with_details",
    "get_place_details",
    "search_places",
    "get_place_details_cached",
    "get_destinations",  # back-compat
]
