import os
import logging
from typing import Dict, Optional, List
from fastapi import FastAPI
from datetime import datetime, timedelta
import httpx
import asyncio
from collections import defaultdict
from worker.redis_manager import RedisConnectionManager

logger = logging.getLogger(__name__)

class ServiceMesh:
    def __init__(self, app: FastAPI):
        self.app = app
        self._redis_manager = RedisConnectionManager()
        self.redis = None
        self.service_registry: Dict[str, dict] = {}
        self.analytics_manager = ServiceAnalytics()
        self.circuit_breaker_manager = CircuitBreakerManager()
        self.request_batcher = RequestBatcher()
        self.compression_enabled = True
        self.compression_threshold = 1024  # Compress responses larger than 1KB
        self.scaling_config = {
            'min_instances': 1,
            'max_instances': 5,
            'scale_up_threshold': 0.8,
            'scale_down_threshold': 0.3,
            'cooldown_period': 300,
            'metrics_window': 60,  # 1 minute window for metrics
            'cpu_threshold': 70,    # Scale up at 70% CPU
            'memory_threshold': 80   # Scale up at 80% memory
        }
        self.circuit_breaker_config = {
            'failure_threshold': 5,
            'reset_timeout': 60,
            'half_open_timeout': 30,
            'success_threshold': 2,
            'error_threshold_percentage': 50,  # Trip at 50% error rate
            'min_request_threshold': 20,       # Minimum requests before tripping
            'sliding_window_size': 100,        # Last 100 requests
            'sliding_window_time': 60          # Or last 60 seconds
        }
        self.last_scale_action = datetime.now()
        # No method calls here
        
    def _initialize_monitoring(self):
        # Placeholder implementation for monitoring initialization
        logger.info("Initializing service mesh monitoring")
        pass
        
    async def register_service(self, service_name, host, port=None):
        # Placeholder implementation
        logger.info(f"Registered service: {service_name} at {host}:{port}")
        self.service_registry[service_name] = {
            'host': host,
            'port': port,
            'last_heartbeat': datetime.now(),
            'status': 'active'
        }
        return True

    async def deregister_service(self, service_name: str, service_id: str):
        """Remove a service from the registry"""
        await self._ensure_redis_connection()
        try:
            await self.redis.hdel(f'service_registry:{service_name}', service_id)
            self.service_registry.pop(service_id, None)
            logger.info(f"Deregistered service: {service_id}")
        except Exception as e:
            logger.error(f"Failed to deregister service {service_id}: {e}")

    def _handle_failure(self, circuit_key: str, circuit: dict) -> None:
        """Handle service failure and update circuit breaker"""
        circuit['failures'] += 1
        circuit['last_failure'] = datetime.now()

        if circuit['failures'] >= 3:  # Three strikes rule
            circuit['state'] = 'open'
            self.analytics['circuit_breaks'] += 1
        
        self.circuit_breakers[circuit_key] = circuit

    async def get_service(self, service_name: str, strategy: str = 'round_robin') -> Optional[dict]:
        """Get service details with advanced load balancing and analytics"""
        await self._ensure_redis_connection()
        try:
            services = await self.redis.hgetall(f'service_registry:{service_name}')
            if not services:
                return None

            service_list = [eval(s) for s in services.values()]
            healthy_services = [s for s in service_list if s['status'] == 'healthy']
            
            if not healthy_services:
                return None

            if strategy == 'least_connections':
                # Select service with least active connections
                return min(healthy_services, key=lambda s: s.get('active_connections', 0))
            elif strategy == 'weighted':
                # Weighted selection based on health metrics
                total_weight = sum(s.get('weight', 1) for s in healthy_services)
                if total_weight == 0:
                    return healthy_services[0]
                
                point = int(datetime.now().timestamp()) % total_weight
                for service in healthy_services:
                    if point <= service.get('weight', 1):
                        return service
                    point -= service.get('weight', 1)
                return healthy_services[0]
            elif strategy == 'response_time':
                # Select based on recent response times
                return min(healthy_services, 
                          key=lambda s: s.get('last_response_time', float('inf')))
            else:  # Default to round-bin
                current_time = datetime.now().timestamp()
                selected_index = int(current_time) % len(healthy_services)
                return healthy_services[selected_index]

        except Exception as e:
            logger.error(f"Error getting service {service_name}: {e}")
            return None

    async def cache_response(self, key: str, value: str, ttl: int = None):
        """Cache response with size and count limits for free tier"""
        await self._ensure_redis_connection()
        try:
            # Check cache size limits
            current_cache_size = await self.redis.dbsize()
            if current_cache_size >= self.cache_config['max_cache_size']:
                # Remove oldest entries if cache is full
                oldest_keys = await self.redis.keys('cache:*')
                # Get timestamps for all keys first
                timestamps = []
                for key in oldest_keys:
                    ts = await self.redis.get(f'{key}:timestamp')
                    timestamps.append((key, float(ts or 0)))
                # Sort based on timestamps
                timestamps.sort(key=lambda x: x[1])
                # Remove oldest entries
                for key, _ in timestamps[:10]:  # Remove 10 oldest entries
                    await self.redis.delete(key)

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

    async def check_scaling_needs(self):
        """Check if services need scaling based on metrics"""
        now = datetime.now()
        if (now - self.last_scale_action).total_seconds() < self.scaling_config['cooldown_period']:
            return

        for service_name in self.service_registry:
            metrics = self.analytics_manager.get_service_metrics(service_name)
            current_instances = len([s for s in self.service_registry.values() 
                                   if s['name'] == service_name and s['status'] == 'healthy'])

            # Check for scale up
            if metrics['resource_utilization'] > self.scaling_config['scale_up_threshold'] \
               and current_instances < self.scaling_config['max_instances']:
                await self._scale_service(service_name, 'up')
                self.last_scale_action = now

            # Check for scale down
            elif metrics['resource_utilization'] < self.scaling_config['scale_down_threshold'] \
                 and current_instances > self.scaling_config['min_instances']:
                await self._scale_service(service_name, 'down')
                self.last_scale_action = now

    async def _scale_service(self, service_name: str, direction: str):
        """Scale a service up or down"""
        try:
            if direction == 'up':
                # Logic to scale up service (e.g., spawn new instance)
                new_port = self._get_next_available_port(service_name)
                await self.register_service(
                    service_name,
                    'localhost',  # For local development
                    new_port,
                    '/health'
                )
                logger.info(f"Scaled up {service_name} with new instance on port {new_port}")

            else:  # scale down
                # Find least utilized instance
                instances = [s for s in self.service_registry.values() 
                            if s['name'] == service_name and s['status'] == 'healthy']
                if instances:
                    least_utilized = min(instances, 
                                        key=lambda x: x.get('resource_utilization', float('inf')))
                    await self.deregister_service(service_name, 
                                                 f"{service_name}_{least_utilized['host']}_{least_utilized['port']}")
                    logger.info(f"Scaled down {service_name} by removing instance on port {least_utilized['port']}")

        except Exception as e:
            logger.error(f"Error scaling {service_name} {direction}: {e}")

    def _get_next_available_port(self, service_name: str) -> int:
        """Get next available port for new service instance"""
        used_ports = set()
        for service in self.service_registry.values():
            if service['name'] == service_name:
                used_ports.add(service['port'])
        
        # Start from base port (e.g., 8000) and find next available
        base_port = 8000
        while base_port in used_ports:
            base_port += 1
        return base_port

