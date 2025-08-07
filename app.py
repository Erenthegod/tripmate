from flask import Flask, request, jsonify
from flask_cors import CORS
from services.destinations import get_top_destinations_by_state, get_place_details

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["https://apex.oracle.com"]}})


@app.get("/")
def home():
    """
    Root route to display API info.
    """
    return jsonify({
        "message": "Welcome to TripMate API",
        "available_endpoints": {
            "/health": "Check API health",
            "/destinations?state=Arizona": "Get top destinations for a given US state",
            "/place?name=Sedona": "Get details for a specific place"
        }
    }), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.get("/destinations")
def destinations():
    """
    GET /destinations?state=Arizona
    Returns top destinations (names only) for a given US state.
    """
    state = request.args.get("state")
    if not state:
        return jsonify({"error": "Missing required query param: state"}), 400
    results = get_top_destinations_by_state(state.strip().lower())
    return jsonify({"state": state, "destinations": results}), 200


@app.get("/place")
def place():
    """
    GET /place?name=Sedona
    Returns details for a given place (summary, best_time, activities).
    """
    name = request.args.get("name")
    if not name:
        return jsonify({"error": "Missing required query param: name"}), 400
    data = get_place_details(name.strip())
    if not data:
        return jsonify({"error": f"No details found for {name}"}), 404
    return jsonify(data), 200


if __name__ == "__main__":
    # Run locally: python app.py
    app.run(host="0.0.0.0", port=5000, debug=True)
