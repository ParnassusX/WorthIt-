import logging
import time
from typing import Dict, Any, Optional

try:
    import prometheus_client
    from prometheus_client import Counter, Gauge, Histogram
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

logger = logging.getLogger(__name__)

class RedisPrometheusMetrics:
    """Prometheus metrics integration for Redis monitoring.
    
    This class provides Prometheus metrics for Redis operations and health,
    enabling better observability and monitoring through Prometheus-compatible
    systems.
    """
    
    def __init__(self):
        self.enabled = PROMETHEUS_AVAILABLE
        self.metrics: Dict[str, Any] = {}
        
        if not self.enabled:
            logger.warning("Prometheus client not available. Install with 'pip install prometheus-client'")
            return
            
        # Initialize Prometheus metrics
        self._initialize_metrics()
    
    def _initialize_metrics(self):
        """Initialize Prometheus metrics collectors."""
        if not self.enabled:
            return
            
        # Connection metrics
        self.metrics['redis_connection_attempts'] = Counter(
            'redis_connection_attempts_total',
            'Total number of Redis connection attempts'
        )
        self.metrics['redis_connection_failures'] = Counter(
            'redis_connection_failures_total',
            'Total number of Redis connection failures'
        )
        
        # Performance metrics
        self.metrics['redis_command_latency'] = Histogram(
            'redis_command_latency_seconds',
            'Redis command execution latency in seconds',
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)
        )
        
        # Health metrics
        self.metrics['redis_health_status'] = Gauge(
            'redis_health_status',
            'Redis health status (1=healthy, 0=unhealthy)'
        )
        self.metrics['redis_connected_clients'] = Gauge(
            'redis_connected_clients',
            'Number of clients connected to Redis'
        )
        self.metrics['redis_used_memory_bytes'] = Gauge(
            'redis_used_memory_bytes',
            'Memory used by Redis in bytes'
        )
        self.metrics['redis_uptime_seconds'] = Gauge(
            'redis_uptime_seconds',
            'Redis server uptime in seconds'
        )
        
        # Operation metrics
        self.metrics['redis_operations_total'] = Counter(
            'redis_operations_total',
            'Total number of Redis operations',
            ['operation']
        )
        self.metrics['redis_operations_failed_total'] = Counter(
            'redis_operations_failed_total',
            'Total number of failed Redis operations',
            ['operation']
        )
    
    def record_connection_attempt(self, success: bool = True):
        """Record a Redis connection attempt."""
        if not self.enabled:
            return
            
        self.metrics['redis_connection_attempts'].inc()
        if not success:
            self.metrics['redis_connection_failures'].inc()
    
    def record_operation(self, operation: str, success: bool = True, duration: Optional[float] = None):
        """Record a Redis operation with optional duration."""
        if not self.enabled:
            return
            
        self.metrics['redis_operations_total'].labels(operation=operation).inc()
        if not success:
            self.metrics['redis_operations_failed_total'].labels(operation=operation).inc()
        
        if duration is not None:
            self.metrics['redis_command_latency'].observe(duration)
    
    def update_health_metrics(self, redis_info: Dict[str, Any], is_healthy: bool):
        """Update Redis health metrics from info data."""
        if not self.enabled:
            return
            
        self.metrics['redis_health_status'].set(1 if is_healthy else 0)
        
        if redis_info:
            if 'connected_clients' in redis_info:
                self.metrics['redis_connected_clients'].set(redis_info['connected_clients'])
            
            if 'used_memory' in redis_info:
                self.metrics['redis_used_memory_bytes'].set(redis_info['used_memory'])
            
            if 'uptime_in_seconds' in redis_info:
                self.metrics['redis_uptime_seconds'].set(redis_info['uptime_in_seconds'])
                
            # Additional metrics if available
            if 'total_connections_received' in redis_info:
                if 'redis_total_connections' not in self.metrics:
                    self.metrics['redis_total_connections'] = Gauge(
                        'redis_total_connections',
                        'Total number of connections accepted by Redis'
                    )
                self.metrics['redis_total_connections'].set(redis_info['total_connections_received'])
                
            if 'instantaneous_ops_per_sec' in redis_info:
                if 'redis_ops_per_second' not in self.metrics:
                    self.metrics['redis_ops_per_second'] = Gauge(
                        'redis_ops_per_second',
                        'Instantaneous operations per second'
                    )
                self.metrics['redis_ops_per_second'].set(redis_info['instantaneous_ops_per_sec'])
    
    def start_http_server(self, port: int = 9090):
        """Start a Prometheus HTTP server to expose metrics."""
        if not self.enabled:
            logger.warning("Cannot start Prometheus HTTP server: prometheus_client not available")
            return False
            
        try:
            prometheus_client.start_http_server(port)
            logger.info(f"Prometheus metrics server started on port {port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start Prometheus metrics server: {str(e)}")
            return False

# Singleton instance
_prometheus_metrics = None

def get_prometheus_metrics() -> RedisPrometheusMetrics:
    """Get the singleton Prometheus metrics instance."""
    global _prometheus_metrics
    if _prometheus_metrics is None:
        _prometheus_metrics = RedisPrometheusMetrics()
    return _prometheus_metrics