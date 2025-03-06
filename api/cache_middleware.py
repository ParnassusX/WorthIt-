import logging
from typing import Callable
from fastapi import Request, Response
from api.service_mesh import ServiceMesh
import hashlib
import json
import zlib
from datetime import datetime

logger = logging.getLogger(__name__)

class CacheMiddleware:
    def __init__(self, service_mesh: ServiceMesh):
        self.service_mesh = service_mesh
        self.hit_counters = {}
        self.last_cleanup = datetime.now()

    async def __call__(self, request: Request, call_next: Callable) -> Response:
        # Cleanup hit counters periodically
        if (datetime.now() - self.last_cleanup).seconds > 3600:  # Every hour
            self.hit_counters = {}
            self.last_cleanup = datetime.now()

        # Only cache GET requests
        if request.method != "GET":
            return await call_next(request)

        # Generate cache key from request
        cache_key = self._generate_cache_key(request)

        # Try to get from cache
        cached_response = await self.service_mesh.get_cached_response(cache_key)
        if cached_response:
            # Decompress if needed
            if cached_response.startswith('compressed:'):
                try:
                    compressed_data = cached_response[10:].encode('latin1')
                    cached_response = zlib.decompress(compressed_data).decode('utf-8')
                except Exception as e:
                    logger.error(f"Error decompressing cache: {e}")
                    return await call_next(request)

            # Update hit counter for adaptive TTL
            self.hit_counters[cache_key] = self.hit_counters.get(cache_key, 0) + 1
            logger.info(f"Cache hit for {request.url.path} (hits: {self.hit_counters[cache_key]})")
            
            return Response(
                content=cached_response,
                media_type="application/json"
            )

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