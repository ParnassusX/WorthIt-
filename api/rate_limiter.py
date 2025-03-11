import time
import logging
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from typing import Dict, List, Set, Optional, Callable, Awaitable
from collections import defaultdict
import redis
import json
import os
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger(__name__)

class RateLimiter:
    """Enhanced rate limiter with adaptive thresholds and suspicious behavior detection"""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        # Use provided Redis client or create a new one
        self.redis = redis_client
        self.default_limit = 60  # Default requests per minute
        self.endpoint_limits = {
            "/api/analyze": 30,  # Resource-intensive endpoint
            "/api/analyze-image": 20,  # Very resource-intensive endpoint
            "/api/health": 120,  # Health checks can be more frequent
        }
        self.window_size = 60  # 1 minute window
        self.block_duration = 30 * 60  # 30 minutes block
        self.suspicious_threshold = 3  # Number of suspicious activities before blocking
        
        # In-memory fallback if Redis is not available
        self._local_counters = defaultdict(lambda: defaultdict(list))
        self._blocked_ips = set()
        self._suspicious_activity = defaultdict(int)
        self._last_cleanup = time.time()
    
    async def _get_redis_key(self, ip: str, endpoint: str) -> str:
        """Generate Redis key for rate limiting"""
        return f"ratelimit:{ip}:{endpoint}:{int(time.time() / self.window_size)}"
    
    async def _get_block_key(self, ip: str) -> str:
        """Generate Redis key for blocked IPs"""
        return f"blocked:{ip}"
    
    async def _is_blocked_redis(self, ip: str) -> bool:
        """Check if IP is blocked using Redis"""
        if not self.redis:
            return False
        
        try:
            return bool(self.redis.exists(await self._get_block_key(ip)))
        except Exception as e:
            logger.error(f"Redis error checking blocked status: {e}")
            return False
    
    async def _is_blocked_local(self, ip: str) -> bool:
        """Check if IP is blocked using local memory"""
        return ip in self._blocked_ips
    
    async def _increment_redis(self, ip: str, endpoint: str) -> int:
        """Increment request counter in Redis and return current count"""
        if not self.redis:
            return 0
        
        try:
            key = await self._get_redis_key(ip, endpoint)
            count = self.redis.incr(key)
            # Set expiration if this is a new key
            if count == 1:
                self.redis.expire(key, self.window_size * 2)  # Double window size for safety
            return count
        except Exception as e:
            logger.error(f"Redis error incrementing counter: {e}")
            return 0
    
    async def _increment_local(self, ip: str, endpoint: str) -> int:
        """Increment request counter locally and return current count"""
        current_time = time.time()
        
        # Clean up old records
        if current_time - self._last_cleanup > self.window_size:
            await self._cleanup_local()
        
        # Add current request timestamp
        self._local_counters[ip][endpoint].append(current_time)
        
        # Count requests within window
        count = sum(1 for t in self._local_counters[ip][endpoint] 
                   if current_time - t < self.window_size)
        
        return count
    
    async def _block_ip_redis(self, ip: str, reason: str) -> None:
        """Block an IP in Redis"""
        if not self.redis:
            return
        
        try:
            key = await self._get_block_key(ip)
            self.redis.setex(key, self.block_duration, reason)
            logger.warning(f"IP blocked in Redis: {ip}, Reason: {reason}")
        except Exception as e:
            logger.error(f"Redis error blocking IP: {e}")
    
    async def _block_ip_local(self, ip: str, reason: str) -> None:
        """Block an IP locally"""
        self._blocked_ips.add(ip)
        logger.warning(f"IP blocked locally: {ip}, Reason: {reason}")
    
    async def _cleanup_local(self) -> None:
        """Clean up old request records"""
        current_time = time.time()
        self._last_cleanup = current_time
        
        # Clean up request counters
        for ip in list(self._local_counters.keys()):
            for endpoint in list(self._local_counters[ip].keys()):
                self._local_counters[ip][endpoint] = [
                    t for t in self._local_counters[ip][endpoint]
                    if current_time - t < self.window_size
                ]
                if not self._local_counters[ip][endpoint]:
                    del self._local_counters[ip][endpoint]
            if not self._local_counters[ip]:
                del self._local_counters[ip]
    
    async def _detect_suspicious_pattern(self, request: Request) -> bool:
        """Detect suspicious request patterns"""
        ip = request.client.host
        endpoint = request.url.path
        headers = request.headers
        
        # Check for rapid successive requests
        if ip in self._local_counters and endpoint in self._local_counters[ip]:
            recent_requests = [t for t in self._local_counters[ip][endpoint] 
                              if time.time() - t < 1]  # Requests in the last second
            if len(recent_requests) >= 10:  # More than 10 requests per second
                return True
        
        # Check for suspicious headers or patterns
        suspicious_patterns = [
            not headers.get('User-Agent'),
            headers.get('User-Agent', '').lower() in ['', 'python-requests', 'curl'],
            not headers.get('Accept'),
            headers.get('X-Forwarded-For') and headers.get('X-Forwarded-For') != ip
        ]
        
        return sum(suspicious_patterns) >= 2
    
    async def is_rate_limited(self, request: Request) -> bool:
        """Check if a request should be rate limited"""
        ip = request.client.host
        endpoint = request.url.path
        
        # Check if IP is blocked
        if await self._is_blocked_redis(ip) or await self._is_blocked_local(ip):
            return True
        
        # Detect suspicious patterns
        if await self._detect_suspicious_pattern(request):
            self._suspicious_activity[ip] += 1
            logger.warning(f"Suspicious activity detected from IP: {ip}, Count: {self._suspicious_activity[ip]}")
            
            if self._suspicious_activity[ip] >= self.suspicious_threshold:
                reason = "Suspicious activity detected"
                await self._block_ip_redis(ip, reason)
                await self._block_ip_local(ip, reason)
                return True
        
        # Get rate limit for this endpoint
        limit = self.endpoint_limits.get(endpoint, self.default_limit)
        
        # Try Redis first, fall back to local counter
        count = await self._increment_redis(ip, endpoint)
        if count == 0:  # Redis failed
            count = await self._increment_local(ip, endpoint)
        
        # Check if limit exceeded
        if count > limit:
            reason = f"Rate limit exceeded: {count}/{limit} requests"
            await self._block_ip_redis(ip, reason)
            await self._block_ip_local(ip, reason)
            logger.warning(f"Rate limit exceeded for IP: {ip}, Endpoint: {endpoint}, Count: {count}/{limit}")
            return True
        
        # Add rate limit headers to response
        return False

