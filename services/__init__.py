from flask import Blueprint

# Create a blueprint for all tripmate services
tripmate_bp = Blueprint('tripmate', __name__)

# Import routes so they register with the blueprint
from . import routes
