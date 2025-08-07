import os
import requests

WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"

# Minimal seed data for MVP. Expand later or replace with live sources.
STATE_TO_DESTINATIONS = {
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

# Simple heuristic suggestions for best time & activities (extend or replace with AI)
DEFAULT_ACTIVITIES = {
    "Sedona": ["Hiking", "Jeep tours", "Photography"],
    "Grand Canyon": ["Hiking", "Rim viewpoints", "Rafting"],
    "Antelope Canyon": ["Photography", "Guided tours"],
    "Flagstaff": ["Skiing (winter)", "Hiking", "Lowell Observatory"],
}

DEFAULT_BEST_TIME = {
    "Sedona": "March–May, Sep–Nov",
    "Grand Canyon": "March–May, Sep–Nov",
    "Antelope Canyon": "March–Oct",
    "Flagstaff": "Year-round; skiing Dec–Mar",
}

def wiki_summary(title: str) -> str | None:
    try:
        resp = requests.get(WIKI_SUMMARY_URL.format(requests.utils.quote(title)), timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # Prefer 'extract' if present, else 'description'
            return data.get("extract") or data.get("description")
    except Exception:
        pass
    return None

def get_top_destinations_by_state(state: str) -> list[str]:
    key = (state or "").strip().lower()
    return STATE_TO_DESTINATIONS.get(key, [])

def get_place_details(name: str) -> dict | None:
    name = (name or "").strip()
    if not name:
        return None

    # Try to get a short summary from Wikipedia
    summary = wiki_summary(name)

    # Attach defaults if available
    best_time = DEFAULT_BEST_TIME.get(name)
    activities = DEFAULT_ACTIVITIES.get(name, [])

    # If nothing found, still return basic structure
    return {
        "name": name,
        "summary": summary or f"{name} is a notable destination. More details coming soon.",
        "best_time": best_time or "Varies by season; spring and fall are often ideal.",
        "activities": activities or ["Sightseeing", "Local tours", "Photography"],
    }
