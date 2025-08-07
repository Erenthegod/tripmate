from flask import jsonify, request
from . import tripmate_bp
from .destinations import get_destinations

@tripmate_bp.route("/api/destinations/<state>", methods=["GET"])
def destinations(state):
    """
    API endpoint to get attractions for a given state.
    Example: GET /api/destinations/Arizona
    """
    data = get_destinations(state)
    return jsonify({
        "state": state,
        "destinations": data
    })
