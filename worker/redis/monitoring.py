import asyncio
import logging
import time
from typing import Dict, Any, Optional
from redis.asyncio import Redis

from .prometheus_metrics import get_prometheus_metrics

logger = logging.getLogger(__name__)

class RedisMonitor:
    """Redis monitoring class for tracking connection health and performance metrics."""
    
    def __init__(self, redis_client: Redis):
        self._redis = redis_client
        self._metrics: Dict[str, Any] = {
            "connection_attempts": 0,
            "connection_failures": 0,
            "last_connection_time": None,
            "avg_response_time": 0,
            "total_commands": 0,
            "failed_commands": 0,
            "last_error": None,
            "uptime": 0,
            "start_time": time.time()
        }
        self._monitoring_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._prometheus = get_prometheus_metrics()
    
    async def start_monitoring(self):
        """Start the Redis monitoring process."""
        if not self._is_running:
            self._is_running = True
            self._monitoring_task = asyncio.create_task(self._monitor_loop())
            logger.info("Redis monitoring started")
    
    async def stop_monitoring(self):
        """Stop the Redis monitoring process."""
        self._is_running = False
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Redis monitoring stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop that collects metrics periodically."""
        while self._is_running:
            try:
                await self._collect_metrics()
                await asyncio.sleep(60)  # Collect metrics every minute
            except Exception as e:
                logger.error(f"Error in Redis monitoring loop: {str(e)}")
                await asyncio.sleep(10)  # Shorter interval on error
    
    async def _collect_metrics(self):
        """Collect Redis performance metrics."""
        try:
            # Measure response time
            start_time = time.time()
            await self._redis.ping()
            response_time = time.time() - start_time
            
            # Update metrics
            self._metrics["last_connection_time"] = time.time()
            self._metrics["connection_attempts"] += 1
            
            # Record connection success in Prometheus if enabled
            if self._prometheus.enabled:
                self._prometheus.record_connection_attempt(success=True)
                self._prometheus.record_operation("ping", success=True, duration=response_time)
            
            # Calculate rolling average response time
            total_commands = self._metrics["total_commands"]
            if total_commands > 0:
                self._metrics["avg_response_time"] = (
                    (self._metrics["avg_response_time"] * total_commands + response_time) / 
                    (total_commands + 1)
                )
            else:
                self._metrics["avg_response_time"] = response_time
            
            self._metrics["total_commands"] += 1
            self._metrics["uptime"] = time.time() - self._metrics["start_time"]
            
            # Collect Redis info if available
            try:
                info = await self._redis.info()
                self._metrics["redis_info"] = {
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory": info.get("used_memory", 0),
                    "total_connections_received": info.get("total_connections_received", 0),
                    "uptime_in_seconds": info.get("uptime_in_seconds", 0),
                    "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0)
                }
                
                # Update Prometheus metrics with Redis info if enabled
                if self._prometheus.enabled:
                    self._prometheus.update_health_metrics(info, True)
            except Exception as e:
                logger.warning(f"Could not collect Redis info: {str(e)}")
                
        except Exception as e:
            self._metrics["connection_failures"] += 1
            self._metrics["failed_commands"] += 1
            self._metrics["last_error"] = str(e)
            
            # Record connection failure in Prometheus
            self._prometheus.record_connection_attempt(success=False)
            self._prometheus.record_operation("ping", success=False)
            
            logger.error(f"Error collecting Redis metrics: {str(e)}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get the current Redis metrics."""
        # Add calculated metrics
        metrics = self._metrics.copy()
        metrics["failure_rate"] = 0
        if metrics["total_commands"] > 0:
            metrics["failure_rate"] = metrics["failed_commands"] / metrics["total_commands"]
        
        # Add health status
        metrics["health_status"] = "healthy"
        if metrics["failure_rate"] > 0.1:  # More than 10% failure rate
            metrics["health_status"] = "degraded"
        if metrics["connection_failures"] > 5:  # Multiple connection failures
            metrics["health_status"] = "unhealthy"
            
        return metrics
    
    async def check_health(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            start_time = time.time()
            await self._redis.ping()
            response_time = time.time() - start_time
            
            # Update metrics
            self._metrics["last_connection_time"] = time.time()
            self._metrics["connection_attempts"] += 1
            
            # Record in Prometheus
            self._prometheus.record_connection_attempt(success=True)
            self._prometheus.record_operation("health_check", success=True, duration=response_time)
            
            # Consider connection unhealthy if response time is too high
            if response_time > 1.0:  # More than 1 second response time
                logger.warning(f"Redis response time is high: {response_time:.2f}s")
                return False
                
            return True
        except Exception as e:
            self._metrics["connection_failures"] += 1
            self._metrics["last_error"] = str(e)
            
            # Record in Prometheus
            self._prometheus.record_connection_attempt(success=False)
            self._prometheus.record_operation("health_check", success=False)
            
            logger.error(f"Redis health check failed: {str(e)}")
            return False

# Factory function to create a monitor instance
async def create_redis_monitor(redis_client: Redis) -> RedisMonitor:
    """Create and initialize a Redis monitor instance."""
    monitor = RedisMonitor(redis_client)
    await monitor.start_monitoring()
    return monitor