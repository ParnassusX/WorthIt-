import asyncio
import logging
import os
import time
from typing import Optional
from redis.asyncio import Redis

from .client import RedisClient

logger = logging.getLogger(__name__)

class RedisConnectionManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
            self._client: Optional[RedisClient] = None
            self._redis: Optional[Redis] = None
            self._cleanup_task = None
            self._health_check_task = None
            self._is_shutting_down = False
            self._connection_errors = 0
            self._last_health_check = None
            self._health_check_interval = 60
            self.initialized = True
    
    async def get_client(self) -> Redis:
        """Get a Redis client instance with enhanced retry logic and connection pooling."""
        if self._redis is None or not await self._check_connection():
            await self._initialize_client()
            
        # Monitor connection health
        if self._last_health_check is None or \
           (time.time() - self._last_health_check > self._health_check_interval):
            await self._check_connection()
            self._last_health_check = time.time()
            
        return self._redis
    
    async def _initialize_client(self):
        """Initialize Redis client with proper connection pooling."""
        try:
            # Create a new RedisClient instance
            self._client = RedisClient(self.redis_url)
            self._redis = await self._client.connect()
            
            # Start monitoring tasks
            await self._start_monitoring()
            
            logger.info("Successfully initialized Redis client")
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {str(e)}")
            if self._client:
                await self._client.close()
            self._client = None
            self._redis = None
            raise
    
    async def _check_connection(self) -> bool:
        """Check Redis connection health with improved error handling."""
        try:
            if self._redis is None:
                logger.error("Redis client is not initialized")
                return False
            
            ping_result = await self._redis.ping()
            if ping_result:
                if self._connection_errors > 0:
                    logger.info("Connection restored after previous errors")
                    self._connection_errors = 0
                return True
            return False
        except (ConnectionError, asyncio.TimeoutError) as e:
            self._connection_errors += 1
            logger.error(f"Redis connection error: {str(e)}")
            if self._connection_errors >= 3:
                logger.critical("Multiple connection failures detected, initiating recovery")
                await self._initiate_recovery()
            return False
        except Exception as e:
            logger.error(f"Unexpected Redis error: {str(e)}")
            return False

    async def _initiate_recovery(self):
        """Consolidated recovery logic for connection failures with exponential backoff."""
        try:
            if self._client:
                await self._client.close()
            self._client = None
            self._redis = None
            self._connection_errors = 0
            logger.info("Initiating connection recovery process")
            
            # Exponential backoff for recovery attempts
            for attempt in range(3):
                try:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    await self._initialize_client()
                    if await self._check_connection():
                        logger.info("Connection recovered successfully")
                        return
                except Exception as e:
                    logger.warning(f"Recovery attempt {attempt + 1} failed: {str(e)}")
            
            logger.error("All recovery attempts failed")
        except Exception as e:
            logger.error(f"Error during recovery: {str(e)}")
    
    async def _start_monitoring(self):
        """Start connection monitoring tasks."""
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_stale_connections())
        if not self._health_check_task:
            self._health_check_task = asyncio.create_task(self._health_check())
    
    async def _cleanup_stale_connections(self):
        """Simplified periodic cleanup of stale connections."""
        while not self._is_shutting_down:
            try:
                if self._client:
                    await self._client.close()
                    await self._initialize_client()
                    self._connection_errors = 0
                await asyncio.sleep(300)  # Run every 5 minutes
            except Exception as e:
                logger.error(f"Error during connection cleanup: {e}")
                await asyncio.sleep(60)
    
    async def _health_check(self):
        """Periodic health check for Redis connection."""
        while not self._is_shutting_down:
            try:
                if self._redis:
                    await self._check_connection()
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                if self._connection_errors > 3:
                    logger.critical("Multiple health check failures detected")
                    await self._initialize_client()
                await asyncio.sleep(5)
    
    async def shutdown(self):
        """Gracefully shutdown Redis connections."""
        self._is_shutting_down = True
        
        # Cancel monitoring tasks
        for task in [self._cleanup_task, self._health_check_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Close Redis connection
        if self._client:
            await self._client.close()
            self._client = None
        
        # Ensure Redis client is also cleared
        if self._redis:
            await self._redis.close()
            self._redis = None
        
        logger.info("Redis connection manager shutdown complete")

# Singleton instance
_redis_manager = None

def get_redis_manager() -> RedisConnectionManager:
    """Get the singleton Redis connection manager instance."""
    global _redis_manager
    if _redis_manager is None:
        _redis_manager = RedisConnectionManager()
    return _redis_manager

async def get_redis_client() -> Redis:
    """Convenience function to get a Redis client."""
    manager = get_redis_manager()
    return await manager.get_client()