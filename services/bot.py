# services/bot.py
from __future__ import annotations

import os
import re
import difflib
import requests
from typing import Optional, Tuple, Dict, Any, List
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Reuse your destinations helpers so we’re not duplicating logic
from services.destinations import (
    get_place_details,
    get_destinations_with_details,
    get_top_destinations_by_state,
)

# ---------- HTTP session with retries ----------
_session = requests.Session()
_session.headers.update({"User-Agent": "TripMate/1.0 (contact@example.com)"})
_retries = Retry(total=3, backoff_factor=0.3, status_forcelist=(500, 502, 503, 504))
_session.mount("https://", HTTPAdapter(max_retries=_retries))
_session.mount("http://", HTTPAdapter(max_retries=_retries))

# ---------- Optional OpenTripMap (for richer state results if you add a key) ----------
OPEN_TRIPMAP_KEY = os.getenv("OPEN_TRIPMAP_KEY", "")
OTM_BASE = "https://api.opentripmap.com/0.1/en/places"
GEOCODE_URL = "https://nominatim.openstreetmap.org/search"

# ---------- Basic knowledge ----------
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
US_STATES_SET = set(US_STATES)

GREETINGS = {"hi", "hello", "hey", "hola", "yo", "howdy", "namaste"}

# =========================================================
# Small helpers
# =========================================================
def _title(s: str) -> str:
    return (s or "").strip().title()

def is_greeting(q: str) -> bool:
    return (q or "").strip().lower() in GREETINGS

def geocode_place(q: str) -> Optional[Tuple[float, float]]:
    """Geocode with Nominatim (no key). Returns (lat, lon) or None."""
    try:
        r = _session.get(
            GEOCODE_URL,
            params={"q": q, "format": "json", "limit": 1},
            timeout=8,
        )
        r.raise_for_status()
        arr = r.json()
        if not arr:
            return None
        return float(arr[0]["lat"]), float(arr[0]["lon"])
    except Exception:
        return None

def otm_search_in_state(state: str, limit: int = 15) -> List[str]:
    """If you have OPEN_TRIPMAP_KEY, fetch top places around the state's centroid."""
    if not OPEN_TRIPMAP_KEY:
        return []
    coords = geocode_place(f"{state}, USA")
    if not coords:
        return []
    lat, lon = coords
    try:
        r = _session.get(
            f"{OTM_BASE}/radius",
            params={
                "apikey": OPEN_TRIPMAP_KEY,
                "radius": 200000,  # ~200km
                "lat": lat,
                "lon": lon,
                "kinds": "interesting_places,natural,parks,museums,historic",
                "rate": 2,
                "limit": limit,
                "format": "json",
            },
            timeout=10,
        )
        r.raise_for_status()
        names: List[str] = []
        for row in r.json():
            name = (row or {}).get("name")
            if name:
                names.append(name)
        return names
    except Exception:
        return []

def is_state_name(q: str) -> Optional[str]:
    """Detect a US state (case-insensitive, with fuzzy match)."""
    s = (q or "").strip().lower()
    if not s:
        return None

    # avoid greeting 'hi' getting confused with Hawaii
    if s in GREETINGS:
        return None

    if s in US_STATES_SET:
        return s

    match = difflib.get_close_matches(s, US_STATES, n=1, cutoff=0.88)
    return match[0] if match else None

def parse_focus_intent(q: str) -> Tuple[Optional[str], str]:
    """
    Extract simple intents:
      - 'best time to visit X'  -> ('best_time', X)
      - 'things to do in X'     -> ('things', X)
    Returns (focus, cleaned_place)
    """
    text = (q or "").strip()
    m = re.search(r"best\s+time\s+to\s+visit\s+(.+)", text, flags=re.I)
    if m:
        return ("best_time", m.group(1).strip())

    m = re.search(r"(things|what\s+to\s+do)\s+in\s+(.+)", text, flags=re.I)
    if m:
        return ("things", m.group(2).strip())

    return (None, text)