class CircuitBreakerManager:
    def __init__(self):
        self.circuits = {}
        self.failure_threshold = 3
        self.reset_timeout = 30  # seconds
        self.half_open_timeout = 15  # seconds
        self.monitoring_window = timedelta(minutes=5)
        self.recovery_times = defaultdict(list)
        self.degradation_threshold = 0.8  # 80% of failure threshold
        self.alert_threshold = 0.9  # 90% of failure threshold

    def get_circuit_state(self, service_id: str) -> str:
        if service_id not in self.circuits:
            self.circuits[service_id] = {
                'failures': 0,
                'last_failure': None,
                'state': 'closed',
                'last_state_change': datetime.now()
            }
        return self.circuits[service_id]['state']

    def record_failure(self, service_id: str) -> None:
        circuit = self.circuits.get(service_id, {
            'failures': 0,
            'last_failure': None,
            'state': 'closed',
            'last_state_change': datetime.now()
        })

        circuit['failures'] += 1
        circuit['last_failure'] = datetime.now()

        if circuit['failures'] >= self.failure_threshold and circuit['state'] == 'closed':
            circuit['state'] = 'open'
            circuit['last_state_change'] = datetime.now()
            logger.warning(f"Circuit breaker opened for service {service_id}")

        self.circuits[service_id] = circuit

    def record_success(self, service_id: str) -> None:
        if service_id in self.circuits:
            circuit = self.circuits[service_id]
            if circuit['state'] == 'half-open':
                circuit['state'] = 'closed'
                circuit['failures'] = 0
                circuit['degradation_level'] = 0.0
                circuit['recovery_attempts'] = 0
                circuit['last_state_change'] = datetime.now()
                self.recovery_times[service_id].append(
                    (datetime.now() - circuit['last_failure']).total_seconds()
                )
                logger.info(f"Circuit breaker closed for service {service_id}")

    def check_state_transition(self, service_id: str) -> None:
        if service_id not in self.circuits:
            return

        circuit = self.circuits[service_id]
        now = datetime.now()

        if circuit['state'] == 'open':
            if (now - circuit['last_state_change']).total_seconds() >= self.reset_timeout:
                circuit['state'] = 'half-open'
                circuit['recovery_attempts'] += 1
                circuit['last_state_change'] = now
                logger.info(f"Circuit breaker half-open for service {service_id} (attempt {circuit['recovery_attempts']})")

        self.circuits[service_id] = circuit