# app.py
from __future__ import annotations

import os
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS

from services.destinations import (
    get_top_places as get_top_destinations_by_state,
    get_destinations_with_details,
    get_place_details,
    search_places,
)
from services.bot import chat_reply

app = Flask(__name__)

# Allow calls from APEX. Add more origins if needed.
CORS(app, resources={r"/*": {"origins": ["https://apex.oracle.com"]}})


@app.get("/")
def home():
    return jsonify({
        "message": "Welcome to TripMate API",
        "available_endpoints": {
            "/health": "Check API health",
            "/diag": "Run outbound call diagnostics",
            "/search?q=Sedona": "Fuzzy search places",
            "/destinations?state=Arizona": "Top destinations for a state",
            "/destinations_full?state=Arizona": "Destinations + compact details",
            "/place?name=Sedona": "Details for a place",
            "/chat": "POST {message, session_id} to chat"
        }
    }), 200


@app.get("/version")
def version():
    return jsonify({
        "app": "tripmate",
        "commit": os.getenv("RENDER_GIT_COMMIT") or "dev",
    }), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.get("/diag")
def diag():
    """Quick diagnostics to verify outbound APIs & env."""
    import requests
    out = {"ok": True, "checks": {}}

    try:
        w = requests.get("https://en.wikipedia.org/api/rest_v1/page/summary/Sedona", timeout=6)
        out["checks"]["wiki_ok"] = (w.status_code == 200)
        if not out["checks"]["wiki_ok"]:
            out["ok"] = False
            out["checks"]["wiki_status"] = w.status_code
    except Exception as e:
        out["ok"] = False
        out["checks"]["wiki_ok"] = False
        out["checks"]["wiki_err"] = str(e)

    try:
        n = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": "Sedona", "format": "json", "limit": 1},
            headers={"User-Agent": "TripMate/1.0 (support@example.com)"},
            timeout=6
        )
        out["checks"]["nominatim_ok"] = (n.status_code == 200)
        if not out["checks"]["nominatim_ok"]:
            out["ok"] = False
            out["checks"]["nominatim_status"] = n.status_code
    except Exception as e:
        out["ok"] = False
        out["checks"]["nominatim_ok"] = False
        out["checks"]["nominatim_err"] = str(e)

    out["checks"]["opentripmap_key_present"] = bool(os.getenv("OPEN_TRIPMAP_KEY"))
    return jsonify(out), 200


@app.post("/chat")
def chat():
    """Chat endpoint consumed by APEX."""
    try:
        data = request.get_json(silent=True) or {}
        message = (data.get("message") or "").strip()
        session_id = (data.get("session_id") or "guest").strip()
        if not message:
            return jsonify({"error": "empty_message"}), 400

        ans = chat_reply(message, session_id=session_id)  # dict with "message", "suggestions" etc.
        return jsonify(ans), 200

    except Exception as e:
        app.logger.exception("chat error")
        return jsonify({
            "error": "server_error",
            "detail": str(e),
            "trace": traceback.format_exc()
        }), 500


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
    return jsonify({"state": state, "results": get_destinations_with_details(state)}), 200


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
    # Local dev only; Render uses gunicorn
    app.run(host="0.0.0.0", port=5000, debug=True)