# =========================================================
# Response builders
# =========================================================
def state_response(state_raw: str) -> Dict[str, Any]:
    state = state_raw.strip().lower()

    # 1) Try your detailed helper (uses wiki etc.)
    detailed = get_destinations_with_details(state)
    if detailed:
        top_names = [d["name"] for d in detailed][:10]
        msg = f"Here are a few great spots in {_title(state)}:\n- " + "\n- ".join(top_names)
        return {
            "message": msg,
            "suggestions": [f"Things to do in {top_names[0]}", f"Best time to visit {_title(state)}"] if top_names else [],
        }

    # 2) Fallback to simple names (your seed list)
    simple = get_top_destinations_by_state(state)
    if simple:
        msg = f"Here are some popular places in {_title(state)}:\n- " + "\n- ".join(simple[:10])
        return {
            "message": msg,
            "suggestions": [f"Tell me about {simple[0]}"] if simple else [],
        }

    # 3) Optional: OpenTripMap if key provided
    otm = otm_search_in_state(state)
    if otm:
        msg = f"Top attractions I found in {_title(state)}:\n- " + "\n- ".join(otm[:10])
        return {"message": msg, "suggestions": [f"Tell me about {otm[0]}"]}

    # 4) Nothing found
    return {
        "message": f"I couldn’t fetch attractions for {_title(state)} right now.",
        "suggestions": ["Try a city or a famous place name"],
    }

def place_response(place_raw: str, focus: Optional[str] = None) -> Dict[str, Any]:
    """
    Build a conversational reply for a place.
    focus:
        None        -> general summary
        'best_time' -> emphasize best time
        'things'    -> emphasize activities
    """
    name = _title(place_raw)
    data = get_place_details(name) or {}
    summary = data.get("summary")
    best_time = data.get("best_time")
    activities = data.get("activities") or []
    maps_url = data.get("maps_url")
    weather = data.get("weather")

    # Build message
    parts: List[str] = []

    if focus == "best_time" and best_time:
        parts.append(f"Best time to visit {name}: {best_time}.")
    elif focus == "things" and activities:
        parts.append(f"Things to do in {name}: " + ", ".join(activities) + ".")
    elif summary:
        parts.append(summary)
    else:
        parts.append(f"{name} is a notable destination.")

    if weather:
        parts.append(weather)
    if maps_url:
        parts.append(f"Map: {maps_url}")

    # Suggestions
    sug: List[str] = []
    if focus != "best_time":
        sug.append(f"Best time to visit {name}")
    if focus != "things":
        sug.append(f"Things to do in {name}")

    return {"message": "\n\n".join(parts), "suggestions": sug[:3]}

# =========================================================
# Public entry point used by /chat
# =========================================================
def chat_reply(message: str, session_id: str = "") -> Dict[str, Any]:
    """
    Very small intent router. Returns:
      {"message": "...", "suggestions": [...]}
    """
    text = (message or "").strip()
    if not text:
        return {"message": "Tell me a US state, city, or landmark and I’ll help plan.", "suggestions": ["Arizona", "Sedona", "Yosemite"]}

    # Friendly greetings
    if is_greeting(text):
        return {
            "message": "Hey! Tell me a US state, city, or famous place — I’ll suggest highlights and tips.",
            "suggestions": ["Arizona", "Sedona", "Best time to visit Grand Canyon"],
        }

    # “best time to … / things to do …” intents
    focus, cleaned = parse_focus_intent(text)
    if cleaned:
        # If the cleaned text itself is a state name (and no focus), show state list
        state = is_state_name(cleaned)
        if state and focus is None:
            return state_response(state)
        # else treat as a place with focus
        return place_response(cleaned, focus=focus)

    # Pure state request
    state = is_state_name(text)
    if state:
        return state_response(state)

    # Fallback → treat as place
    return place_response(text)
