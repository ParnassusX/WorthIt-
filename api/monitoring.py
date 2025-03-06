import logging
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Histogram, Gauge
from typing import Dict, Any
import time
import psutil
import json

# Configure logging with enhanced context and security audit
def setup_logging():
    """Set up logging configuration with enhanced context tracking and security audit"""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(context)s',
        level=logging.INFO
    )
    logger = logging.getLogger(__name__)
    
    # Add security audit logger
    audit_logger = logging.getLogger('security_audit')
    audit_handler = logging.FileHandler('security_audit.log')
    audit_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s - %(context)s')
    )
    audit_logger.addHandler(audit_handler)
    audit_logger.setLevel(logging.INFO)
    
    logger.info("API monitoring configured", extra={"context": json.dumps({"setup": "initial"})})
    return logger, audit_logger

# Enhanced metrics for cross-component monitoring
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status', 'component']
)

RESPONSE_TIME = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint', 'component']
)
def track_api_metrics(endpoint: str, method: str, status_code: int, duration: float):
    """Track API metrics with enhanced error context"""
    REQUEST_COUNT.labels(
        method=method,
        endpoint=endpoint,
        status=status_code,
        component='api'
    ).inc()

    RESPONSE_TIME.labels(
        method=method,
        endpoint=endpoint,
        component='api'
    ).observe(duration)

    # Track system resources
    memory = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent()

    SYSTEM_MEMORY.labels(type='used').set(memory.used)
    SYSTEM_MEMORY.labels(type='available').set(memory.available)
    SYSTEM_CPU.labels(type='user').set(cpu_percent)

    # Log errors with enhanced context
    if status_code >= 400:
        error_context = {
            "endpoint": endpoint,
            "method": method,
            "status_code": status_code,
            "duration": duration,
            "memory_usage": memory.percent,
            "cpu_usage": cpu_percent
        }
        logging.error(
            f"API Error: {status_code} on {method} {endpoint}",
            extra={"context": json.dumps(error_context)}
        )

def track_security_event(event_type: str, severity: str, details: Dict[str, Any]):
    """Track security-related events with detailed context"""
    SECURITY_EVENTS.labels(
        event_type=event_type,
        severity=severity
    ).inc()

    # Log security event with context
    security_context = {
        "event_type": event_type,
        "severity": severity,
        "timestamp": time.time(),
        **details
    }

    audit_logger = logging.getLogger('security_audit')
    audit_logger.info(
        f"Security event: {event_type}",
        extra={"context": json.dumps(security_context)}
    )

# Cross-component metrics
COMPONENT_HEALTH = Gauge(
    'component_health',
    'Component health status',
    ['component']
)

COMPONENT_LATENCY = Histogram(
    'component_latency',
    'Inter-component communication latency',
    ['source', 'destination']
)

QUEUE_SIZE = Gauge(
    'queue_size',
    'Current queue size',
    ['queue_name']
)

# Performance metrics
PROCESSING_TIME = Histogram(
    'task_processing_time',
    'Task processing time',
    ['task_type']
)

MEMORY_PER_TASK = Gauge(
    'memory_per_task',
    'Memory usage per task type',
    ['task_type']
)

TASK_THROUGHPUT = Counter(
    'task_throughput_total',
    'Number of tasks processed',
    ['task_type', 'status']
)

# System health metrics
SYSTEM_MEMORY = Gauge(
    'system_memory_usage_bytes',
    'System memory usage in bytes',
    ['type']
)

SYSTEM_CPU = Gauge(
    'system_cpu_usage_percent',
    'System CPU usage percentage',
    ['type']
)

# Security metrics
SECURITY_EVENTS = Counter(
    'security_events_total',
    'Total number of security-related events',
    ['event_type', 'severity']
)

FAILED_REQUESTS = Counter(
    'failed_requests_total',
    'Total number of failed requests',
    ['method', 'endpoint', 'error_type']
)

