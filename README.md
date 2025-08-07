# TripMate Starter (Python Flask API)

A minimal backend for your Trip Advisor Bot. It provides two endpoints:

- `GET /destinations?state=Arizona` → returns a list of top destinations for the state (seeded + extend it)
- `GET /place?name=Sedona` → returns details for a place: summary (via Wikipedia), best time, and activities

## Quickstart

1) Create a virtual environment and install deps
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2) Run the API
```bash
python app.py
# The server runs at http://127.0.0.1:5000
```

3) Test in a browser or Postman
```
http://127.0.0.1:5000/health
http://127.0.0.1:5000/destinations?state=Arizona
http://127.0.0.1:5000/place?name=Sedona
```

## Oracle APEX Integration (High-level)

1. Deploy or tunnel your Flask API so APEX can reach it (e.g., deploy on Render or use `ngrok` during development).
2. In APEX: **Shared Components → REST Data Sources → Create**:
   - URL (GET): `https://YOUR-API-URL/destinations?state=&PXX_STATE.`
   - Pagination: None
   - Authentication: None (dev) or Token (prod)
3. Add a page item `PXX_STATE` and a region that sources data from the REST Data Source.
4. For place details, create another REST data source:
   - `https://YOUR-API-URL/place?name=&PXX_PLACE.`

## Notes

- Wikipedia summaries are fetched using the public REST API.
- You can replace seed data with a more robust list or connect to an external travel API.
- To add OpenAI (optional), create a new service module and call the Chat API to enrich summaries.

## Next Steps

- Add caching for Wikipedia requests.
- Add OpenAI enrichment for activities and travel tips.
- Replace seed data with actual curated lists or scraped sources.
