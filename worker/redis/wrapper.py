import logging
from typing import Optional, Any, Dict
from redis.asyncio import Redis

from .connection import get_redis_client, get_redis_manager
from .monitoring import create_redis_monitor, RedisMonitor

logger = logging.getLogger(__name__)

class RedisWrapper:
    """A wrapper class that provides a simplified interface to Redis functionality.
    This class uses the modular Redis components for better maintainability.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self._redis: Optional[Redis] = None
            self._monitor: Optional[RedisMonitor] = None
            self.initialized = True
    
    async def initialize(self):
        """Initialize Redis client and monitoring."""
        try:
            self._redis = await get_redis_client()
            self._monitor = await create_redis_monitor(self._redis)
            logger.info("Redis wrapper initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Redis wrapper: {str(e)}")
            return False
    
    async def get(self, key: str) -> Any:
        """Get a value from Redis."""
        try:
            return await self._redis.get(key)
        except Exception as e:
            logger.error(f"Error getting key {key}: {str(e)}")
            return None
    
    async def set(self, key: str, value: Any, expiration: Optional[int] = None) -> bool:
        """Set a value in Redis with optional expiration."""
        try:
            if expiration:
                return await self._redis.setex(key, expiration, value)
            return await self._redis.set(key, value)
        except Exception as e:
            logger.error(f"Error setting key {key}: {str(e)}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete a key from Redis."""
        try:
            return await self._redis.delete(key) > 0
        except Exception as e:
            logger.error(f"Error deleting key {key}: {str(e)}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in Redis."""
        try:
            return await self._redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Error checking existence of key {key}: {str(e)}")
            return False
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get Redis health status and metrics."""
        if self._monitor:
            return self._monitor.get_metrics()
        return {"health_status": "unknown", "error": "Monitor not initialized"}
    
    async def shutdown(self):
        """Shutdown Redis connections and monitoring."""
        try:
            if self._monitor:
                await self._monitor.stop_monitoring()
            
            # Use the connection manager to properly shutdown
            manager = get_redis_manager()
            await manager.shutdown()
            
            logger.info("Redis wrapper shutdown complete")
        except Exception as e:
            logger.error(f"Error during Redis wrapper shutdown: {str(e)}")

# Singleton instance
_redis_wrapper = None

def get_redis_wrapper() -> RedisWrapper:
    """Get the singleton Redis wrapper instance."""
    global _redis_wrapper
    if _redis_wrapper is None:
        _redis_wrapper = RedisWrapper()
    return _redis_wrapper

async def initialize_redis() -> bool:
    """Initialize the Redis wrapper for application use."""
    wrapper = get_redis_wrapper()
    return await wrapper.initialize()