from fastapi import HTTPException, Request, Depends
from fastapi.security import APIKeyHeader
import re
from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict

# Simple in-memory rate limiting
REQUEST_LIMITS = defaultdict(list)
MAX_REQUESTS = 100  # Maximum requests per window
TIME_WINDOW = 3600  # Time window in seconds (1 hour)

def validate_url(url: str) -> bool:
    """Validate if the URL is from a supported marketplace"""
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")
    
    # Validate URL format and supported marketplaces
    valid_domains = r'^https?://([a-z0-9\.-]+\.)?(amazon|ebay)\.(it|com|co\.uk|de|fr|es|in|ca|com\.au|com\.br|nl|pl|se|sg)'
    if not re.match(valid_domains, url, re.IGNORECASE):
        raise HTTPException(
            status_code=400,
            detail="URL not supported. Please provide a valid Amazon or eBay URL."
        )
    
    return True

async def rate_limiter(request: Request):
    """Simple in-memory rate limiter"""
    client_ip = request.client.host
    now = datetime.now()
    
    # Remove old requests
    REQUEST_LIMITS[client_ip] = [
        req_time for req_time in REQUEST_LIMITS[client_ip]
        if now - req_time < timedelta(seconds=TIME_WINDOW)
    ]
    
    # Check if limit exceeded
    if len(REQUEST_LIMITS[client_ip]) >= MAX_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {MAX_REQUESTS} requests per hour."
        )
    
    # Add current request
    REQUEST_LIMITS[client_ip].append(now)

# API Key security
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: Optional[str] = Depends(API_KEY_HEADER)):
    """Verify API key if present"""
    if api_key:
        # In a production environment, you would validate against a database
        # For now, we'll accept any non-empty API key
        return api_key
    return None

# Security middleware dependencies
async def security_dependencies(request: Request, api_key: Optional[str] = Depends(verify_api_key)):
    """Combine all security checks"""
    await rate_limiter(request)
    return True