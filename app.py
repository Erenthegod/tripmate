# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from services.destinations import (
    get_top_destinations_by_state,
    get_destinations_with_details,
    get_place_details,
    search_places,
)

from services.bot import chat_reply

app = Flask(__name__)
# Restrict CORS to APEX (adjust if you’ll call from elsewhere)
CORS(app, resources={r"/*": {"origins": ["https://apex.oracle.com"]}})



@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    session_id = (data.get("session_id") or "").strip()
    if not message:
        return jsonify({"message": "Ask me about a state or a place."}), 200
    ans = chat_reply(message, session_id=session_id)
    return jsonify(ans), 200



@app.get("/")
def home():
    """Root route to display API info."""
    return jsonify({
        "message": "Welcome to TripMate API",
        "available_endpoints": {
            "/health": "Check API health",
            "/search?q=Sedona": "Fuzzy search places",
            "/destinations?state=Arizona": "Get top destinations for a given state",
            "/destinations_full?state=Arizona": "Destinations + compact details",
            "/place?name=Sedona": "Details for a place (summary, image, maps, weather)"
        }
    }), 200


@app.get("/version")
def version():
    # Render sets RENDER_GIT_COMMIT automatically; fine if None locally
    import os
    return jsonify({
        "app": "tripmate",
        "commit": os.getenv("RENDER_GIT_COMMIT") or "dev",
        "has_search": True,
    }), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.get("/search")
def search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"results": []}), 200
    return jsonify({"results": search_places(q)}), 200


@app.get("/destinations")
def destinations():
    """
    GET /destinations?state=Arizona
    Returns top destinations (names only) for a given US state.
    """
    state = (request.args.get("state") or "").strip()
    if not state:
        return jsonify({"error": "Missing required query param: state"}), 400
    results = get_top_destinations_by_state(state)
    return jsonify({"state": state, "destinations": results}), 200


@app.get("/destinations_full")
def destinations_full():
    """
    GET /destinations_full?state=Arizona
    Returns a compact details array for each destination in a state.
    """
    state = (request.args.get("state") or "").strip()
    if not state:
        return jsonify({"error": "Missing required query param: state"}), 400
    return jsonify({"state": state, "results": get_destinations_with_details(state)}), 200


@app.get("/place")
def place():
    """
    GET /place?name=Sedona
    Returns details for a given place (summary, best_time, activities, image_url?, maps_url, weather?).
    """
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
