"""API Key Rotation Mechanism for WorthIt!

This module provides functionality for secure API key rotation, including:
- Scheduled key rotation for external API services
- Key versioning and expiration management
- Graceful transition between old and new keys
- Audit logging for key rotation events
"""

import logging
import os
import time
import json
import secrets
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import asyncio
from fastapi import HTTPException

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Key storage - in production, this should be in a secure database
# For this implementation, we'll use in-memory storage
API_KEYS = {
    # Format: "service_name": {"current": {"key": "value", "created": timestamp}, "previous": {...}}
}

# Default rotation settings
DEFAULT_ROTATION_INTERVAL = 30  # days
DEFAULT_OVERLAP_PERIOD = 2  # days

class KeyRotationManager:
    """Manages API key rotation for external services."""
    
    def __init__(self):
        """Initialize the key rotation manager."""
        self.rotation_schedules = {}
        self.last_rotation = {}
        self.rotation_lock = asyncio.Lock()
        
        # Load initial keys from environment
        self._load_initial_keys()
        
    def _load_initial_keys(self):
        """Load initial API keys from environment variables."""
        # Map of environment variable names to service names
        env_to_service = {
            "APIFY_TOKEN": "apify",
            "HF_TOKEN": "huggingface",
            "STRIPE_API_KEY": "stripe"
        }
        
        for env_name, service_name in env_to_service.items():
            key_value = os.getenv(env_name)
            if key_value:
                self._store_key(service_name, key_value)
                logger.info(f"Loaded initial key for {service_name}")
            else:
                logger.warning(f"No key found for {service_name} in environment variables")
    
    def _store_key(self, service: str, key_value: str):
        """Store a new API key for a service.
        
        Args:
            service: Name of the service
            key_value: The API key value
        """
        now = datetime.now().timestamp()
        
        if service in API_KEYS:
            # Move current key to previous
            API_KEYS[service]["previous"] = API_KEYS[service]["current"]
        else:
            API_KEYS[service] = {}
        
        # Store new key as current
        API_KEYS[service]["current"] = {
            "key": key_value,
            "created": now,
            "hash": hashlib.sha256(key_value.encode()).hexdigest()[:8]  # For logging (partial hash)
        }
        
        self.last_rotation[service] = now
    
    def get_key(self, service: str) -> str:
        """Get the current API key for a service.
        
        Args:
            service: Name of the service
            
        Returns:
            Current API key
            
        Raises:
            HTTPException: If no key is available for the service
        """
        if service not in API_KEYS or "current" not in API_KEYS[service]:
            logger.error(f"No API key available for {service}")
            raise HTTPException(status_code=500, detail=f"API key for {service} not configured")
        
        return API_KEYS[service]["current"]["key"]
    
    def get_previous_key(self, service: str) -> Optional[str]:
        """Get the previous API key for a service if available.
        
        Args:
            service: Name of the service
            
        Returns:
            Previous API key or None if not available
        """
        if service in API_KEYS and "previous" in API_KEYS[service]:
            return API_KEYS[service]["previous"]["key"]
        return None
    
    def set_rotation_schedule(self, service: str, interval_days: int = DEFAULT_ROTATION_INTERVAL,
                             overlap_days: int = DEFAULT_OVERLAP_PERIOD):
        """Set the rotation schedule for a service.
        
        Args:
            service: Name of the service
            interval_days: Number of days between rotations
            overlap_days: Number of days to keep the previous key valid
        """
        self.rotation_schedules[service] = {
            "interval": interval_days,
            "overlap": overlap_days
        }
        logger.info(f"Set rotation schedule for {service}: every {interval_days} days with {overlap_days} days overlap")
    
    async def rotate_key(self, service: str, new_key: str) -> bool:
        """Rotate the API key for a service.
        
        Args:
            service: Name of the service
            new_key: The new API key value
            
        Returns:
            True if rotation was successful
        """
        async with self.rotation_lock:
            try:
                # Store the new key
                self._store_key(service, new_key)
                
                # Log the rotation (with partial hash for security)
                key_hash = API_KEYS[service]["current"]["hash"]
                logger.info(f"Rotated API key for {service} (new key hash: {key_hash})")
                
                return True
            except Exception as e:
                logger.error(f"Error rotating key for {service}: {str(e)}")
                return False
    
    async def check_rotation_schedules(self):
        """Check if any keys need rotation based on schedules."""
        now = datetime.now().timestamp()
        
        for service, schedule in self.rotation_schedules.items():
            if service in self.last_rotation:
                last_rotation = self.last_rotation[service]
                interval_seconds = schedule["interval"] * 86400  # days to seconds
                
                if now - last_rotation > interval_seconds:
                    logger.info(f"Key rotation needed for {service} based on schedule")
                    # In a real implementation, this would trigger the key rotation process
                    # For example, by calling an external API or notifying administrators
    
    def is_key_valid(self, service: str, key: str) -> bool:
        """Check if a key is valid (either current or previous within overlap period).
        
        Args:
            service: Name of the service
            key: The API key to check
            
        Returns:
            True if the key is valid
        """
        if service not in API_KEYS:
            return False
        
        # Check if it matches the current key
        if API_KEYS[service]["current"]["key"] == key:
            return True
        
        # Check if it matches the previous key and is within overlap period
        if "previous" in API_KEYS[service]:
            previous = API_KEYS[service]["previous"]
            if previous["key"] == key:
                # Calculate if we're still in the overlap period
                if service in self.rotation_schedules:
                    overlap_seconds = self.rotation_schedules[service]["overlap"] * 86400  # days to seconds
                    current_created = API_KEYS[service]["current"]["created"]
                    now = datetime.now().timestamp()
                    
                    # If we're still within the overlap period from when the new key was created
                    if now - current_created < overlap_seconds:
                        return True
        
        return False

# Create a singleton instance
key_rotation_manager = KeyRotationManager()

# Example usage:
# key_rotation_manager.set_rotation_schedule("apify", 30, 2)  # Rotate every 30 days with 2 days overlap
# current_key = key_rotation_manager.get_key("apify")
# is_valid = key_rotation_manager.is_key_valid("apify", some_key)