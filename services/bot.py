# services/bot.py
from __future__ import annotations
import os, re, difflib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OPEN_TRIPMAP_KEY = os.getenv("OPEN_TRIPMAP_KEY", "")  # set in Render
OTM_BASE = "https://api.opentripmap.com/0.1/en/places"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
GEOCODE = "https://nominatim.openstreetmap.org/search"  # user-agent required

_session = requests.Session()
_retries = Retry(total=3, backoff_factor=0.3, status_forcelist=(500,502,503,504))
_session.mount("https://", HTTPAdapter(max_retries=_retries))
_session.headers.update({"User-Agent": "TripMate/1.0 (contact@example.com)"})

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

def is_state(q: str) -> str | None:
    s = q.strip().lower()
    if s in US_STATES: return s
    # fuzzy match
    m = difflib.get_close_matches(s, US_STATES, n=1, cutoff=0.85)
    return m[0] if m else None

def geocode_place(q: str) -> tuple[float,float] | None:
    try:
        r = _session.get(GEOCODE, params={"q": q, "format": "json", "limit": 1})
        r.raise_for_status()
        arr = r.json()
        if not arr: return None
        return float(arr[0]["lat"]), float(arr[0]["lon"])
    except Exception:
        return None

def otm_search_in_state(state: str, limit: int = 15) -> list[dict]:
    """Try to center roughly on the state name via geocode, then radius search."""
    if not OPEN_TRIPMAP_KEY:
        return []
    coords = geocode_place(f"{state}, USA")
    if not coords:
        return []
    lat, lon = coords
    try:
        # radius in meters (200km)
        r = _session.get(
            f"{OTM_BASE}/radius",
            params={
                "apikey": OPEN_TRIPMAP_KEY,
                "radius": 200000,
                "lat": lat,
                "lon": lon,
                "kinds": "interesting_places,natural,parks,museums,historic",
                "rate": 2,      # higher rated
                "limit": limit,
                "format": "json"
            }
        )
        r.raise_for_status()
        out = []
        for row in r.json():
            name = row.get("name")
            if not name: continue
            out.append({"name": name, "lat": row.get("point",{}).get("lat"),
                        "lon": row.get("point",{}).get("lon")})
        return out
    except Exception:
        return []

def wiki_enrich(title: str) -> dict:
    try:
        r = _session.get(WIKI_SUMMARY.format(requests.utils.quote(title)), timeout=8)
        if r.status_code != 200:
            return {}
        d = r.json()
        return {
            "summary": d.get("extract") or d.get("description"),
            "image_url": (d.get("thumbnail") or {}).get("source"),
            "coords": (d.get("coordinates") or None),
        }
    except Exception:
        return {}

def weather_brief(lat: float, lon: float) -> str | None:
    try:
        r = _session.get("https://api.open-meteo.com/v1/forecast",
                         params={"latitude": lat, "longitude": lon,
                                 "daily":"temperature_2m_max,temperature_2m_min,weathercode",
                                 "forecast_days": 3, "timezone":"auto"}, timeout=8)
        if r.status_code != 200: return None
        d = r.json().get("daily",{})
        tmax = d.get("temperature_2m_max",[None])[0]
        tmin = d.get("temperature_2m_min",[None])[0]
        if tmax is None or tmin is None: return None
        return f"This weekend: {round(tmax)}°/{round(tmin)}°."
    except Exception:
        return None

def places_for_state(state: str) -> dict:
    rows = otm_search_in_state(state)
    if not rows:
        return {"message": f"I couldn’t fetch attractions for {state.title()} right now.",
                "suggestions": ["Try a city or a famous place name"]}
    names = [r["name"] for r in rows if r.get("name")]
    msg = f"Top places in {state.title()}:\n- " + "\n- ".join(names[:10])
    return {"message": msg, "suggestions": names[:5]}

def details_for_place(name: str) -> dict:
    info = wiki_enrich(name)
    # coordinates: try from wiki first, else geocode
    lat = lon = None
    if info.get("coords"):
        lat = info["coords"].get("lat"); lon = info["coords"].get("lon")
    if lat is None or lon is None:
        gl = geocode_place(name)
        if gl: lat, lon = gl
    wx = weather_brief(lat, lon) if (lat is not None and lon is not None) else None

    chunks = []
    if info.get("summary"): chunks.append(info["summary"])
    if wx: chunks.append(wx)
    chunks.append(f"Maps: https://www.google.com/maps/search/?api=1&query={requests.utils.quote(name)}")

    return {
        "message": "\n\n".join(chunks) or f"{name} is a notable destination.",
        "suggestions": ["Best time to visit " + name, "Things to do in " + name]
    }

def chat_reply(message: str, session_id: str="") -> dict:
    # very light intent router
    s = is_state(message)
    if s:
        return places_for_state(s)
    # if prompt looks like “tell me about X” or just a place, go to details
    m = re.sub(r'^(tell me about|info on|details about)\s+', '', message.strip(), flags=re.I)
    return details_for_place(m)
