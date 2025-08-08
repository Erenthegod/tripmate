# services/bot.py
from __future__ import annotations
import os, difflib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OPEN_TRIPMAP_KEY = (os.getenv("OPEN_TRIPMAP_KEY") or "").strip()
OTM_BASE = "https://api.opentripmap.com/0.1/en/places"

_session = requests.Session()
_session.headers.update({"User-Agent": "TripMate/1.0 (contact@example.com)"})
_retries = Retry(total=3, backoff_factor=0.4, status_forcelist=(500, 502, 503, 504))
_session.mount("https://", HTTPAdapter(max_retries=_retries))
_session.mount("http://", HTTPAdapter(max_retries=_retries))

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
    "ny":"new york","nj":"new jersey","nm":"new mexico","ca":"california","az":"arizona",
    "tx":"texas","fl":"florida","wa":"washington","pa":"pennsylvania","va":"virginia",
    "wv":"west virginia","nc":"north carolina","nd":"north dakota","sc":"south carolina",
    "sd":"south dakota","cali":"california","mass":"massachusetts","newyork":"new york",
    "newyorkstate":"new york",
}

# things we usually don’t want as “top attractions”
_BAD_WORDS = {"bank","office","company","building","courthouse","county","police"}
# kinds we DO want to bias toward
_GOOD_KINDS = {
    "natural","national_parks","beaches","water","waterfalls","lakes","caves",
    "mountains","geological_formations","protected_areas",
    "interesting_places","urban_environment",
    "cultural","museums","historic","monuments_and_memorials","architecture",
    "castles","fortifications","archaeology","amusements","theme_parks"
}
# initial kinds filter sent to OTM
KINDS_WHITELIST = ",".join(sorted(_GOOD_KINDS))

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
    if s in US_STATES:
        return s
    for w in s.split():
        w2 = _normalize_token(w)
        if w2 in US_STATES:
            return w2
        if w2 in ALIASES and ALIASES[w2] in US_STATES:
            return ALIASES[w2]
    m = difflib.get_close_matches(s, US_STATES, n=1, cutoff=0.82)
    return m[0] if m else None

def _otm_geoname(state: str) -> tuple[float, float] | None:
    if not OPEN_TRIPMAP_KEY:
        return None
    try:
        r = _session.get(f"{OTM_BASE}/geoname",
                         params={"name": state, "apikey": OPEN_TRIPMAP_KEY},
                         timeout=8)
        if r.status_code != 200:
            return None
        d = r.json()
        if "lat" in d and "lon" in d:
            return float(d["lat"]), float(d["lon"])
    except Exception:
        pass
    return None

def _score_row(row: dict) -> float:
    """Simple popularity score."""
    score = 0.0
    rate = row.get("rate") or 0
    score += 10 * float(rate)

    kinds = set((row.get("kinds") or "").split(","))
    if kinds & _GOOD_KINDS:
        score += 5

    if row.get("wikidata"):
        score += 4

    # light penalty for boring words
    name = (row.get("name") or "").lower()
    if any(b in name for b in _BAD_WORDS):
        score -= 8

    return score

def _clean_names(rows: list[dict], top: int) -> list[str]:
    # rank by score; keep unique names; drop super-short/empty
    rows = sorted(rows, key=_score_row, reverse=True)
    out, seen = [], set()
    for r in rows:
        n = (r.get("name") or "").strip()
        if len(n) < 3:
            continue
        if n.lower() in {"unnamed", "viewpoint"}:
            continue
        if n.lower() in seen:
            continue
        seen.add(n.lower())
        out.append(n)
        if len(out) == top:
            break
    return out

def _radius(lat: float, lon: float, *, radius_km: int, min_rate: int | None, kinds: str | None, limit: int) -> list[dict]:
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
        if kinds:
            params["kinds"] = kinds
        if min_rate is not None:
            params["min_rate"] = min_rate

        r = _session.get(f"{OTM_BASE}/radius", params=params, timeout=10)
        if r.status_code != 200:
            return []
        return r.json()
    except Exception:
        return []

def otm_search_in_state(state: str) -> list[str]:
    coords = _otm_geoname(state)
    if not coords:
        return []
    lat, lon = coords

    # Pass 1: tight, high-quality
    rows = _radius(lat, lon, radius_km=250, min_rate=3, kinds=KINDS_WHITELIST, limit=80)
    names = _clean_names(rows, top=12)
    if len(names) >= 8:
        return names

    # Pass 2: larger radius, allow rate>=2
    rows = _radius(lat, lon, radius_km=400, min_rate=2, kinds=KINDS_WHITELIST, limit=120)
    names = _clean_names(rows, top=12)
    if len(names) >= 6:
        return names

    # Pass 3: widest, minimal filter
    rows = _radius(lat, lon, radius_km=600, min_rate=1, kinds=None, limit=150)
    return _clean_names(rows, top=12)

def chat_reply(message: str, session_id: str = "") -> dict:
    state = is_state(message)
    if not state:
        return {
            "message": (
                "I’m your U.S. state trip buddy. Tell me a state like **Arizona**, **New York**, or **Texas**, "
                "and I’ll suggest great places to visit."
            ),
            "suggestions": ["Arizona", "California", "New York", "Texas", "Florida"],
        }

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

    tip = "I don’t have a live attractions key set up yet." if not OPEN_TRIPMAP_KEY \
          else "The API looks rate-limited or sparse right now."
    return {
        "message": (
            f"Hmm — I’m having trouble fetching live attractions for **{state.title()}**. {tip}\n\n"
            "Want to try another state?"
        ),
        "suggestions": ["California", "Florida", "Utah", "Washington"],
    }
