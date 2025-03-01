from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging
import asyncio

# Configure logging
logger = logging.getLogger(__name__)

# Custom exception classes
class ScrapingError(HTTPException):
    """Exception raised when scraping services are unavailable"""
    def __init__(self, detail="Scraping service temporarily unavailable"):
        super().__init__(status_code=503, detail=detail)

class RateLimitError(HTTPException):
    """Exception raised when rate limit is exceeded"""
    def __init__(self, detail="Rate limit exceeded"):
        super().__init__(status_code=429, detail=detail)

class ProductNotFoundError(HTTPException):
    """Exception raised when product is not found"""
    def __init__(self, detail="Product not found"):
        super().__init__(status_code=404, detail=detail)

# Error handlers
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors"""
    logger.error(f"Validation error: {exc}")
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "detail": exc.errors()
        }
    )

async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    logger.error(f"HTTP error {exc.status_code}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )

async def generic_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )

# Function to register all exception handlers
def register_exception_handlers(app):
    """Register all exception handlers with the FastAPI app"""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)