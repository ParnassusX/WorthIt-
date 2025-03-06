import asyncio
import logging
import os
from typing import Optional
from redis.asyncio import Redis
from tenacity import retry, stop_after_attempt, wait_exponential

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
            self._client: Optional[Redis] = None
            self._connection_pool = None
            self._cleanup_task = None
            self._health_check_task = None
            self._is_shutting_down = False
            self._connection_errors = 0
            self._last_health_check = 0
            self.initialized = True
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def get_client(self) -> Redis:
        """Get a Redis client instance with retry logic and connection pooling."""
        if self._client is None or not await self._check_connection():
            await self._initialize_client()
        return self._client
    
    async def _initialize_client(self):
        """Initialize Redis client with proper connection pooling."""
        try:
            # Configure SSL for Upstash Redis
            if "upstash" in self.redis_url and not self.redis_url.startswith("rediss://"):
                self.redis_url = self.redis_url.replace("redis://", "rediss://")
            
            ssl_enabled = "upstash" in self.redis_url
            pool_settings = {
                "max_connections": 20,
                "max_idle_time": 300,
                "retry_on_timeout": True,
                "health_check_interval": 30,
                "socket_timeout": 5.0,
                "socket_connect_timeout": 5.0,
                "socket_keepalive": True
            }
            
            if ssl_enabled:
                pool_settings.update({
                    "ssl_cert_reqs": None,
                    "ssl_check_hostname": False,
                    "retry_on_error": [TimeoutError, ConnectionError]
                })
            
            self._client = await Redis.from_url(
                self.redis_url,
                decode_responses=False,
                **pool_settings
            )
            
            # Verify connection
            await self._check_connection()
            
            # Start monitoring tasks
            await self._start_monitoring()
            
            logger.info("Successfully initialized Redis client with connection pooling")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {e}")
            self._client = None
            raise
    
    async def _check_connection(self) -> bool:
        """Check if Redis connection is alive and healthy."""
        try:
            if self._client is None:
                return False
            
            await asyncio.wait_for(self._client.ping(), timeout=2.0)
            self._last_health_check = asyncio.get_event_loop().time()
            self._connection_errors = 0
            return True
            
        except Exception as e:
            logger.error(f"Redis connection check failed: {e}")
            self._connection_errors += 1
            return False
    
    async def _start_monitoring(self):
        """Start connection monitoring tasks."""
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_stale_connections())
        if not self._health_check_task:
            self._health_check_task = asyncio.create_task(self._health_check())
    
    async def _cleanup_stale_connections(self):
        """Periodically cleanup stale connections."""
        while not self._is_shutting_down:
            try:
                if self._connection_pool:
                    await self._connection_pool.disconnect(inuse_connections=True)
                    self._connection_errors = 0
                await asyncio.sleep(300)  # Run every 5 minutes
            except Exception as e:
                logger.error(f"Error during connection cleanup: {e}")
                self._connection_errors += 1
                await asyncio.sleep(60)
    
    async def _health_check(self):
        """Periodic health check for Redis connection."""
        while not self._is_shutting_down:
            try:
                if self._client:
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
        
        if self._connection_pool:
            await self._connection_pool.disconnect(inuse_connections=True)
            self._connection_pool = None
        
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