# API module initialization
# This file ensures the api package is properly importable

# Import key components for easier access
from . import errors
from . import validation
from . import scraper
from . import ml_processor

__version__ = "0.1.0"

# Import app after other modules to avoid circular imports
def get_app():
    from .main import app
    return app