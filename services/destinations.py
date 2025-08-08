# services/destinations.py
from __future__ import annotations
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OPEN_TRIPMAP_KEY = os.getenv("OPEN_TRIPMAP_KEY", "").strip()
OTM_BASE = "https://api.opentripmap.com/0.1/en/places"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
GEOCODE_URL = "https://nominatim.openstreetmap.org/search"

# HTTP session with retries + UA
_session = requests.Session()
_session.headers.update({"User-Agent": "TripMate/1.0 (support@example.com)"})
_retries = Retry(total=3, backoff_factor=0.4, status_forcelist=(500, 502, 503, 504))
_session.mount("https://", HTTPAdapter(max_retries=_retries))
_session.mount("http://", HTTPAdapter(max_retries=_retries))


def _geocode_place(q: str) -> tuple[float, float] | None:
    try:
        r = _session.get(GEOCODE_URL, params={"q": f"{q}, USA", "format": "json", "limit": 1}, timeout=8)
        r.raise_for_status()
        arr = r.json()
        if not arr:
            return None
        return float(arr[0]["lat"]), float(arr[0]["lon"])
    except Exception:
        return None


def _otm_radius_names(lat: float, lon: float, limit: int = 20, radius_km: int = 250) -> list[str]:
    """Return a list of unique attraction names around a lat/lon from OpenTripMap."""
    if not OPEN_TRIPMAP_KEY:
        return []
    try:
        r = _session.get(
            f"{OTM_BASE}/radius",
            params={
                "apikey": OPEN_TRIPMAP_KEY,
                "lat": lat,
                "lon": lon,
                "radius": radius_km * 1000,
                "limit": limit,
                "rate": 2,  # better-rated
                "kinds": "natural,interesting_places,parks,beaches,museums,historic,architecture",
                "format": "json",
            },
            timeout=12,
        )
        r.raise_for_status()
        names: list[str] = []
        for row in r.json():
            name = (row or {}).get("name")
            if name and name not in names:
                names.append(name)
        return names
    except Exception:
        return []


def _wiki_enrich(title: str) -> dict:
    try:
        r = _session.get(WIKI_SUMMARY.format(requests.utils.quote(title)), timeout=8)
        if r.status_code != 200:
            return {}
        d = r.json()
        return {
            "summary": d.get("extract") or d.get("description"),
            "image_url": (d.get("thumbnail") or {}).get("source"),
        }
    except Exception:
        return {}


# ---------------- Public API used by app.py ---------------- #

def get_top_destinations_by_state(state: str, limit: int = 14) -> list[str]:
    """Return top attraction names for a US state (live via OTM if key present)."""
    coords = _geocode_place(state)
    if not coords:
        return []
    lat, lon = coords
    return _otm_radius_names(lat, lon, limit=limit)


def get_destinations_with_details(state: str, limit: int = 10) -> list[dict]:
    """
    Return compact details for each destination:
    [{ name, summary?, image_url? }]
    """
    names = get_top_destinations_by_state(state, limit=limit)
    out: list[dict] = []
    for n in names:
        info = _wiki_enrich(n)
        out.append({
            "name": n,
            "summary": info.get("summary"),
            "image_url": info.get("image_url"),
        })
    return out


def get_place_details(name: str) -> dict | None:
    """
    Return detailed info for a place:
    { name, summary?, image_url?, maps_url }
    """
    if not name:
        return None
    info = _wiki_enrich(name)
    data = {
        "name": name,
        "summary": info.get("summary"),
        "image_url": info.get("image_url"),
        "maps_url": f"https://www.google.com/maps/search/?api=1&query={requests.utils.quote(name)}",
    }
    # if nothing at all, still return minimal structure
    return data


def search_places(q: str, limit: int = 10) -> list[str]:
    """Lightweight text search using OTM autosuggest if key present, else []"""
    if not q:
        return []
    if not OPEN_TRIPMAP_KEY:
        return []

    try:
        r = _session.get(
            f"{OTM_BASE}/autosuggest",
            params={"apikey": OPEN_TRIPMAP_KEY, "name": q, "limit": limit, "format": "json"},
            timeout=8,
        )
        r.raise_for_status()
        names: list[str] = []
        for row in r.json():
            name = (row or {}).get("name")
            if name and name not in names:
                names.append(name)
        return names
    except Exception:
        return []


# ---------- Back-compat aliases so older imports won’t crash ---------- #
def get_top_places(state: str, limit: int = 14) -> list[str]:
    return get_top_destinations_by_state(state, limit=limit)


def get_destinations(state: str, limit: int = 14) -> list[str]:
    return get_top_destinations_by_state(state, limit=limit)
