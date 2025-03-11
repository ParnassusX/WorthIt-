"""Authentication utilities for WorthIt! API."""

import os
import logging
from typing import Dict, Optional, Any
from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import OAuth2PasswordBearer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# In a real application, this would validate JWT tokens or session cookies
async def get_current_user(request: Request, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """
    Get the current authenticated user from the request.
    
    In a production environment, this would validate JWT tokens or session cookies.
    For testing and development, it returns a mock user.
    
    Args:
        request: The FastAPI request object
        authorization: The Authorization header value
        
    Returns:
        Dict containing user information
        
    Raises:
        HTTPException: If authentication fails
    """
    # Check if we're in test mode
    if os.getenv("TEST_MODE") == "1":
        # Return a mock user for testing
        return {
            "id": "test_user_123",
            "email": "test@example.com",
            "subscription_tier": "basic"
        }
    
    # In production, validate the token
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    try:
        # Extract the token from the Authorization header
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication scheme",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # In a real application, validate the token and get the user
        # For now, return a mock user
        return {
            "id": "user_123",
            "email": "user@example.com",
            "subscription_tier": "basic"
        }
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )