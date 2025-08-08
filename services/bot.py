# services/bot.py
from __future__ import annotations
import os, difflib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =================== Config ===================
OPEN_TRIPMAP_KEY = (os.getenv("OPEN_TRIPMAP_KEY") or "").strip()
OTM_BASE = "https://api.opentripmap.com/0.1/en/places"

# =================== HTTP session ===================
_session = requests.Session()
_session.headers.update({"User-Agent": "TripMate/1.0 (contact@example.com)"})
_retries = Retry(total=3, backoff_factor=0.4, status_forcelist=(500, 502, 503, 504))
_session.mount("https://", HTTPAdapter(max_retries=_retries))
_session.mount("http://", HTTPAdapter(max_retries=_retries))

# =================== States ===================
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

ALIASES = {
    "ny": "new york", "nj": "new jersey", "nm": "new mexico",
    "ca": "california", "az": "arizona", "tx": "texas", "fl": "florida",
    "wa": "washington", "pa": "pennsylvania", "va": "virginia", "wv": "west virginia",
    "nc": "north carolina", "nd": "north dakota", "sc": "south carolina", "sd": "south dakota",
    "cali": "california", "mass": "massachusetts", "miss": "mississippi",
    "newyork": "new york", "newyorkstate": "new york",
}

def _fmt_list(items: list[str]) -> str:
    return "\n".join(f"• {x}" for x in items)

def _normalize_token(s: str) -> str:
    t = s.strip().lower().replace(".", "").replace(",", "")
    c = t.replace(" ", "")
    return ALIASES.get(c, t)

def is_state(text: str) -> str | None:
    if not text:
        return None
    s = _normalize_token(text)

    # exact first
    if s in US_STATES:
        return s

    # scan tokens
    for w in s.split():
        w2 = _normalize_token(w)
        if w2 in US_STATES:
            return w2
        if w2 in ALIASES and ALIASES[w2] in US_STATES:
            return ALIASES[w2]

    # fuzzy whole-string (typos)
    m = difflib.get_close_matches(s, US_STATES, n=1, cutoff=0.82)
    return m[0] if m else None

# =================== OpenTripMap helpers ===================

def _otm_geoname(state: str) -> tuple[float, float] | None:
    """Use OTM to get the lat/lon for the state name."""
    if not OPEN_TRIPMAP_KEY:
        return None
    try:
        r = _session.get(
            f"{OTM_BASE}/geoname",
            params={"name": state, "apikey": OPEN_TRIPMAP_KEY},
            timeout=8,
        )
        if r.status_code != 200:
            return None
        d = r.json()
        if "lat" in d and "lon" in d:
            return float(d["lat"]), float(d["lon"])
        return None
    except Exception:
        return None

def _radius_names(lat: float, lon: float, *, radius_km: int, limit: int,
                  kinds: str | None, min_rate: int | None) -> list[str]:
    """Call OTM /radius and return a clean list of place names."""
    if not OPEN_TRIPMAP_KEY:
        return []
    try:
        params = {
            "apikey": OPEN_TRIPMAP_KEY,
            "lat": lat, "lon": lon,
            "radius": radius_km * 1000,
            "limit": limit,
            "format": "json",
        }
        # OTM uses min_rate (1..3) as a filter; some old docs show 'rate'
        if min_rate is not None:
            params["min_rate"] = min_rate
        if kinds:
            params["kinds"] = kinds

        r = _session.get(f"{OTM_BASE}/radius", params=params, timeout=10)
        if r.status_code != 200:
            return []
        out = []
        for row in r.json():
            name = (row or {}).get("name")
            if name:
                # drop ultra-generic items
                if name.lower() in {"unnamed", "viewpoint", "park"}:
                    continue
                if name not in out:
                    out.append(name)
        return out
    except Exception:
        return []

def otm_search_in_state(state: str) -> list[str]:
    """Try a couple of passes: tighter → broader, until we get names."""
    coords = _otm_geoname(state)
    if not coords:
        return []
    lat, lon = coords

    # Try progressively broader searches
    for radius, min_rate, kinds in [
        (200, 3, "natural,interesting_places,parks,museums,historic,architecture"),
        (300, 2, "natural,interesting_places,parks,museums,historic,architecture,beaches"),
        (450, 1, None),  # wide open if needed
    ]:
        names = _radius_names(lat, lon, radius_km=radius, limit=30, kinds=kinds, min_rate=min_rate)
        # keep the ones with decent names; shorten list
        names = [n for n in names if len(n) >= 3][:12]
        if names:
            return names
    return []

# =================== Public Chat ===================

def chat_reply(message: str, session_id: str = "") -> dict:
    """
    Chat that ONLY discusses U.S. states. Returns:
      { "message": str, "suggestions": [str, ...] }
    """
    state = is_state(message)
    if not state:
        # Strict: steer user to say a state
        return {
            "message": (
                "I’m your U.S. state trip buddy. Tell me a state like **Arizona**, **New York**, or **Texas**, "
                "and I’ll suggest great places to visit."
            ),
            "suggestions": ["Arizona", "California", "New York", "Texas", "Florida"],
        }

    # Live pull (if key present)
    names = otm_search_in_state(state) if OPEN_TRIPMAP_KEY else []
    if names:
        top = names[:8]
        return {
            "message": (
                f"Nice pick — **{state.title()}** has some gems. Here are a few ideas:\n\n{_fmt_list(top)}\n\n"
                "Ask for any of them and I’ll share a quick blurb and map link."
            ),
            "suggestions": top[:5],
        }

    # No key or no results
    if not OPEN_TRIPMAP_KEY:
        tip = "I don’t have a live attractions key set up on the server yet."
    else:
        tip = "I couldn’t find enough attractions just now (API may be rate-limited)."

    return {
        "message": (
            f"Hmm — I’m having trouble fetching live attractions for **{state.title()}** right now. {tip}\n\n"
            "Want to try another state?"
        ),
        "suggestions": ["California", "Florida", "Utah", "Washington"],
    }
