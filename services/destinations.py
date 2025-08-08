import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===== Config =====
OPEN_TRIPMAP_KEY = os.getenv("OPEN_TRIPMAP_KEY", "").strip()
OTM_BASE = "https://api.opentripmap.com/0.1/en/places"
GEOCODE_URL = "https://nominatim.openstreetmap.org/search"

# ===== HTTP session with retries =====
_session = requests.Session()
_session.headers.update({"User-Agent": "TripMate/1.0 (support@example.com)"})
_retries = Retry(total=3, backoff_factor=0.4, status_forcelist=(500, 502, 503, 504))
_session.mount("https://", HTTPAdapter(max_retries=_retries))
_session.mount("http://", HTTPAdapter(max_retries=_retries))

# ===== US States =====
US_STATES = [
    "alabama","alaska","arizona","arkansas","california","colorado","connecticut",
    "delaware","florida","georgia","hawaii","idaho","illinois","indiana","iowa",
    "kansas","kentucky","louisiana","maine","maryland","massachusetts","michigan",
    "minnesota","mississippi","missouri","montana","nebraska","nevada","new hampshire",
    "new jersey","new mexico","new york","north carolina","north dakota","ohio",
    "oklahoma","oregon","pennsylvania","rhode island","south carolina","south dakota",
    "tennessee","texas","utah","vermont","virginia","washington","west virginia",
    "wisconsin","wyoming"
]

# ===== Helper functions =====
def _geocode_place(q: str):
    try:
        r = _session.get(GEOCODE_URL, params={"q": f"{q}, USA", "format": "json", "limit": 1}, timeout=8)
        r.raise_for_status()
        arr = r.json()
        if not arr:
            return None
        return float(arr[0]["lat"]), float(arr[0]["lon"])
    except Exception:
        return None

def _otm_search(lat: float, lon: float, limit: int = 12, radius_km: int = 250):
    try:
        r = _session.get(
            f"{OTM_BASE}/radius",
            params={
                "apikey": OPEN_TRIPMAP_KEY,
                "lat": lat,
                "lon": lon,
                "radius": radius_km * 1000,
                "limit": limit,
                "rate": 2,
                "kinds": "natural,interesting_places,parks,beaches,museums,historic,architecture",
                "format": "json",
            },
            timeout=10,
        )
        r.raise_for_status()
        names = []
        for row in r.json():
            name = (row or {}).get("name")
            if name and name not in names:
                names.append(name)
        return names
    except Exception:
        return []

# ===== Main public function =====
def get_top_places(state: str, limit: int = 12):
    """
    Get top attractions for a given US state using OpenTripMap.
    Falls back to empty list if API key not set or fails.
    """
    if not OPEN_TRIPMAP_KEY:
        return []

    coords = _geocode_place(state)
    if not coords:
        return []
    lat, lon = coords
    return _otm_search(lat, lon, limit)

# ===== Alias for backward compatibility =====
def get_top_destinations_by_state(state: str, limit: int = 12):
    """
    Backward compatibility for old code expecting get_top_destinations_by_state.
    """
    return get_top_places(state, limit)
