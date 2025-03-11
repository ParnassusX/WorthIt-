"""Redis Cache Optimizer for WorthIt!

This module provides optimization strategies for Redis cache usage including:
- Batch operations for reducing network overhead
- Intelligent TTL management based on access patterns
- Memory usage optimization with compression
- Cache eviction policies
- Prefetching commonly accessed keys

It works with the existing RedisClient to provide enhanced caching capabilities.
"""

import asyncio
import logging
import time
import zlib
import json
import random
from typing import Dict, List, Any, Optional, Tuple, Set
from collections import defaultdict, Counter
from prometheus_client import Counter as PrometheusCounter, Histogram, Gauge

logger = logging.getLogger(__name__)

class RedisCacheOptimizer:
    """Optimizes Redis cache operations for improved performance and resource usage."""
    
    def __init__(self, redis_client):
        """Initialize the cache optimizer with a Redis client.
        
        Args:
            redis_client: An instance of RedisClient
        """
        self.redis_client = redis_client
        self.access_patterns = defaultdict(int)  # Key access frequency tracking
        self.last_accessed = {}  # Last access time for each key
        self.batch_operations = defaultdict(list)  # Pending batch operations
        self.batch_size = 10  # Default batch size
        self.batch_timeout = 0.1  # 100ms default timeout
        self.compression_threshold = 1024  # Compress values larger than 1KB
        self.compression_level = 6  # Balance between speed and compression ratio
        self.prefetch_keys = set()  # Keys to prefetch
        self.ttl_tiers = {
            'frequent': 3600,     # 1 hour for frequently accessed keys
            'regular': 1800,      # 30 minutes for regularly accessed keys
            'infrequent': 600     # 10 minutes for infrequently accessed keys
        }
        self._batch_tasks = {}
        self._metrics = {
            'batch_operations': 0,
            'compressed_keys': 0,
            'compression_ratio': 0,
            'prefetched_keys': 0,
            'adaptive_ttl_adjustments': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        
        # Prometheus metrics for monitoring cache performance
        self._prometheus = {
            'cache_hits': PrometheusCounter('redis_cache_hits_total', 'Total number of cache hits'),
            'cache_misses': PrometheusCounter('redis_cache_misses_total', 'Total number of cache misses'),
            'compression_ratio': Gauge('redis_compression_ratio', 'Compression ratio for cached data'),
            'batch_operations': PrometheusCounter('redis_batch_operations_total', 'Total number of batch operations'),
            'prefetched_keys': PrometheusCounter('redis_prefetched_keys_total', 'Total number of prefetched keys'),
            'get_latency': Histogram('redis_get_latency_seconds', 'Latency of get operations'),
            'set_latency': Histogram('redis_set_latency_seconds', 'Latency of set operations'),
            'key_size': Histogram('redis_key_size_bytes', 'Size of cached values in bytes')
        }
        
        # Start background tasks
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        self._prefetch_task = asyncio.create_task(self._periodic_prefetch())
    
    async def get(self, key: str) -> Optional[Any]:
        """Get a value from cache with optimized access patterns.
        
        Args:
            key: The cache key to retrieve
            
        Returns:
            The cached value if found, None otherwise
        """
        # Track access patterns
        self.access_patterns[key] += 1
        self.last_accessed[key] = time.time()
        
        try:
            # Measure get operation latency
            start_time = time.time()
            
            # Get from Redis
            value = await self.redis_client.execute('get', key)
            
            # Record latency in Prometheus
            get_latency = time.time() - start_time
            self._prometheus['get_latency'].observe(get_latency)
            
            if value:
                # Record cache hit
                self._metrics['cache_hits'] += 1
                self._prometheus['cache_hits'].inc()
                
                # Record value size
                if isinstance(value, bytes):
                    self._prometheus['key_size'].observe(len(value))
                
                # Decompress if needed
                if isinstance(value, bytes) and value.startswith(b'compressed:'):
                    value = zlib.decompress(value[11:])
                
                # Parse JSON
                if isinstance(value, bytes):
                    value = value.decode('utf-8')
                    
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    # Return as is if not JSON
                    return value
            else:
                # Record cache miss
                self._metrics['cache_misses'] += 1
                self._prometheus['cache_misses'].inc()
                return None
                
        except Exception as e:
            logger.error(f"Error getting key {key}: {str(e)}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a value in cache with optimized storage.
        
        Args:
            key: The cache key
            value: The value to cache
            ttl: Time to live in seconds (optional)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Measure set operation latency
            start_time = time.time()
            
            # Determine appropriate TTL based on access patterns
            if ttl is None:
                ttl = self._get_adaptive_ttl(key)
            
            # Serialize value
            if not isinstance(value, (str, bytes)):
                value = json.dumps(value)
                
            # Compress if needed
            original_size = 0
            compressed_size = 0
            if isinstance(value, str):
                value_bytes = value.encode('utf-8')
                original_size = len(value_bytes)
                
                if original_size > self.compression_threshold:
                    compressed = zlib.compress(value_bytes, level=self.compression_level)
                    compressed_size = len(compressed)
                    
                    # Only use compression if it actually reduces size
                    if compressed_size < original_size:
                        value = b'compressed:' + compressed
                        self._metrics['compressed_keys'] += 1
                        compression_ratio = compressed_size / original_size
                        self._metrics['compression_ratio'] = compression_ratio
                        
                        # Update Prometheus compression ratio metric
                        self._prometheus['compression_ratio'].set(compression_ratio)
                    else:
                        value = value_bytes
            
            # Add to batch operations
            self.batch_operations['set'].append((key, value, ttl))
            
            # Process batch if it reaches the threshold
            if len(self.batch_operations['set']) >= self.batch_size:
                await self._process_batch('set')
            else:
                # Schedule batch processing after timeout
                if 'set' not in self._batch_tasks:
                    self._batch_tasks['set'] = asyncio.create_task(
                        self._schedule_batch('set')
                    )
            
            # Record set latency in Prometheus
            set_latency = time.time() - start_time
            self._prometheus['set_latency'].observe(set_latency)
            
            return True
        except Exception as e:
            logger.error(f"Error setting key {key}: {str(e)}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete a key from cache.
        
        Args:
            key: The cache key to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Add to batch operations
            self.batch_operations['delete'].append(key)
            
            # Process batch if it reaches the threshold
            if len(self.batch_operations['delete']) >= self.batch_size:
                await self._process_batch('delete')
            else:
                # Schedule batch processing after timeout
                if 'delete' not in self._batch_tasks:
                    self._batch_tasks['delete'] = asyncio.create_task(
                        self._schedule_batch('delete')
                    )
            
            # Clean up tracking data
            if key in self.access_patterns:
                del self.access_patterns[key]
            if key in self.last_accessed:
                del self.last_accessed[key]
            if key in self.prefetch_keys:
                self.prefetch_keys.remove(key)
                
            return True
        except Exception as e:
            logger.error(f"Error deleting key {key}: {str(e)}")
            return False
    
    async def _schedule_batch(self, operation_type: str):
        """Schedule a batch operation after timeout.
        
        Args:
            operation_type: Type of operation ('set', 'delete', etc.)
        """
        await asyncio.sleep(self.batch_timeout)
        await self._process_batch(operation_type)
    
    async def _process_batch(self, operation_type: str):
        """Process a batch of operations.
        
        Args:
            operation_type: Type of operation ('set', 'delete', etc.)
        """
        if operation_type in self._batch_tasks:
            self._batch_tasks[operation_type].cancel()
            del self._batch_tasks[operation_type]
        
        operations = self.batch_operations[operation_type]
        self.batch_operations[operation_type] = []
        
        if not operations:
            return
        
        try:
            # Measure batch operation time
            start_time = time.time()
            batch_size = len(operations)
            
            if operation_type == 'set':
                # Use pipeline for batch set operations
                pipeline = await self.redis_client.execute('pipeline')
                
                for key, value, ttl in operations:
                    if ttl:
                        pipeline.setex(key, ttl, value)
                    else:
                        pipeline.set(key, value)
                
                await pipeline.execute()
                self._metrics['batch_operations'] += 1
                self._prometheus['batch_operations'].inc()
                
            elif operation_type == 'delete':
                # Use pipeline for batch delete operations
                pipeline = await self.redis_client.execute('pipeline')
                
                for key in operations:
                    pipeline.delete(key)
                
                await pipeline.execute()
                self._metrics['batch_operations'] += 1
                self._prometheus['batch_operations'].inc()
            
            # Log batch operation performance
            duration = time.time() - start_time
            logger.debug(
                f"Processed {batch_size} {operation_type} operations in {duration:.3f}s",
                extra={"batch_size": batch_size, "operation_type": operation_type, "duration": duration}
            )
                
        except Exception as e:
            logger.error(f"Error processing batch {operation_type}: {str(e)}")
    
    def _get_adaptive_ttl(self, key: str) -> int:
        """Get adaptive TTL based on access patterns.
        
        Args:
            key: The cache key
            
        Returns:
            TTL in seconds
        """
        access_count = self.access_patterns.get(key, 0)
        
        # Determine TTL tier based on access frequency
        if access_count > 10:
            ttl = self.ttl_tiers['frequent']
        elif access_count > 3:
            ttl = self.ttl_tiers['regular']
        else:
            ttl = self.ttl_tiers['infrequent']
        
        self._metrics['adaptive_ttl_adjustments'] += 1
        return ttl
    
    async def _periodic_cleanup(self):
        """Periodically clean up tracking data for expired keys."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                current_time = time.time()
                expired_keys = []
                
                # Find keys that haven't been accessed in a while
                for key, last_access in self.last_accessed.items():
                    if current_time - last_access > 7200:  # 2 hours
                        expired_keys.append(key)
                
                # Clean up tracking data for expired keys
                for key in expired_keys:
                    if key in self.access_patterns:
                        del self.access_patterns[key]
                    if key in self.last_accessed:
                        del self.last_accessed[key]
                    if key in self.prefetch_keys:
                        self.prefetch_keys.remove(key)
                
                logger.info(f"Cleaned up tracking data for {len(expired_keys)} expired keys")
                
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {str(e)}")
    
    async def _periodic_prefetch(self):
        """Periodically prefetch frequently accessed keys."""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                
                # Find top accessed keys
                top_keys = Counter(self.access_patterns).most_common(10)
                
                # Prefetch keys that aren't already in the prefetch set
                for key, _ in top_keys:
                    if key not in self.prefetch_keys:
                        # Check if key exists in Redis
                        exists = await self.redis_client.execute('exists', key)
                        
                        if exists:
                            # Get the key to refresh TTL and keep it in cache
                            await self.get(key)
                            self.prefetch_keys.add(key)
                            self._metrics['prefetched_keys'] += 1
                
                logger.info(f"Prefetched {len(self.prefetch_keys)} frequently accessed keys")
                
            except Exception as e:
                logger.error(f"Error in periodic prefetch: {str(e)}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get cache optimizer metrics.
        
        Returns:
            Dictionary of metrics
        """
        return {
            'batch_operations': self._metrics['batch_operations'],
            'compressed_keys': self._metrics['compressed_keys'],
            'compression_ratio': self._metrics['compression_ratio'],
            'prefetched_keys': self._metrics['prefetched_keys'],
            'adaptive_ttl_adjustments': self._metrics['adaptive_ttl_adjustments'],
            'cache_hits': self._metrics['cache_hits'],
            'cache_misses': self._metrics['cache_misses'],
            'hit_ratio': self._metrics['cache_hits'] / (self._metrics['cache_hits'] + self._metrics['cache_misses']) 
                if (self._metrics['cache_hits'] + self._metrics['cache_misses']) > 0 else 0,
            'tracked_keys': len(self.access_patterns),
            'batch_queue_size': sum(len(ops) for ops in self.batch_operations.values())
        }
    
    async def close(self):
        """Clean up resources."""
        # Cancel background tasks
        if hasattr(self, '_cleanup_task'):
            self._cleanup_task.cancel()
        if hasattr(self, '_prefetch_task'):
            self._prefetch_task.cancel()
        
        # Process any remaining batch operations
        for operation_type in self.batch_operations:
            if self.batch_operations[operation_type]:
                await self._process_batch(operation_type)
        
        # Cancel any pending batch tasks
        for task_type, task in self._batch_tasks.items():
            task.cancel()
        
        self._batch_tasks = {}