async def rate_limit_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Middleware to apply rate limiting to all requests"""
    # Get Redis client from app state or create a new one
    redis_url = os.getenv("REDIS_URL")
    redis_client = None
    
    if redis_url:
        try:
            # Use SSL if using Upstash Redis or if URL starts with rediss://
            use_ssl = "upstash.io" in redis_url or redis_url.startswith("rediss://")
            redis_client = redis.Redis.from_url(
                redis_url,
                ssl=use_ssl,
                decode_responses=True
            )
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
    
    # Create rate limiter
    rate_limiter = RateLimiter(redis_client)
    
    # Check if request should be rate limited
    if await rate_limiter.is_rate_limited(request):
        return JSONResponse(
            status_code=429,
            content={
                "error": "Too many requests",
                "detail": "Rate limit exceeded. Please try again later."
            },
            headers={
                "Retry-After": "60",
                "X-RateLimit-Limit": str(rate_limiter.default_limit),
                "X-RateLimit-Reset": str(int(time.time() + 60))
            }
        )
    
    # Process the request
    response = await call_next(request)
    
    return response

def create_rate_limit_middleware():
    """Factory function to create the rate limit middleware.
    
    This function is imported in main.py to add rate limiting to all endpoints.
    
    Returns:
        Callable: The rate limit middleware function
    """
    async def middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        return await rate_limit_middleware(request, call_next)
    
    return middleware