# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS

# your modules
from services.destinations import (
    get_top_destinations_by_state,
    get_destinations_with_details,
    get_place_details,
    search_places,
)
from services.bot import chat_reply

import requests
import os

app = Flask(__name__)

# Allow calls from APEX (add other origins if you’ll test elsewhere)
CORS(app, resources={r"/*": {"origins": ["https://apex.oracle.com"]}})


@app.get("/")
def home():
    return jsonify({
        "message": "Welcome to TripMate API",
        "available_endpoints": {
            "/health": "Check API health",
            "/version": "Commit hash (Render) & feature flags",
            "/diag": "Connectivity checks (wiki, nominatim, key presence)",
            "/search?q=Sedona": "Fuzzy search places",
            "/destinations?state=Arizona": "Top destinations for a state",
            "/destinations_full?state=Arizona": "Destinations + compact details",
            "/place?name=Sedona": "Details for a place",
            "/chat": "POST {message, session_id} to chat"
        }
    }), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.get("/version")
def version():
    return jsonify({
        "app": "tripmate",
        "commit": os.getenv("RENDER_GIT_COMMIT") or "dev",
        "has_search": True
    }), 200


@app.get("/diag")
def diag():
    """Lightweight diagnostics to debug Render/network issues."""
    out = {"ok": True, "OPEN_TRIPMAP_KEY": bool(os.getenv("OPEN_TRIPMAP_KEY"))}
    try:
        r = requests.get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/Sedona",
            timeout=5
        )
        out["wiki_ok"] = (r.status_code == 200)
    except Exception as e:
        out["wiki_ok"] = False
        out["wiki_err"] = str(e)

    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": "Arizona, USA", "format": "json", "limit": 1},
            headers={"User-Agent": "TripMate/1.0"},
            timeout=5
        )
        out["nominatim_ok"] = (r.status_code == 200)
    except Exception as e:
        out["nominatim_ok"] = False
        out["nominatim_err"] = str(e)

    return jsonify(out), 200


@app.post("/chat")
def chat():
    """Chat endpoint used by APEX. Never throws HTML; always JSON."""
    try:
        data = request.get_json(silent=True) or {}
        message = (data.get("message") or "").strip()
        session_id = (data.get("session_id") or "guest").strip()

        if not message:
            return jsonify({"message": "Ask me about a state or a place."}), 200

        resp = chat_reply(message, session_id=session_id)
        # chat_reply should return a dict like {"message": "...", "suggestions": [...]}
        if not isinstance(resp, dict):
            resp = {"message": str(resp)}
        return jsonify(resp), 200

    except Exception as e:
        app.logger.exception("chat() failed")
        return jsonify({"error": "server_error", "detail": str(e)}), 500


@app.get("/search")
def search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"results": []}), 200
    return jsonify({"results": search_places(q)}), 200


@app.get("/destinations")
def destinations():
    state = (request.args.get("state") or "").strip()
    if not state:
        return jsonify({"error": "Missing required query param: state"}), 400
    results = get_top_destinations_by_state(state)
    return jsonify({"state": state, "destinations": results}), 200


@app.get("/destinations_full")
def destinations_full():
    state = (request.args.get("state") or "").strip()
    if not state:
        return jsonify({"error": "Missing required query param: state"}), 400
    return jsonify({
        "state": state,
        "results": get_destinations_with_details(state)
    }), 200


@app.get("/place")
def place():
    name = (request.args.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Missing required query param: name"}), 400
    data = get_place_details(name)
    if not data:
        return jsonify({"error": f"No details found for {name}"}), 404
    return jsonify(data), 200


if __name__ == "__main__":
    # Local dev only; Render runs via gunicorn
    app.run(host="0.0.0.0", port=5000, debug=True)
