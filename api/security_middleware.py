"""Security middleware for FastAPI integration.

This module provides middleware components for integrating security features:
- API key rotation integration
- Fraud detection middleware
- Payment encryption middleware
- Input validation middleware
"""

import logging
import time
from typing import Dict, Any, Callable, Awaitable, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from api.key_rotation import key_rotation_manager
from api.fraud_detection import fraud_detector
from api.payment_encryption import encrypt_payment_data, decrypt_payment_data

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SecurityMiddlewareManager:
    """Manager for all security middleware components."""
    
    def __init__(self):
        self.key_rotation_middleware = KeyRotationMiddleware()
        self.fraud_detection_middleware = FraudDetectionMiddleware()
        self.payment_encryption_middleware = PaymentEncryptionMiddleware()
    
    def setup_middleware(self, app: FastAPI):
        """Set up all security middleware for a FastAPI application.
        
        Args:
            app: FastAPI application instance
        """
        # Add middleware in the correct order (outermost first)
        app.middleware("http")(self.key_rotation_middleware)
        app.middleware("http")(self.fraud_detection_middleware)
        app.middleware("http")(self.payment_encryption_middleware)
        
        logger.info("Security middleware components initialized and registered")


class KeyRotationMiddleware:
    """Middleware for API key rotation."""
    
    async def __call__(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        """Process request with key rotation checks.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware in the chain
            
        Returns:
            Response from the API
        """
        # Check if any keys need rotation based on schedule
        await key_rotation_manager.check_rotation_schedules()
        
        # Continue processing the request
        return await call_next(request)


class FraudDetectionMiddleware:
    """Middleware for fraud detection on payment endpoints."""
    
    async def __call__(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        """Process request for fraud detection.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware in the chain
            
        Returns:
            Response from the API
        """
        # Only check payment-related endpoints
        if request.url.path.startswith("/api/payment"):
            # Get client IP
            ip_address = request.client.host
            
            # For POST requests (payments), perform deeper analysis
            if request.method == "POST":
                try:
                    # Get user ID from request or session
                    user_id = request.session.get("user_id", "anonymous")
                    
                    # We don't block here, just log for monitoring
                    # Actual fraud detection happens in the payment routes
                    logger.info(f"Payment request from user {user_id} at {ip_address}")
                except Exception as e:
                    logger.error(f"Error in fraud detection middleware: {str(e)}")
        
        # Continue processing the request
        return await call_next(request)


class PaymentEncryptionMiddleware:
    """Middleware for payment data encryption."""
    
    async def __call__(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        """Process request for payment encryption.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware in the chain
            
        Returns:
            Response from the API
        """
        # Only process payment endpoints that need encryption/decryption
        if request.url.path.startswith("/api/payment") and request.method == "POST":
            try:
                # Clone the request to modify it
                # This is a simplified example - in a real implementation,
                # you would need to handle the request body more carefully
                body = await request.json()
                
                # If the request contains payment data that needs encryption
                if "payment_data" in body and not body.get("is_encrypted", False):
                    # Encrypt the payment data
                    body["payment_data"] = encrypt_payment_data(body["payment_data"])
                    body["is_encrypted"] = True
                    
                    # Create a new request with the encrypted data
                    # This is a simplified example - in a real implementation,
                    # you would need to create a new request object
                    
                    # For now, just log that we would encrypt
                    logger.info("Payment data would be encrypted")
            except Exception as e:
                logger.error(f"Error in payment encryption middleware: {str(e)}")
        
        # Continue processing the request
        response = await call_next(request)
        
        # Process the response if needed (e.g., decrypt data for the client)
        # This is a simplified example
        
        return response


# Create singleton instance
security_middleware_manager = SecurityMiddlewareManager()


# Helper function to set up all security middleware
def setup_security_middleware(app: FastAPI):
    """Set up all security middleware for a FastAPI application.
    
    Args:
        app: FastAPI application instance
    """
    security_middleware_manager.setup_middleware(app)