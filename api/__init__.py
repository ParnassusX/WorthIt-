# Initialize API package
from .main import app
from .errors import register_exception_handlers
from .db_init import init_db

__version__ = "0.1.0"