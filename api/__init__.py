# Initialize API package
from .errors import register_exception_handlers

__version__ = "0.1.0"

# Import app after other modules to avoid circular imports
def get_app():
    from .main import app
    return app