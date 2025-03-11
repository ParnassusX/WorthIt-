import asyncio
import logging
import os
import time
from typing import Optional, Any, Dict
from redis.asyncio import Redis, ConnectionPool
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

class RedisClient:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._client: Optional[Redis] = None
        self._connection_pool: Optional[ConnectionPool] = None
        self._last_connection_attempt = 0
        self._connection_attempts = 0
        self._connection_failures = 0
        self._last_error = None
        self._metrics = {
            "operations": 0,
            "errors": 0,
            "avg_latency": 0,
            "last_operation_time": 0
        }

    @retry(
        stop=stop_after_attempt(5), 
        wait=wait_exponential(multiplier=1, min=4, max=30),
        retry=retry_if_exception_type((ConnectionError, asyncio.TimeoutError, OSError))
    )
    async def connect(self) -> Redis:
        """Establish connection to Redis with enhanced retry logic and metrics tracking."""
        if self._client is None or not self._connection_pool:
            try:
                self._last_connection_attempt = time.time()
                self._connection_attempts += 1
                
                # Get optimized pool settings
                pool_settings = self._get_pool_settings()
                
                # Create connection pool first
                self._connection_pool = ConnectionPool.from_url(
                    self.redis_url,
                    **pool_settings
                )
                
                # Create Redis client with the pool
                self._client = Redis.from_pool(
                    self._connection_pool,
                    decode_responses=False
                )
                
                # Verify the connection is working
                await self._verify_connection()
                
                logger.info("Successfully connected to Redis")
            except Exception as e:
                self._connection_failures += 1
                self._last_error = str(e)
                logger.error(f"Failed to connect to Redis: {str(e)}")
                
                # Clean up resources on failure
                await self._cleanup_resources()
                raise
        return self._client

    def _get_pool_settings(self) -> dict:
        """Get Redis connection pool settings based on URL."""
        base_settings = {
            "retry_on_timeout": True,
            "socket_timeout": 15.0,
            "socket_connect_timeout": 10.0,
            "socket_keepalive": True,
            "health_check_interval": 60,
            "retry": True
        }
        
        # Handle Upstash Redis URLs or check environment variables for SSL settings
        use_ssl = "upstash" in self.redis_url or os.getenv('REDIS_SSL', '').lower() == 'true'
        
        if use_ssl:
            # Ensure we're using SSL for Upstash via rediss:// protocol
            # instead of using the explicit ssl parameter
            if not self.redis_url.startswith("rediss://"):
                self.redis_url = self.redis_url.replace("redis://", "rediss://")
                logger.info(f"Converted Redis URL to use SSL: {self.redis_url}")
            
            # Upstash-specific settings - optimized for cloud-based Redis
            base_settings.update({
                "socket_timeout": 30.0,
                "socket_connect_timeout": 20.0,
                "max_connections": 5,
                "retry_on_timeout": True,
                "health_check_interval": 30,  # More frequent health checks for cloud Redis
                "retry_on_error": True,      # Retry on all errors, not just timeouts
                "ssl_cert_reqs": None        # Don't verify SSL cert in serverless environment
            })
            
            # Remove ssl parameter if it exists as it's not supported in current Redis client
            # when using rediss:// protocol (SSL is handled by the protocol)
            if "ssl" in base_settings:
                del base_settings["ssl"]
        
        return base_settings

    async def _verify_connection(self, max_attempts: int = 3) -> None:
        """Verify Redis connection with retry logic."""
        for attempt in range(max_attempts):
            try:
                # Simple ping to verify connection
                result = await asyncio.wait_for(self._client.ping(), timeout=10.0)
                if result:
                    return
                raise Exception("Ping returned false")
            except asyncio.TimeoutError:
                if attempt == max_attempts - 1:
                    raise Exception("Failed to verify Redis connection - timeout")
                logger.warning(f"Connection verification attempt {attempt + 1} timed out, retrying...")
            except Exception as e:
                if attempt == max_attempts - 1:
                    raise
                logger.warning(f"Connection verification attempt {attempt + 1} failed: {str(e)}, retrying...")
            await asyncio.sleep(2 ** attempt)

    async def _cleanup_resources(self) -> None:
        """Clean up Redis resources properly."""
        try:
            if self._client:
                await self._client.aclose()
                self._client = None
            if self._connection_pool:
                await self._connection_pool.disconnect(inuse_connections=True)
                self._connection_pool = None
        except Exception as e:
            logger.error(f"Error during resource cleanup: {str(e)}")

    async def close(self) -> None:
        """Close Redis connection and cleanup resources."""
        await self._cleanup_resources()

    async def execute(self, command: str, *args: Any) -> Any:
        """Execute Redis command with automatic reconnection and metrics tracking."""
        start_time = time.time()
        self._metrics["operations"] += 1
        
        try:
            client = await self.connect()
            result = await getattr(client, command)(*args)
            
            # Update metrics on success
            duration = time.time() - start_time
            self._metrics["last_operation_time"] = duration
            self._metrics["avg_latency"] = (
                (self._metrics["avg_latency"] * (self._metrics["operations"] - 1) + duration) / 
                self._metrics["operations"]
            )
            
            return result
        except (ConnectionError, asyncio.TimeoutError, OSError) as e:
            self._metrics["errors"] += 1
            self._last_error = str(e)
            logger.error(f"Redis execution error: {str(e)}")
            await self.close()
            raise
        except Exception as e:
            self._metrics["errors"] += 1
            self._last_error = str(e)
            logger.error(f"Unexpected Redis error: {str(e)}")
            raise
            
    def get_metrics(self) -> Dict[str, Any]:
        """Get Redis client metrics for monitoring."""
        return {
            "connection_attempts": self._connection_attempts,
            "connection_failures": self._connection_failures,
            "last_connection_attempt": self._last_connection_attempt,
            "last_error": self._last_error,
            "operations": self._metrics["operations"],
            "errors": self._metrics["errors"],
            "avg_latency": self._metrics["avg_latency"],
            "last_operation_time": self._metrics["last_operation_time"]
        }