def update_system_metrics():
    """Update system-level metrics with resource usage thresholds"""
    try:
        memory = psutil.virtual_memory()
        SYSTEM_MEMORY.labels('total').set(memory.total)
        SYSTEM_MEMORY.labels('used').set(memory.used)
        SYSTEM_MEMORY.labels('available').set(memory.available)
        
        # Alert on high memory usage
        if memory.percent > 90:
            logging.warning("High memory usage detected", 
                          extra={"context": json.dumps({"memory_percent": memory.percent})})
        
        cpu_percent = psutil.cpu_percent(interval=1)
        SYSTEM_CPU.labels('total').set(cpu_percent)
        
        # Alert on high CPU usage
        if cpu_percent > 80:
            logging.warning("High CPU usage detected", 
                          extra={"context": json.dumps({"cpu_percent": cpu_percent})})

        # Update cross-component metrics
        update_component_health()
        update_queue_metrics()
        
    except Exception as e:
        logging.error(f"Error updating system metrics: {str(e)}", 
                     extra={"context": json.dumps({"error": str(e)})})

def update_component_health():
    """Update health status of system components"""
    try:
        components = ['api', 'worker', 'bot', 'redis']
        for component in components:
            health_status = check_component_health(component)
            COMPONENT_HEALTH.labels(component=component).set(1 if health_status else 0)
    except Exception as e:
        logging.error(f"Error updating component health: {str(e)}", 
                     extra={"context": json.dumps({"error": str(e)})})

def update_queue_metrics():
    """Update queue-related metrics"""
    try:
        queues = ['tasks', 'notifications', 'events']
        for queue in queues:
            size = get_queue_size(queue)
            QUEUE_SIZE.labels(queue_name=queue).set(size)
    except Exception as e:
        logging.error(f"Error updating queue metrics: {str(e)}", 
                     extra={"context": json.dumps({"error": str(e)})})

def log_task_metrics(task_type: str, duration: float, status: str):
    """Log task processing metrics"""
    try:
        PROCESSING_TIME.labels(task_type=task_type).observe(duration)
        TASK_THROUGHPUT.labels(task_type=task_type, status=status).inc()
        
        # Track memory usage per task
        process = psutil.Process()
        MEMORY_PER_TASK.labels(task_type=task_type).set(process.memory_info().rss)
        
    except Exception as e:
        logging.error(f"Error logging task metrics: {str(e)}", 
                     extra={"context": json.dumps({"error": str(e)})})

# Helper functions
from .health import check_component_health, get_queue_size  # Import actual implementations
def setup_metrics(app: FastAPI):
    """Set up enhanced metrics collection with security monitoring"""
    # Initialize Prometheus instrumentation
    Instrumentator().instrument(app).expose(app)
    
    @app.middleware("http")
    async def metrics_middleware(request, call_next):
        start_time = time.time()
        component = request.url.path.split('/')[1] if len(request.url.path.split('/')) > 1 else 'root'
        
        try:
            response = await call_next(request)
            duration = time.time() - start_time
            
            # Record enhanced metrics
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code,
                component=component
            ).inc()
            
            RESPONSE_TIME.labels(
                method=request.method,
                endpoint=request.url.path,
                component=component
            ).observe(duration)
            
            # Log slow requests
            if duration > 1.0:  # 1 second threshold
                logging.warning(
                    "Slow request detected",
                    extra={"context": json.dumps({
                        "method": request.method,
                        "path": request.url.path,
                        "duration": duration
                    })}
                )
            
            return response
        except Exception as e:
            # Record failed request metrics
            FAILED_REQUESTS.labels(
                method=request.method,
                endpoint=request.url.path,
                error_type=type(e).__name__
            ).inc()
            
            # Log security-related errors
            if isinstance(e, (PermissionError, ValueError)):
                SECURITY_EVENTS.labels(
                    event_type='request_error',
                    severity='high'
                ).inc()
                
                logging.getLogger('security_audit').warning(
                    "Security-related request error",
                    extra={"context": json.dumps({
                        "method": request.method,
                        "path": request.url.path,
                        "error": str(e)
                    })}
                )
            
            raise
    logger = logging.getLogger(__name__)
    logger.info("Enhanced Prometheus metrics configured successfully", 
                extra={"context": json.dumps({"setup": "metrics"})})
    
    return app

# Function to register all monitoring components
def setup_monitoring(app: FastAPI):
    """Set up all monitoring components with enhanced tracking"""
    setup_logging()
    setup_metrics(app)
    return app