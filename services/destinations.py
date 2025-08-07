# services/destinations.py
from __future__ import annotations

import requests
from datetime import datetime, timedelta

# put near the top of destinations.py
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# session with retries
_session = requests.Session()
_retries = Retry(total=3, backoff_factor=0.3, status_forcelist=(500, 502, 503, 504))
_session.mount("https://", HTTPAdapter(max_retries=_retries))
_session.mount("http://", HTTPAdapter(max_retries=_retries))


WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"

# --- Minimal seed data for MVP. Expand later or replace with live sources. ---
STATE_TO_DESTINATIONS: dict[str, list[str]] = {
    "arizona": [
        "Grand Canyon",
        "Sedona",
        "Antelope Canyon",
        "Flagstaff",
        "Horseshoe Bend",
        "Page",
        "Monument Valley",
        "Petrified Forest National Park",
    ],
    "california": [
        "Yosemite National Park",
        "San Francisco",
        "Los Angeles",
        "Lake Tahoe",
        "Big Sur",
        "San Diego",
        "Death Valley National Park",
    ],
    "new york": [
        "New York City",
        "Niagara Falls",
        "Adirondack Mountains",
        "Finger Lakes",
        "Buffalo",
        "Saratoga Springs",
    ],
}

# --- Simple heuristic defaults (extend/replace later with smarter logic) ---
DEFAULT_ACTIVITIES: dict[str, list[str]] = {
    "Sedona": ["Hiking", "Jeep tours", "Photography"],
    "Grand Canyon": ["Hiking", "Rim viewpoints", "Rafting"],
    "Antelope Canyon": ["Photography", "Guided tours"],
    "Flagstaff": ["Skiing (winter)", "Hiking", "Lowell Observatory"],
}

DEFAULT_BEST_TIME: dict[str, str] = {
    "Sedona": "March–May, Sep–Nov",
    "Grand Canyon": "March–May, Sep–Nov",
    "Antelope Canyon": "March–Oct",
    "Flagstaff": "Year-round; skiing Dec–Mar",
}

# --- In-memory cache for place details (very lightweight) ---
_CACHE: dict[str, dict] = {}
_TTL = timedelta(hours=24)


def wiki_summary(title: str) -> str | None:
    """Fetch a short summary for a place from Wikipedia."""
    if not title:
        return None
    try:
        url = WIKI_SUMMARY_URL.format(requests.utils.quote(title))
        resp = _session.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # Prefer 'extract' if present, else 'description'
            return data.get("extract") or data.get("description")
    except Exception:
        # Silently ignore network/JSON errors for resiliency
        pass
    return None


def get_top_destinations_by_state(state: str) -> list[str]:
    """Return a list of destination names for a given state (case-insensitive)."""
    key = (state or "").strip().lower()
    return STATE_TO_DESTINATIONS.get(key, [])


def get_place_details(name: str) -> dict | None:
    """Return details for a specific place."""
    name = (name or "").strip()
    if not name:
        return None

    # Pull a short summary from Wikipedia (best-effort)
    summary = wiki_summary(name)

    # Attach simple defaults if available
    best_time = DEFAULT_BEST_TIME.get(name) or "Varies by season; spring and fall are often ideal."
    activities = DEFAULT_ACTIVITIES.get(name, ["Sightseeing", "Local tours", "Photography"])

    return {
        "name": name,
        "summary": summary or f"{name} is a notable destination. More details coming soon.",
        "best_time": best_time,
        "activities": activities,
    }


def get_destinations(state: str) -> list[str]:
    """Alias kept for compatibility with earlier imports."""
    return get_top_destinations_by_state(state)


# ----------------------- Lightweight caching helpers ----------------------- #
def _cache_key(name: str) -> str:
    return (name or "").strip().lower()


def _cache_get(name: str) -> dict | None:
    key = _cache_key(name)
    entry = _CACHE.get(key)
    if not entry:
        return None
    if datetime.utcnow() - entry["ts"] > _TTL:
        _CACHE.pop(key, None)
        return None
    return entry["data"]


def _cache_set(name: str, data: dict) -> None:
    key = _cache_key(name)
    _CACHE[key] = {"data": data, "ts": datetime.utcnow()}


def get_place_details_cached(name: str) -> dict | None:
    """Cached variant of get_place_details to reduce repeat Wikipedia calls."""
    hit = _cache_get(name)
    if hit:
        return hit
    data = get_place_details(name)
    if data:
        _cache_set(name, data)
    return data


def get_destinations_with_details(state: str) -> list[dict]:
    """
    Return compact detail objects for each destination in the given state:
    [
      { "name": ..., "summary": ..., "best_time": ..., "activities": [...] },
      ...
    ]
    """
    places = get_top_destinations_by_state(state)
    results: list[dict] = []
    for place in places:
        details = get_place_details_cached(place)
        if details:
            results.append(
                {
                    "name": details["name"],
                    "summary": details["summary"],
                    "best_time": details["best_time"],
                    "activities": details["activities"],
                }
            )
    return results


__all__ = [
    "get_top_destinations_by_state",
    "get_place_details",
    "get_destinations",
    "get_place_details_cached",
    "get_destinations_with_details",
]
