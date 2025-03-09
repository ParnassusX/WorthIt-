import asyncio
import logging
from typing import Optional, Any
from redis.asyncio import Redis
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class RedisClient:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._client: Optional[Redis] = None
        self._connection_pool = None

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=30))
    async def connect(self) -> Redis:
        """Establish connection to Redis with retry logic."""
        if self._client is None:
            try:
                pool_settings = self._get_pool_settings()
                self._client = await Redis.from_url(
                    self.redis_url,
                    decode_responses=False,
                    **pool_settings
                )
                await self._verify_connection()
                logger.info("Successfully connected to Redis")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {str(e)}")
                if self._client:
                    await self._client.close()
                self._client = None
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
        
        # Handle Upstash Redis URLs
        if "upstash" in self.redis_url:
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
                "retry_on_error": True       # Retry on all errors, not just timeouts
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

    async def close(self) -> None:
        """Close Redis connection and cleanup resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._connection_pool:
            await self._connection_pool.disconnect(inuse_connections=True)
            self._connection_pool = None

    async def execute(self, command: str, *args: Any) -> Any:
        """Execute Redis command with automatic reconnection."""
        client = await self.connect()
        try:
            return await getattr(client, command)(*args)
        except (ConnectionError, asyncio.TimeoutError) as e:
            logger.error(f"Redis execution error: {str(e)}")
            await self.close()
            raise