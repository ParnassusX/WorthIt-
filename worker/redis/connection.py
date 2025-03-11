import asyncio
import logging
import os
import time
from typing import Optional, Dict, Any
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, TimeoutError as RedisTimeoutError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

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
            # Load Redis URL from environment with fallback
            self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
            self._client: Optional[RedisClient] = None
            self._redis: Optional[Redis] = None
            self._cleanup_task = None
            self._health_check_task = None
            self._is_shutting_down = False
            self._connection_errors = 0
            self._last_health_check = None
            self._health_check_interval = 60
            self._connection_pool = None
            self._metrics = {
                "connection_attempts": 0,
                "connection_failures": 0,
                "last_connection_time": None,
                "last_error": None,
                "health_checks": 0,
                "recovery_attempts": 0,
                "successful_recoveries": 0
            }
            self.initialized = True
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, asyncio.TimeoutError, RedisTimeoutError, OSError))
    )
    async def get_client(self) -> Redis:
        """Get a Redis client instance with enhanced retry logic and connection pooling."""
        self._metrics["connection_attempts"] += 1
        
        if self._redis is None or not await self._check_connection():
            await self._initialize_client()
            
        # Monitor connection health periodically
        current_time = time.time()
        if self._last_health_check is None or \
           (current_time - self._last_health_check > self._health_check_interval):
            await self._check_connection()
            self._last_health_check = current_time
            self._metrics["health_checks"] += 1
            
        return self._redis
    
    async def _initialize_client(self):
        """Initialize Redis client with proper connection pooling and error handling."""
        try:
            # Create a new RedisClient instance with enhanced metrics
            self._client = RedisClient(self.redis_url)
            self._redis = await self._client.connect()
            
            # Start monitoring tasks if not already running
            await self._start_monitoring()
            
            # Update metrics
            self._metrics["last_connection_time"] = time.time()
            
            logger.info("Successfully initialized Redis client")
        except Exception as e:
            self._metrics["connection_failures"] += 1
            self._metrics["last_error"] = str(e)
            logger.error(f"Failed to initialize Redis client: {str(e)}")
            
            # Cleanup resources on failure
            if self._client:
                await self._client.close()
            self._client = None
            self._redis = None
            raise
    
    async def _check_connection(self) -> bool:
        """Check Redis connection health with improved error handling and metrics."""
        try:
            if self._redis is None:
                logger.error("Redis client is not initialized")
                return False
            
            # Use timeout to prevent hanging
            ping_result = await asyncio.wait_for(self._redis.ping(), timeout=5.0)
            
            if ping_result:
                if self._connection_errors > 0:
                    logger.info("Connection restored after previous errors")
                    self._connection_errors = 0
                return True
            
            logger.warning("Redis ping returned false")
            return False
        except (ConnectionError, asyncio.TimeoutError, RedisTimeoutError, OSError) as e:
            self._connection_errors += 1
            self._metrics["last_error"] = str(e)
            logger.error(f"Redis connection error: {str(e)}")
            
            # Initiate recovery after multiple failures
            if self._connection_errors >= 3:
                logger.critical("Multiple connection failures detected, initiating recovery")
                await self._initiate_recovery()
            return False
        except Exception as e:
            self._metrics["last_error"] = str(e)
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
            self._metrics["recovery_attempts"] += 1
            
            # Exponential backoff for recovery attempts
            for attempt in range(3):
                try:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    await self._initialize_client()
                    if await self._check_connection():
                        logger.info("Connection recovered successfully")
                        self._metrics["successful_recoveries"] += 1
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
                
    def get_metrics(self) -> Dict[str, Any]:
        """Get Redis connection manager metrics for monitoring."""
        return {
            **self._metrics,
            "connection_errors": self._connection_errors,
            "last_health_check": self._last_health_check,
            "is_connected": self._redis is not None
        }
        
    async def release_connection(self, redis_client: Redis) -> None:
        """Release a Redis connection back to the pool."""
        # This is a no-op since we're using connection pooling
        # but we keep this method for API compatibility
        pass
    
    async def shutdown(self):
        """Gracefully shutdown Redis connections with enhanced error handling."""
        self._is_shutting_down = True
        logger.info("Initiating Redis connection manager shutdown")
        
        # Cancel monitoring tasks
        for task_name, task in [("cleanup", self._cleanup_task), ("health_check", self._health_check_task)]:
            if task and not task.done():
                try:
                    logger.debug(f"Cancelling {task_name} task")
                    task.cancel()
                    await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout while waiting for {task_name} task to cancel")
                except asyncio.CancelledError:
                    logger.debug(f"{task_name} task cancelled successfully")
                except Exception as e:
                    logger.error(f"Error cancelling {task_name} task: {str(e)}")
        
        # Close Redis connection with timeout protection
        try:
            if self._client:
                logger.debug("Closing Redis client")
                await asyncio.wait_for(self._client.close(), timeout=5.0)
                self._client = None
            
            # Ensure Redis client is also cleared
            if self._redis:
                logger.debug("Closing Redis connection")
                await asyncio.wait_for(self._redis.close(), timeout=5.0)
                self._redis = None
                
            # Final cleanup of connection pool if it exists
            if hasattr(self, '_connection_pool') and self._connection_pool:
                logger.debug("Disconnecting connection pool")
                await self._connection_pool.disconnect(inuse_connections=True)
                self._connection_pool = None
                
            logger.info("Redis connection manager shutdown completed successfully")
        except asyncio.TimeoutError:
            logger.warning("Timeout during Redis connection shutdown")
        except Exception as e:
            logger.error(f"Error during Redis connection shutdown: {str(e)}")
            
        # Reset metrics for potential reconnection
        self._connection_errors = 0
        self._metrics["connection_attempts"] = 0
        self._metrics["connection_failures"] = 0

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