"""Data Cache for WorthIt!

This module provides intelligent caching for frequently accessed data in the application.
It works with the existing CacheManager to provide enhanced caching capabilities for
specific data types and access patterns common in the application.
"""

import logging
import json
import time
from typing import Dict, List, Any, Optional, Tuple, Set, Callable
from functools import wraps
from api.cache_manager import CacheManager

logger = logging.getLogger(__name__)

class DataCache:
    """Intelligent data caching for frequently accessed application data."""
    
    def __init__(self, cache_manager: CacheManager):
        """Initialize the data cache with a cache manager.
        
        Args:
            cache_manager: An instance of CacheManager
        """
        self.cache_manager = cache_manager
        self.access_counters = {}
        self.last_accessed = {}
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'cached_items': 0,
            'evictions': 0
        }
        self.cache_config = {
            # Data type specific TTLs
            'product_data': 3600,      # 1 hour for product data
            'user_preferences': 86400,  # 24 hours for user preferences
            'analysis_results': 1800,   # 30 minutes for analysis results
            'search_results': 600,      # 10 minutes for search results
            'default': 300              # 5 minutes default
        }
        
        # Frequently accessed paths that should be cached
        self.cacheable_paths = [
            '/api/products/',
            '/api/analyze',
            '/api/search',
            '/api/recommendations'
        ]
        
        # Cache key prefixes for different data types
        self.key_prefixes = {
            'product': 'prod:',
            'analysis': 'analysis:',
            'search': 'search:',
            'user': 'user:'
        }
    
    def should_cache_path(self, path: str) -> bool:
        """Determine if a path should be cached based on configured rules.
        
        Args:
            path: The API path to check
            
        Returns:
            True if the path should be cached, False otherwise
        """
        return any(path.startswith(cacheable) for cacheable in self.cacheable_paths)
    
    def get_cache_key(self, data_type: str, identifier: str) -> str:
        """Generate a cache key for a specific data type and identifier.
        
        Args:
            data_type: The type of data (product, analysis, search, user)
            identifier: The unique identifier for the data
            
        Returns:
            A formatted cache key
        """
        prefix = self.key_prefixes.get(data_type, '')
        return f"{prefix}{identifier}"
    
    def get_ttl(self, data_type: str) -> int:
        """Get the appropriate TTL for a data type.
        
        Args:
            data_type: The type of data
            
        Returns:
            TTL in seconds
        """
        return self.cache_config.get(data_type, self.cache_config['default'])
    
    async def get_data(self, data_type: str, identifier: str) -> Optional[Any]:
        """Get data from cache with tracking.
        
        Args:
            data_type: The type of data
            identifier: The unique identifier for the data
            
        Returns:
            The cached data if found, None otherwise
        """
        cache_key = self.get_cache_key(data_type, identifier)
        
        # Track access
        self.access_counters[cache_key] = self.access_counters.get(cache_key, 0) + 1
        self.last_accessed[cache_key] = time.time()
        
        try:
            # Get from cache
            data = self.cache_manager.get(cache_key)
            
            if data is not None:
                self.cache_stats['hits'] += 1
                logger.debug(f"Cache hit for {cache_key}")
                return data
            
            self.cache_stats['misses'] += 1
            logger.debug(f"Cache miss for {cache_key}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting data from cache: {str(e)}")
            return None
    
    async def set_data(self, data_type: str, identifier: str, data: Any) -> bool:
        """Store data in cache with appropriate TTL.
        
        Args:
            data_type: The type of data
            identifier: The unique identifier for the data
            data: The data to cache
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = self.get_cache_key(data_type, identifier)
        ttl = self.get_ttl(data_type)
        
        try:
            # Store in cache
            result = self.cache_manager.set(cache_key, data, ttl=ttl)
            
            if result:
                self.cache_stats['cached_items'] += 1
                logger.debug(f"Cached data for {cache_key} with TTL {ttl}s")
            
            return result
            
        except Exception as e:
            logger.error(f"Error setting data in cache: {str(e)}")
            return False
    
    async def invalidate_data(self, data_type: str, identifier: str) -> bool:
        """Invalidate cached data.
        
        Args:
            data_type: The type of data
            identifier: The unique identifier for the data
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = self.get_cache_key(data_type, identifier)
        
        try:
            # Delete from cache
            result = self.cache_manager.delete(cache_key)
            
            if result:
                self.cache_stats['evictions'] += 1
                logger.debug(f"Invalidated cache for {cache_key}")
                
                # Clean up tracking data
                if cache_key in self.access_counters:
                    del self.access_counters[cache_key]
                if cache_key in self.last_accessed:
                    del self.last_accessed[cache_key]
            
            return result
            
        except Exception as e:
            logger.error(f"Error invalidating cache: {str(e)}")
            return False
    
    def cached(self, data_type: str, id_func: Callable = None):
        """Decorator for caching function results.
        
        Args:
            data_type: The type of data being cached
            id_func: Optional function to extract identifier from function arguments
            
        Returns:
            Decorated function
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Generate identifier from arguments if id_func is provided
                if id_func:
                    identifier = id_func(*args, **kwargs)
                else:
                    # Default to using a hash of the arguments
                    arg_str = json.dumps(str(args) + str(kwargs), sort_keys=True)
                    identifier = hash(arg_str)
                
                # Try to get from cache first
                cached_data = await self.get_data(data_type, str(identifier))
                if cached_data is not None:
                    return cached_data
                
                # If not in cache, call the original function
                result = await func(*args, **kwargs)
                
                # Cache the result
                await self.set_data(data_type, str(identifier), result)
                
                return result
            return wrapper
        return decorator
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary of cache statistics
        """
        stats = self.cache_stats.copy()
        
        # Calculate hit ratio
        total_requests = stats['hits'] + stats['misses']
        stats['hit_ratio'] = stats['hits'] / total_requests if total_requests > 0 else 0
        
        # Add tracking stats
        stats['tracked_items'] = len(self.access_counters)
        
        # Find most frequently accessed items
        if self.access_counters:
            most_accessed = max(self.access_counters.items(), key=lambda x: x[1])
            stats['most_accessed_key'] = most_accessed[0]
            stats['most_accessed_count'] = most_accessed[1]
        
        return stats