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
# allow APEX
CORS(app, resources={r"/*": {"origins": ["https://apex.oracle.com"]}})

@app.get("/")
def home():
    return jsonify({
        "message": "Welcome to TripMate API",
        "available_endpoints": {
            "/health": "Check API health",
            "/search?q=Sedona": "Fuzzy search places",
            "/destinations?state=Arizona": "Get top destinations for a state",
            "/destinations_full?state=Arizona": "Destinations + compact details",
            "/place?name=Sedona": "Details for a place",
            "/chat": "POST {message, session_id} to chat"
        }
    }), 200

@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    session_id = (data.get("session_id") or "guest").strip()
    if not message:
        return jsonify({"error": "empty message"}), 400
    # chat_reply returns {"reply": "...", ...}
    return jsonify(chat_reply(message, session_id=session_id)), 200

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
    app.run(host="0.0.0.0", port=5000, debug=True)
