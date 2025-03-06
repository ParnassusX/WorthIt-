import os
import logging
from typing import Dict, Optional
from fastapi import FastAPI
from redis.asyncio import Redis
from datetime import datetime, timedelta
import httpx
import asyncio

logger = logging.getLogger(__name__)

class ServiceMesh:
    def __init__(self, app: FastAPI, redis_client: Redis):
        self.app = app
        self.redis = redis_client
        self.service_registry: Dict[str, dict] = {}
        self.cache_config = {
            'default_ttl': 300,  # 5 minutes default TTL
            'max_cache_size': 1000,  # Maximum number of cache entries for free tier
            'max_item_size': 512000  # 512KB max size per cached item
        }
        self.circuit_breakers = {}
        self.health_check_interval = 30  # seconds
        self._start_health_check_loop()

    def _start_health_check_loop(self):
        """Start the background health check loop"""
        asyncio.create_task(self._health_check_loop())

    async def _health_check_loop(self):
        """Continuous health check loop"""
        while True:
            await self.health_check()
            await asyncio.sleep(self.health_check_interval)

    async def _check_service_health(self, service_info: dict) -> bool:
        """Check health of a specific service"""
        try:
            async with httpx.AsyncClient() as client:
                url = f"http://{service_info['host']}:{service_info['port']}{service_info['health_check_path']}"
                response = await client.get(url, timeout=5.0)
                return 200 <= response.status_code < 300
        except Exception as e:
            logger.error(f"Health check failed for {service_info['name']}: {e}")
            return False

    async def register_service(self, service_name: str, host: str, port: int, health_check_path: str = '/health'):
        """Register a service with the mesh"""
        service_id = f"{service_name}_{host}_{port}"
        service_info = {
            'name': service_name,
            'host': host,
            'port': port,
            'health_check_path': health_check_path,
            'last_health_check': datetime.now().isoformat(),
            'status': 'healthy'
        }
        
        try:
            await self.redis.hset(
                f'service_registry:{service_name}',
                service_id,
                str(service_info)
            )
            self.service_registry[service_id] = service_info
            logger.info(f"Registered service: {service_id}")
        except Exception as e:
            logger.error(f"Failed to register service {service_id}: {e}")

    async def deregister_service(self, service_name: str, service_id: str):
        """Remove a service from the registry"""
        try:
            await self.redis.hdel(f'service_registry:{service_name}', service_id)
            self.service_registry.pop(service_id, None)
            logger.info(f"Deregistered service: {service_id}")
        except Exception as e:
            logger.error(f"Failed to deregister service {service_id}: {e}")

    async def get_service(self, service_name: str) -> Optional[dict]:
        """Get service details with basic load balancing"""
        try:
            services = await self.redis.hgetall(f'service_registry:{service_name}')
            if not services:
                return None

            # Simple round-robin load balancing
            service_list = [eval(s) for s in services.values()]
            healthy_services = [s for s in service_list if s['status'] == 'healthy']
            
            if not healthy_services:
                return None

            # Use timestamp for round-robin selection
            current_time = datetime.now().timestamp()
            selected_index = int(current_time) % len(healthy_services)
            return healthy_services[selected_index]

        except Exception as e:
            logger.error(f"Error getting service {service_name}: {e}")
            return None

    async def cache_response(self, key: str, value: str, ttl: int = None):
        """Cache response with size and count limits for free tier"""
        try:
            # Check cache size limits
            current_cache_size = await self.redis.dbsize()
            if current_cache_size >= self.cache_config['max_cache_size']:
                # Remove oldest entries if cache is full
                oldest_keys = await self.redis.keys('cache:*')
                oldest_keys.sort(key=lambda x: float(await self.redis.get(f'{x}:timestamp') or 0))
                for old_key in oldest_keys[:10]:  # Remove 10 oldest entries
                    await self.redis.delete(old_key)

            # Check item size
            if len(value.encode()) > self.cache_config['max_item_size']:
                logger.warning(f"Cache item too large for key {key}")
                return False

            # Set cache with TTL
            ttl = ttl or self.cache_config['default_ttl']
            await self.redis.setex(f'cache:{key}', ttl, value)
            await self.redis.set(f'cache:{key}:timestamp', datetime.now().timestamp())
            return True

        except Exception as e:
            logger.error(f"Cache error for key {key}: {e}")
            return False

    async def get_cached_response(self, key: str) -> Optional[str]:
        """Retrieve cached response"""
        try:
            return await self.redis.get(f'cache:{key}')
        except Exception as e:
            logger.error(f"Error retrieving cache for key {key}: {e}")
            return None

    async def health_check(self):
        """Perform health checks on registered services"""
        for service_id, service_info in self.service_registry.items():
            try:
                is_healthy = await self._check_service_health(service_info)
                service_info['status'] = 'healthy' if is_healthy else 'unhealthy'
                service_info['last_health_check'] = datetime.now().isoformat()
                
                # Update circuit breaker status
                if not is_healthy:
                    self.circuit_breakers[service_id] = self.circuit_breakers.get(service_id, 0) + 1
                    if self.circuit_breakers[service_id] >= 3:  # Circuit breaks after 3 failures
                        service_info['status'] = 'circuit_broken'
                else:
                    self.circuit_breakers[service_id] = 0

                await self.redis.hset(
                    f'service_registry:{service_info["name"]}',
                    service_id,
                    str(service_info)
                )
                
                # Log status changes
                logger.info(
                    f"Health check for {service_id}: {service_info['status']}",
                    extra={
                        'service_id': service_id,
                        'status': service_info['status'],
                        'failures': self.circuit_breakers.get(service_id, 0)
                    }
                )
                
            except Exception as e:
                logger.error(f"Health check failed for {service_id}: {e}")
                service_info['status'] = 'unhealthy'