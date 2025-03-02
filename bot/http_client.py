import httpx
import asyncio
from typing import Optional

# Initialize a shared httpx client with proper connection pool settings
_http_client = None

def get_http_client():
    """Get or create a shared httpx client with proper connection pool settings"""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=10.0,  # Reduced timeout
            limits=httpx.Limits(
                max_keepalive_connections=5,  # Reduced from 20
                max_connections=10,  # Reduced from 50
                keepalive_expiry=5.0  # Added expiry time
            ),
            http2=False
        )
    return _http_client

async def close_http_client():
    """Close the shared httpx client to free resources"""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None