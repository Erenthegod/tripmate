# services/bot.py
from __future__ import annotations
import os
import difflib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===== Config =====
OPEN_TRIPMAP_KEY = os.getenv("OPEN_TRIPMAP_KEY", "").strip()
OTM_BASE = "https://api.opentripmap.com/0.1/en/places"
GEOCODE_URL = "https://nominatim.openstreetmap.org/search"

# ===== HTTP session with retries & UA =====
_session = requests.Session()
_session.headers.update({"User-Agent": "TripMate/1.0 (support@example.com)"})
_retries = Retry(total=3, backoff_factor=0.4, status_forcelist=(500, 502, 503, 504))
_session.mount("https://", HTTPAdapter(max_retries=_retries))
_session.mount("http://", HTTPAdapter(max_retries=_retries))

# ===== US State list =====
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

STATE_ALIASES = {
    # common short forms people type
    "cali": "california",
    "wash": "washington",
    "mass": "massachusetts",
    "miss": "mississippi",
    "newyork": "new york",
    "newyorkstate": "new york",
    "ny": "new york",
    "nj": "new jersey",
    "nm": "new mexico",
    "ca": "california",
    "az": "arizona",
    "tx": "texas",
    "fl": "florida",
    "wa": "washington",
    "pa": "pennsylvania",
    "va": "virginia",
    "wv": "west virginia",
    "nc": "north carolina",
    "nd": "north dakota",
    "sc": "south carolina",
    "sd": "south dakota",
}

def _format_list(items: list[str], bullet: str = "•") -> str:
    return "\n".join(f"{bullet} {x}" for x in items)

def _normalize_state_token(s: str) -> str:
    t = s.strip().lower().replace(".", "").replace(",", "")
    # collapse spaces for stuff like “newyork”
    t_compact = t.replace(" ", "")
    if t_compact in STATE_ALIASES:
        return STATE_ALIASES[t_compact]
    return t

def is_state(text: str) -> str | None:
    """Return a normalized US state name or None."""
    if not text:
        return None
    s = _normalize_state_token(text)

    # exact
    if s in US_STATES:
        return s

    # try to extract a token that is a state
    # (e.g., “tell me about arizona please”)
    words = [w for w in s.split() if w.isalpha()]
    for w in words:
        w2 = _normalize_state_token(w)
        if w2 in US_STATES:
            return w2
        if w2 in STATE_ALIASES:
            alias = STATE_ALIASES[w2]
            if alias in US_STATES:
                return alias

    # fuzzy match on the full string (helps “Californi” / “Massachusets” typos)
    match = difflib.get_close_matches(s, US_STATES, n=1, cutoff=0.82)
    if match:
        return match[0]

    return None

def geocode_place(q: str) -> tuple[float, float] | None:
    try:
        r = _session.get(GEOCODE_URL, params={"q": f"{q}, USA", "format": "json", "limit": 1}, timeout=8)
        r.raise_for_status()
        arr = r.json()
        if not arr:
            return None
        return float(arr[0]["lat"]), float(arr[0]["lon"])
    except Exception:
        return None

def otm_search_in_state(state: str, limit: int = 14, radius_km: int = 250) -> list[str]:
    """Search OpenTripMap around the state's centroid (via geocode)."""
    if not OPEN_TRIPMAP_KEY:
        return []

    coords = geocode_place(state)
    if not coords:
        return []
    lat, lon = coords

    try:
        r = _session.get(
            f"{OTM_BASE}/radius",
            params={
                "apikey": OPEN_TRIPMAP_KEY,
                "lat": lat,
                "lon": lon,
                "radius": radius_km * 1000,  # meters
                "limit": limit,
                "rate": 2,  # filter to higher rated
                "kinds": "natural,interesting_places,parks,beaches,museums,historic,architecture",
                "format": "json",
            },
            timeout=10,
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

# -------------------- Public Chat Entry -------------------- #
def chat_reply(message: str, session_id: str = "") -> dict:
    """
    Humanized chat that ONLY responds to US states.
    Returns:
      { "message": str, "suggestions": [str, ...] }
    """
    state = is_state(message)
    if not state:
        # Strict: only states allowed
        return {
            "message": (
                "I can help with **US states** only.\n\n"
                "Tell me a state like *Arizona*, *New York*, or *Texas* and I’ll suggest top places to visit."
            ),
            "suggestions": ["Arizona", "California", "New York", "Texas", "Florida"],
        }

    # Live pull via OpenTripMap when key is configured
    names = otm_search_in_state(state)
    if names:
        top = names[:8]
        msg = (
            f"Nice choice — **{state.title()}** has some great spots! Here are a few to check out:\n\n"
            f"{_format_list(top)}\n\n"
            "Tap one to see details, best time to visit, and a quick map link."
        )
        return {
            "message": msg,
            "suggestions": top[:5],
        }

    # Fallback when no key / API issue
    return {
        "message": (
            f"I’m having trouble pulling live attractions for **{state.title()}** right now.\n\n"
            "Mind trying another state? (Or add an OpenTripMap API key to enable live results.)"
        ),
        "suggestions": ["California", "Florida", "Utah", "Washington"],
    }
