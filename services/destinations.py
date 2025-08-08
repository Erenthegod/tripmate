# services/destinations.py
from __future__ import annotations
import time
from .bot import US_STATES, otm_search_in_state

# Simple in-memory cache: { state: (timestamp, [places]) }
_CACHE: dict[str, tuple[float, list[str]]] = {}
_CACHE_TTL = 60 * 60 * 6  # 6 hours

def get_top_places(state: str, limit: int = 12) -> list[str]:
    """
    Get top attractions for a US state.
    Dynamically calls OpenTripMap from bot.py and caches results.
    """
    s = state.strip().lower()
    if s not in US_STATES:
        return []

    now = time.time()

    # Return from cache if valid
    if s in _CACHE:
        ts, data = _CACHE[s]
        if now - ts < _CACHE_TTL:
            return data[:limit]

    # Pull fresh data
    places = otm_search_in_state(s)
    _CACHE[s] = (now, places)
    return places[:limit]

def get_all_states_with_places(limit: int = 12) -> dict[str, list[str]]:
    """
    Returns {state: [top places]} for all US states dynamically.
    """
    result = {}
    for state in US_STATES:
        result[state.title()] = get_top_places(state, limit=limit)
    return result
