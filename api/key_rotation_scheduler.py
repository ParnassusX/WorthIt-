"""API Key Rotation Scheduler for WorthIt!

This module implements the scheduled key rotation mechanism for external API services.
It provides functionality to automatically rotate API keys at specified intervals,
manage the transition between old and new keys, and maintain an audit log of key rotation events.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import os
import json

from api.key_rotation import KeyRotationManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KeyRotationScheduler:
    """Scheduler for automatic API key rotation."""
    
    def __init__(self, rotation_manager: KeyRotationManager = None):
        """Initialize the key rotation scheduler.
        
        Args:
            rotation_manager: An instance of KeyRotationManager
        """
        self.rotation_manager = rotation_manager or KeyRotationManager()
        self.running = False
        self.rotation_task = None
        self.rotation_intervals = {
            # Service name: days between rotations
            "apify": 30,
            "huggingface": 45,
            "stripe": 60
        }
        self.audit_log = []
        self.max_audit_log_entries = 1000
        
    async def start(self):
        """Start the key rotation scheduler."""
        if self.running:
            logger.warning("Key rotation scheduler is already running")
            return
            
        self.running = True
        self.rotation_task = asyncio.create_task(self._rotation_loop())
        logger.info("Key rotation scheduler started successfully")
        logger.info("Key rotation scheduler started")
        
    async def stop(self):
        """Stop the key rotation scheduler."""
        if not self.running:
            logger.warning("Key rotation scheduler is not running")
            return
            
        self.running = False
        if self.rotation_task:
            self.rotation_task.cancel()
            try:
                await self.rotation_task
            except asyncio.CancelledError:
                pass
            self.rotation_task = None
        logger.info("Key rotation scheduler stopped")
        
    async def _rotation_loop(self):
        """Main loop for scheduled key rotation."""
        while self.running:
            try:
                # Check each service for rotation
                for service, interval_days in self.rotation_intervals.items():
                    await self._check_and_rotate_key(service, interval_days)
                    
                # Sleep for a day before checking again
                await asyncio.sleep(86400)  # 24 hours
            except Exception as e:
                logger.error(f"Error in key rotation loop: {str(e)}")
                # Sleep for a shorter time if there was an error
                await asyncio.sleep(3600)  # 1 hour
                
    async def _check_and_rotate_key(self, service: str, interval_days: int):
        """Check if a key needs rotation and rotate if necessary.
        
        Args:
            service: Name of the service
            interval_days: Number of days between rotations
        """
        try:
            # Get the last rotation time for this service
            last_rotation = self.rotation_manager.last_rotation.get(service)
            if not last_rotation:
                logger.info(f"No previous rotation found for {service}, skipping")
                return
                
            # Calculate next rotation time
            next_rotation = last_rotation + (interval_days * 86400)  # Convert days to seconds
            now = time.time()
            
            # Check if it's time to rotate
            if now >= next_rotation:
                logger.info(f"Rotating key for {service}")
                
                # Call the key rotation method
                new_key = await self.rotation_manager.rotate_key(service)
                
                # Log the rotation event
                self._log_rotation_event(service, "scheduled")
                
                logger.info(f"Successfully rotated key for {service}")
            else:
                # Calculate time remaining until next rotation
                days_remaining = (next_rotation - now) / 86400
                logger.debug(f"Key rotation for {service} scheduled in {days_remaining:.1f} days")
        except Exception as e:
            logger.error(f"Error checking/rotating key for {service}: {str(e)}")
            # Log the failed rotation attempt
            self._log_rotation_event(service, "failed", error=str(e))
            
    def _log_rotation_event(self, service: str, event_type: str, error: str = None):
        """Log a key rotation event to the audit log.
        
        Args:
            service: Name of the service
            event_type: Type of event (scheduled, manual, failed)
            error: Optional error message if the rotation failed
        """
        event = {
            "service": service,
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            "success": error is None
        }
        
        if error:
            event["error"] = error
            
        # Add to audit log
        self.audit_log.append(event)
        
        # Trim audit log if it gets too large
        if len(self.audit_log) > self.max_audit_log_entries:
            self.audit_log = self.audit_log[-self.max_audit_log_entries:]
            
    def get_audit_log(self, service: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get the key rotation audit log.
        
        Args:
            service: Optional service name to filter by
            limit: Maximum number of log entries to return
            
        Returns:
            List of audit log entries
        """
        if service:
            filtered_log = [entry for entry in self.audit_log if entry["service"] == service]
        else:
            filtered_log = self.audit_log.copy()
            
        # Return most recent entries first, limited to requested count
        return sorted(filtered_log, key=lambda x: x["timestamp"], reverse=True)[:limit]
        
    async def force_rotate_key(self, service: str) -> bool:
        """Force an immediate key rotation for a service.
        
        Args:
            service: Name of the service to rotate key for
            
        Returns:
            True if rotation was successful, False otherwise
        """
        try:
            logger.info(f"Forcing key rotation for {service}")
            
            # Call the key rotation method
            new_key = await self.rotation_manager.rotate_key(service)
            
            # Log the rotation event
            self._log_rotation_event(service, "manual")
            
            logger.info(f"Successfully rotated key for {service}")
            return True
        except Exception as e:
            logger.error(f"Error forcing key rotation for {service}: {str(e)}")
            # Log the failed rotation attempt
            self._log_rotation_event(service, "failed", error=str(e))
            return False

# Singleton instance for application-wide use
_scheduler_instance = None

def get_key_rotation_scheduler() -> KeyRotationScheduler:
    """Get the singleton instance of KeyRotationScheduler.
    
    Returns:
        The KeyRotationScheduler instance
    """
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = KeyRotationScheduler()
    return _scheduler_instance