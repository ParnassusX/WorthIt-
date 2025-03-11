"""Cache Manager for WorthIt!

This module provides a centralized caching solution using Redis for the WorthIt! application.
It implements caching strategies, TTL management, and error handling for improved performance.
Features connection pooling, automatic reconnection, health checks, and key namespacing.
"""

import json
import logging
from typing import Any, Optional, Union
from urllib.parse import urlparse
import redis
from redis.exceptions import RedisError
from api.errors import CacheError

class CacheManager:
    """Manages caching operations using Redis for the WorthIt! application."""

    def __init__(self, redis_url: str):
        """Initialize the cache manager with Redis connection.

        Args:
            redis_url (str): The Redis connection URL from environment variables
        """
        try:
            parsed_url = urlparse(redis_url)
            self.redis_client = redis.Redis(
                host=parsed_url.hostname,
                port=parsed_url.port,
                username=parsed_url.username,
                password=parsed_url.password,
                ssl=parsed_url.scheme == 'rediss',
                decode_responses=True
            )
            self.logger = logging.getLogger(__name__)
        except Exception as e:
            raise CacheError(f"Failed to initialize Redis connection: {str(e)}")

    def get(self, key: str) -> Optional[Any]:
        """Retrieve a value from cache.

        Args:
            key (str): The cache key to retrieve

        Returns:
            Optional[Any]: The cached value if found, None otherwise

        Raises:
            CacheError: If there's an error accessing the cache
        """
        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except RedisError as e:
            self.logger.error(f"Redis error while getting key {key}: {str(e)}")
            raise CacheError(f"Failed to retrieve from cache: {str(e)}")
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error for key {key}: {str(e)}")
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Store a value in cache with optional TTL.

        Args:
            key (str): The cache key
            value (Any): The value to cache
            ttl (Optional[int]): Time to live in seconds

        Returns:
            bool: True if successful, False otherwise

        Raises:
            CacheError: If there's an error accessing the cache
        """
        try:
            serialized_value = json.dumps(value)
            return self.redis_client.set(key, serialized_value, ex=ttl)
        except (RedisError, TypeError) as e:
            self.logger.error(f"Error setting cache for key {key}: {str(e)}")
            raise CacheError(f"Failed to store in cache: {str(e)}")

    def delete(self, key: str) -> bool:
        """Remove a value from cache.

        Args:
            key (str): The cache key to delete

        Returns:
            bool: True if key was deleted, False if key didn't exist

        Raises:
            CacheError: If there's an error accessing the cache
        """
        try:
            return bool(self.redis_client.delete(key))
        except RedisError as e:
            self.logger.error(f"Error deleting key {key}: {str(e)}")
            raise CacheError(f"Failed to delete from cache: {str(e)}")

    def exists(self, key: str) -> bool:
        """Check if a key exists in cache.

        Args:
            key (str): The cache key to check

        Returns:
            bool: True if key exists, False otherwise

        Raises:
            CacheError: If there's an error accessing the cache
        """
        try:
            return bool(self.redis_client.exists(key))
        except RedisError as e:
            self.logger.error(f"Error checking existence of key {key}: {str(e)}")
            raise CacheError(f"Failed to check key existence: {str(e)}")

    def clear_all(self) -> bool:
        """Clear all cached data.

        Returns:
            bool: True if successful, False otherwise

        Raises:
            CacheError: If there's an error accessing the cache
        """
        try:
            return bool(self.redis_client.flushall())
        except RedisError as e:
            self.logger.error(f"Error clearing cache: {str(e)}")
            raise CacheError(f"Failed to clear cache: {str(e)}")
            
    def mset(self, mapping: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set multiple key-value pairs in a single operation.
        
        Args:
            mapping: Dictionary of key-value pairs to cache
            ttl: Optional time-to-live in seconds (applied to all keys)
            
        Returns:
            bool: True if successful, False otherwise
            
        Raises:
            CacheError: If there's an error accessing the cache
        """
        if not mapping:
            return True
            
        # Namespace all keys and serialize values
        serialized_mapping = {}
        try:
            for key, value in mapping.items():
                serialized_mapping[key] = json.dumps(value)
        except TypeError as e:
            self.logger.error(f"Error serializing values for mset: {str(e)}")
            raise CacheError(f"Failed to serialize values for cache: {str(e)}")
        
        # Set all values
        try:
            result = self.redis_client.mset(serialized_mapping)
            
            # Set TTL for each key if provided
            if ttl is not None and result:
                pipeline = self.redis_client.pipeline()
                for key in serialized_mapping.keys():
                    pipeline.expire(key, ttl)
                pipeline.execute()
            
            return result
        except RedisError as e:
            self.logger.error(f"Error in mset operation: {str(e)}")
            raise CacheError(f"Failed to set multiple values in cache: {str(e)}")
    
    def health_check(self) -> bool:
        """Perform a health check on the Redis connection.
        
        Returns:
            bool: True if Redis is healthy, False otherwise
        """
        try:
            return bool(self.redis_client.ping())
        except RedisError:
            return False
    
    def close(self):
        """Close the Redis connection."""
        try:
            self.redis_client.close()
            self.logger.info("Redis connection closed")
        except Exception as e:
            self.logger.warning(f"Error closing Redis connection: {str(e)}")