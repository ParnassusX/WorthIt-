import logging
from typing import Callable
from fastapi import Request, Response
from api.service_mesh import ServiceMesh
import hashlib
import json
import zlib
import asyncio
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

class CacheMiddleware:
    def __init__(self, service_mesh: ServiceMesh):
        self.service_mesh = service_mesh
        self.hit_counters = {}
        self.last_cleanup = datetime.now()
        self.analytics = {
            'hits': {},
            'misses': {},
            'warm_cache': set(),
            'memory_usage': {
                'cache_size': 0,
                'compression_savings': 0
            },
            'performance': {
                'avg_response_time': 0,
                'total_requests': 0,
                'batch_metrics': {
                    'batch_sizes': [],
                    'batch_latencies': [],
                    'compression_ratio': 0
                }
            }
        }
        self.cleanup_threshold = 1000
        self.memory_limit = 100 * 1024 * 1024  # 100MB
        self.batch_size = 10
        self.batch_timeout = 0.1  # 100ms
        self._request_batches = defaultdict(list)
        self._batch_tasks = {}
        self.compression_threshold = 1024  # Compress responses larger than 1KB
        self.compression_level = 6  # Balance between speed and compression ratio

    async def _process_batch(self, cache_key: str):
        if cache_key in self._batch_tasks:
            self._batch_tasks[cache_key].cancel()
            del self._batch_tasks[cache_key]

        batch = self._request_batches[cache_key]
        self._request_batches[cache_key] = []

        if not batch:
            return

        try:
            start_time = time.time()
            cached_response = await self.service_mesh.get_cached_response(cache_key)

            if cached_response:
                decompressed = self._decompress_if_needed(cached_response)
                for future in batch:
                    if not future.done():
                        future.set_result(decompressed)
            else:
                # Handle cache miss for batch
                response = await self._fetch_and_cache(cache_key)
                for future in batch:
                    if not future.done():
                        future.set_result(response)

            # Update batch metrics
            duration = time.time() - start_time
            self.analytics['performance']['batch_metrics']['batch_sizes'].append(len(batch))
            self.analytics['performance']['batch_metrics']['batch_latencies'].append(duration / len(batch))

        except Exception as e:
            logger.error(f"Error processing batch for {cache_key}: {e}")
            for future in batch:
                if not future.done():
                    future.set_exception(e)

    def _compress_if_needed(self, content: str) -> str:
        if len(content) > self.compression_threshold:
            original_size = len(content.encode())
            compressed = zlib.compress(content.encode(), level=self.compression_level)
            compressed_size = len(compressed)
            
            # Update compression metrics
            self.analytics['memory_usage']['compression_savings'] += (original_size - compressed_size)
            self.analytics['performance']['batch_metrics']['compression_ratio'] = \
                compressed_size / original_size if original_size > 0 else 1
            
            return f"compressed:{compressed.decode('latin1')}"
        return content

    def _decompress_if_needed(self, content: str) -> str:
        if content.startswith('compressed:'):
            compressed = content[11:].encode('latin1')
            return zlib.decompress(compressed).decode()
        return content

    async def _schedule_batch(self, cache_key: str):
        await asyncio.sleep(self.batch_timeout)
        await self._process_batch(cache_key)

    async def get_cached_response(self, cache_key: str) -> str:
        future = asyncio.Future()
        self._request_batches[cache_key].append(future)

        if len(self._request_batches[cache_key]) >= self.batch_size:
            await self._process_batch(cache_key)
        elif cache_key not in self._batch_tasks:
            self._batch_tasks[cache_key] = asyncio.create_task(
                self._schedule_batch(cache_key)
            )

        return await future

    async def warm_cache(self, paths: list[str]):
        """Pre-warm cache for frequently accessed paths"""
        for path in paths:
            if path not in self.analytics['warm_cache']:
                try:
                    response = await self._fetch_and_cache(path)
                    if response:
                        self.analytics['warm_cache'].add(path)
                        logger.info(f"Warmed cache for {path}")
                except Exception as e:
                    logger.error(f"Error warming cache for {path}: {e}")

    async def _fetch_and_cache(self, path: str) -> bool:
        """Fetch and cache content for a given path"""
        try:
            # Create a simulated request object
            mock_request = Request(scope={
                'type': 'http',
                'method': 'GET',
                'path': path,
                'query_string': b'',
                'headers': [(b'host', b'localhost')]
            })

            # Generate cache key
            cache_key = self._generate_cache_key(mock_request)

            # Simulate the request to get fresh content
            async def mock_call_next(request):
                return Response(
                    content=json.dumps({"status": "success", "path": path}),
                    media_type="application/json"
                )

            response = await mock_call_next(mock_request)

            # Cache the response
            if 200 <= response.status_code < 300:
                content = await response.body()
                content_str = content.decode()

                # Apply compression if needed
                if len(content_str) > 1024:
                    compressed = zlib.compress(content_str.encode())
                    content_str = 'compressed:' + compressed.decode('latin1')

                # Use default TTL for warm cache
                await self.service_mesh.cache_response(
                    cache_key,
                    content_str,
                    ttl=300  # 5 minutes default TTL
                )
                return True

            return False
        except Exception as e:
            logger.error(f"Error fetching content for {path}: {e}")
            return False

    def _generate_cache_key_from_path(self, path: str) -> str:
        """Generate cache key from path only"""
        return hashlib.md5(path.encode()).hexdigest()

    async def __call__(self, request: Request, call_next: Callable) -> Response:
        # Cleanup hit counters periodically
        if (datetime.now() - self.last_cleanup).seconds > 3600:  # Every hour
            self._analyze_and_warm_cache()
            self.hit_counters = {}
            self.last_cleanup = datetime.now()

        # Only cache GET requests
        if request.method != "GET":
            return await call_next(request)

        cache_key = self._generate_cache_key(request)
        path = request.url.path

        # Try to get from cache
        cached_response = await self.service_mesh.get_cached_response(cache_key)
        if cached_response:
            # Update analytics
            self.analytics['hits'][path] = self.analytics['hits'].get(path, 0) + 1
            self.hit_counters[cache_key] = self.hit_counters.get(cache_key, 0) + 1
            logger.info(f"Cache hit for {path} (hits: {self.hit_counters[cache_key]})")
            
            # Handle decompression
            if cached_response.startswith('compressed:'):
                try:
                    compressed_data = cached_response[10:].encode('latin1')
                    cached_response = zlib.decompress(compressed_data).decode('utf-8')
                except Exception as e:
                    logger.error(f"Error decompressing cache: {e}")
                    return await call_next(request)

            return Response(
                content=cached_response,
                media_type="application/json"
            )
        else:
            # Update miss counter
            self.analytics['misses'][path] = self.analytics['misses'].get(path, 0) + 1

        # Get fresh response
        response = await call_next(request)

        # Cache the response if it's successful
        if 200 <= response.status_code < 300:
            try:
                # Get response body
                response_body = [section async for section in response.body_iterator]
                response.body_iterator = iter(response_body)

                # Cache response with compression if needed
                content = b''.join(response_body)
                content_str = content.decode()
                
                # Compress if content is large
                if len(content_str) > 1024:  # Compress if larger than 1KB
                    compressed = zlib.compress(content_str.encode())
                    content_str = 'compressed:' + compressed.decode('latin1')

                # Calculate adaptive TTL based on hit rate
                hit_count = self.hit_counters.get(cache_key, 0)
                base_ttl = 300  # 5 minutes base TTL
                adaptive_ttl = min(base_ttl * (1 + (hit_count // 10)), 3600)  # Max 1 hour

                await self.service_mesh.cache_response(
                    cache_key,
                    content_str,
                    ttl=adaptive_ttl
                )

            except Exception as e:
                logger.error(f"Error caching response: {e}")

        return response

    async def _analyze_and_warm_cache(self):
        """Analyze cache patterns and warm frequently accessed paths"""
        try:
            # Resource cleanup based on memory usage
            current_size = self.analytics['memory_usage']['cache_size']
            if current_size > self.memory_limit:
                await self._cleanup_least_used()

            # Find paths with high miss rates
            paths_to_warm = []
            for path, misses in self.analytics['misses'].items():
                hits = self.analytics['hits'].get(path, 0)
                total = hits + misses
                if total > 10 and (misses / total) > 0.3:  # More than 30% miss rate
                    paths_to_warm.append(path)

            # Warm cache for identified paths
            if paths_to_warm:
                logger.info(f"Warming cache for paths: {paths_to_warm}")
                asyncio.create_task(self.warm_cache(paths_to_warm))

            # Update performance metrics
            if self.analytics['performance']['total_requests'] > 0:
                self.analytics['performance']['avg_response_time'] = (
                    self.analytics['performance']['avg_response_time'] * 0.7 +
                    self.analytics['performance']['total_requests'] * 0.3
                )

            # Reset analytics for next period
            self.analytics['hits'] = {}
            self.analytics['misses'] = {}
            self.analytics['warm_cache'] = set()
            self.analytics['performance']['total_requests'] = 0

        except Exception as e:
            logger.error(f"Error in cache analysis: {e}")

    async def _cleanup_least_used(self):
        """Clean up least used cache entries"""
        try:
            # Sort cache entries by hit count
            sorted_entries = sorted(
                self.hit_counters.items(),
                key=lambda x: x[1]
            )

            # Remove bottom 20% of least used entries
            entries_to_remove = sorted_entries[:len(sorted_entries) // 5]
            for cache_key, _ in entries_to_remove:
                await self.service_mesh.delete_cached_response(cache_key)
                self.hit_counters.pop(cache_key, None)

            logger.info(f"Cleaned up {len(entries_to_remove)} least used cache entries")
        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")

    def _generate_cache_key(self, request: Request) -> str:
        """Generate a unique cache key for the request"""
        # Combine path and query params
        key_parts = [
            request.url.path,
            str(sorted(request.query_params.items()))
        ]

        # Create hash
        key_string = json.dumps(key_parts, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()

    async def _compress_response(self, response_data: bytes) -> bytes:
        """Compress response data if it exceeds the threshold."""
        if len(response_data) > self.compression_threshold:
            compressed = zlib.compress(response_data, level=self.compression_level)
            compression_ratio = len(compressed) / len(response_data)
            self.analytics['memory_usage']['compression_savings'] += (len(response_data) - len(compressed))
            self.analytics['performance']['batch_metrics']['compression_ratio'] = compression_ratio
            return compressed
        return response_data

    async def _decompress_if_needed(self, data: bytes) -> bytes:
        """Decompress data if it was compressed."""
        try:
            return zlib.decompress(data)
        except zlib.error:
            return data

    async def _fetch_and_cache(self, cache_key: str) -> bytes:
        """Fetch response from service and cache it with compression."""
        response = await self.service_mesh.fetch_response(cache_key)
        compressed = await self._compress_response(response)
        await self.service_mesh.cache_response(cache_key, compressed)
        return response

    async def _schedule_batch_processing(self, cache_key: str):
        """Schedule batch processing with timeout."""
        if cache_key not in self._batch_tasks:
            self._batch_tasks[cache_key] = asyncio.create_task(
                asyncio.sleep(self.batch_timeout)
            )
            await self._batch_tasks[cache_key]
            await self._process_batch(cache_key)