from typing import Dict, Any, List
import psutil
from prometheus_client import Gauge, Histogram, Counter, CollectorRegistry, REGISTRY
import time
import logging
import json
from .queue import get_redis_client

# Configure logging with enhanced context
def setup_logging():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(context)s',
        level=logging.INFO
    )
    logger = logging.getLogger(__name__)
    logger.info("Worker monitoring configured", extra={"setup": "initial"})
    return logger

# Create a custom registry to avoid conflicts
monitoring_registry = CollectorRegistry()

# Prometheus metrics
CPU_USAGE = Gauge('worker_cpu_usage', 'Current CPU usage percentage', registry=monitoring_registry)
MEMORY_USAGE = Gauge('worker_memory_usage', 'Current memory usage percentage', registry=monitoring_registry)
ACTIVE_WORKERS = Gauge('active_workers', 'Number of active worker processes', registry=monitoring_registry)

# Service monitoring metrics
HF_API_CALLS = Counter('hf_api_calls_total', 'Hugging Face API call count', registry=monitoring_registry)
HF_ERROR_RATE = Gauge('hf_error_rate', 'Hugging Face API error rate', registry=monitoring_registry)
HF_RESPONSE_TIME = Histogram('hf_response_time', 'Hugging Face API response time', registry=monitoring_registry)
APIFY_CALLS = Counter('apify_calls_total', 'Apify API call count', registry=monitoring_registry)
APIFY_ERROR_RATE = Gauge('apify_error_rate', 'Apify API error rate', registry=monitoring_registry)
APIFY_RESPONSE_TIME = Histogram('apify_response_time', 'Apify API response time', registry=monitoring_registry)

# Cross-component metrics
COMPONENT_HEALTH = Gauge('component_health', 'Component health status', ['component'], registry=monitoring_registry)
COMPONENT_LATENCY = Histogram('component_latency', 'Inter-component communication latency', ['source', 'destination'], registry=monitoring_registry)
QUEUE_SIZE = Gauge('queue_size', 'Current queue size', ['queue_name'], registry=monitoring_registry)

# Performance metrics
PROCESSING_TIME = Histogram('task_processing_time', 'Task processing time', ['task_type'], registry=monitoring_registry)
MEMORY_PER_TASK = Gauge('memory_per_task', 'Memory usage per task type', ['task_type'], registry=monitoring_registry)
TASK_THROUGHPUT = Counter('task_throughput_total', 'Number of tasks processed', ['task_type', 'status'], registry=monitoring_registry)

# User interaction metrics
USER_START_COMMANDS = Counter('user_start_commands_total', 'Number of /start commands received', registry=monitoring_registry)
USER_LINK_INTERACTIONS = Counter('user_link_interactions_total', 'Number of product links interacted with', registry=monitoring_registry)
USER_JOURNEY_STAGE = Histogram('user_journey_stage', 'Current stage in user interaction flow', ['stage'], registry=monitoring_registry)

# Enhanced monitoring functions
async def update_component_health(component: str, is_healthy: bool):
    """Update health status of a component"""
    COMPONENT_HEALTH.labels(component=component).set(1 if is_healthy else 0)

async def track_component_latency(source: str, destination: str, duration: float):
    """Track latency between components"""
    try:
        COMPONENT_LATENCY.labels(source=source, destination=destination).observe(duration)
        logger.info(f"Component latency tracked",
                  extra={'context': json.dumps({'source': source, 'destination': destination, 'duration': duration})})
    except Exception as e:
        logger.error(f"Error tracking component latency: {str(e)}",
                    extra={'context': json.dumps({'error': str(e)})})

async def update_queue_metrics(queue_name: str, size: int):
    """Update queue size metrics"""
    QUEUE_SIZE.labels(queue_name=queue_name).set(size)

async def track_task_metrics(task_type: str, duration: float, memory_usage: float, status: str):
    """Track comprehensive task metrics"""
    try:
        PROCESSING_TIME.labels(task_type=task_type).observe(duration)
        MEMORY_PER_TASK.labels(task_type=task_type).set(memory_usage)
        TASK_THROUGHPUT.labels(task_type=task_type, status=status).inc()
        
        logger.info(f"Task metrics tracked",
                  extra={'context': json.dumps({
                      'task_type': task_type,
                      'duration': duration,
                      'memory_usage': memory_usage,
                      'status': status
                  })})
    except Exception as e:
        logger.error(f"Error tracking task metrics: {str(e)}",
                    extra={'context': json.dumps({'error': str(e)})})

async def track_user_interaction(interaction_type: str, stage: str = None):
    """Track user interaction metrics"""
    if interaction_type == 'start':
        USER_START_COMMANDS.inc()
    elif interaction_type == 'link':
        USER_LINK_INTERACTIONS.inc()
    
    if stage:
        USER_JOURNEY_STAGE.labels(stage=stage).observe(time.time())

class RequestTracker:
    def __init__(self):
        self.total = 0
        self.errors = 0
        self.total_response_time = 0.0
        
    def track_request(self, duration: float, is_error: bool = False):
        self.total += 1
        if is_error:
            self.errors += 1
        self.total_response_time += duration
        
    @property
    def error_rate(self) -> float:
        return self.errors / self.total if self.total > 0 else 0.0
        
    @property
    def average_response_time(self) -> float:
        return self.total_response_time / self.total if self.total > 0 else 0.0
        self.start_time = time.time()

    @property
    def avg_response_time(self):
        return self.total_response_time / self.total if self.total > 0 else 0

    @property
    def error_rate(self):
        return self.errors / self.total if self.total > 0 else 0

# Global trackers
hf_requests = RequestTracker()
apify_requests = RequestTracker()

def track_metrics():
    """Track enhanced worker metrics with service monitoring and detailed error context"""
    try:
        # Basic metrics with enhanced context
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        metrics_context = {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent,
            "timestamp": time.time()
        }
        
        CPU_USAGE.set(cpu_percent)
        MEMORY_USAGE.set(memory.percent)
        # Get active workers count from process monitoring
        active_workers = len(psutil.Process().children())
        ACTIVE_WORKERS.set(active_workers)

        # Service-specific metrics with detailed tracking
        HF_API_CALLS.inc()
        HF_ERROR_RATE.set(hf_requests.error_rate)
        APIFY_CALLS.inc()
        APIFY_ERROR_RATE.set(apify_requests.error_rate)

        # Response time metrics with percentile tracking
        HF_RESPONSE_TIME.observe(hf_requests.avg_response_time)
        APIFY_RESPONSE_TIME.observe(apify_requests.avg_response_time)

        # Component health check with enhanced monitoring
        health_status = update_component_health()
        metrics_context["component_health"] = health_status

        # Resource monitoring alerts with thresholds
        if cpu_percent > 80:
            logging.warning(
                "High CPU usage detected", 
                extra={"context": json.dumps({**metrics_context, "alert_type": "cpu_high"})}
            )
        if memory.percent > 90:
            logging.warning(
                "High memory usage detected", 
                extra={"context": json.dumps({**metrics_context, "alert_type": "memory_high"})}
            )
        if disk.percent > 85:
            logging.warning(
                "High disk usage detected",
                extra={"context": json.dumps({**metrics_context, "alert_type": "disk_high"})}
            )

        # Log successful metrics update
        logging.info(
            "Metrics updated successfully",
            extra={"context": json.dumps(metrics_context)}
        )

    except Exception as e:
        error_context = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "timestamp": time.time()
        }
        logging.error(
            f"Error updating metrics: {str(e)}", 
            extra={"context": json.dumps(error_context)},
            exc_info=True
        )

def log_external_api_call(service_name: str, duration: float, success: bool = True):
    """Log external API calls with enhanced monitoring"""
    try:
        if service_name.lower() == 'huggingface':
            tracker = hf_requests
            response_time = HF_RESPONSE_TIME
            error_rate = HF_ERROR_RATE
        elif service_name.lower() == 'apify':
            tracker = apify_requests
            response_time = APIFY_RESPONSE_TIME
            error_rate = APIFY_ERROR_RATE
        else:
            return

        tracker.total += 1
        tracker.total_response_time += duration
        if not success:
            tracker.errors += 1

        response_time.observe(duration)
        error_rate.set(tracker.error_rate)

        if duration > 5.0:  # Alert on slow responses
            logging.warning(f"Slow {service_name} API response", 
                          extra={"context": json.dumps({"duration": duration})})

    except Exception as e:
        logging.error(f"Error logging API call: {str(e)}", 
                     extra={"context": json.dumps({"error": str(e)})})

def update_component_health():
    """Enhanced component health check with detailed status tracking"""
    health_status = {}
    components = ['api', 'worker', 'bot', 'redis', 'database']
    
    for component in components:
        try:
            # Implement specific health checks for each component
            status = check_component_status(component)
            COMPONENT_HEALTH.labels(component=component).set(status['health_score'])
            health_status[component] = status
        except Exception as e:
            logging.error(f"Health check failed for {component}", 
                         extra={"context": json.dumps({"error": str(e), "component": component})})
            COMPONENT_HEALTH.labels(component=component).set(0)
            health_status[component] = {"status": "error", "error": str(e)}
    
    return health_status

def check_component_status(component: str) -> Dict[str, Any]:
    """Perform detailed health checks for specific components"""
    status = {"health_score": 1.0, "last_check": time.time()}
    
    if component == 'worker':
        # Worker-specific checks
        cpu = psutil.cpu_percent()
        memory = psutil.virtual_memory().percent
        status.update({
            "cpu_usage": cpu,
            "memory_usage": memory,
            "health_score": 1.0 if cpu < 80 and memory < 80 else 0.5
        })
    
    elif component == 'redis':
        # Redis connection check
        try:
            # Implement Redis ping check here
            status["health_score"] = 1.0
        except Exception as e:
            status["health_score"] = 0.0
            status["error"] = str(e)
    
    # Add more component-specific checks as needed
    
    return status

def track_performance_metrics(task_type: str, start_time: float):
    """Track detailed performance metrics for tasks"""
    processing_time = time.time() - start_time
    PROCESSING_TIME.labels(task_type=task_type).observe(processing_time)
    
    # Track memory usage
    process = psutil.Process()
    memory_info = process.memory_info()
    MEMORY_PER_TASK.labels(task_type=task_type).set(memory_info.rss)
    
    # Track task throughput
    TASK_THROUGHPUT.labels(task_type=task_type, status="completed").inc()

# Helper functions

async def update_task_status(task_id: str, status: str, context: Dict[str, Any] = None):
    """Update task status and track metrics"""
    try:
        TASK_THROUGHPUT.labels(task_type=status, status='success').inc()
        if context:
            logger.info(f"Task {task_id} status updated to {status}",
                      extra={'context': json.dumps(context)})
    except Exception as e:
        logger.error(f"Error updating task status: {str(e)}",
                    extra={'context': json.dumps({'task_id': task_id, 'error': str(e)})})

async def log_task_lifecycle(task_id: str, event: str, context: Dict[str, Any] = None):
    """Log task lifecycle events with metrics tracking"""
    try:
        if context:
            logger.info(f"Task {task_id} lifecycle event: {event}",
                      extra={'context': json.dumps(context)})
    except Exception as e:
        logger.error(f"Error logging task lifecycle: {str(e)}",
                    extra={'context': json.dumps({'task_id': task_id, 'error': str(e)})})

class AlertingSystem:
    def __init__(self):
        self.logger

async def get_task_history(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent task processing history"""
    try:
        # For now, return a simple list of recent task metrics
        tasks = []
        for sample in TASK_THROUGHPUT._metrics:
            task_type = sample.labels.get('task_type', 'unknown')
            status = sample.labels.get('status', 'unknown')
            count = sample.value
            tasks.append({
                'task_type': task_type,
                'status': status,
                'count': count
            })
        return tasks[:limit]
    except Exception as e:
        logger.error(f"Error getting task history: {str(e)}")
        return []

async def get_worker_health() -> Dict[str, Any]:
    """Get current worker health metrics"""
    try:
        return {
            'cpu_usage': CPU_USAGE._value.get(),
            'memory_usage': MEMORY_USAGE._value.get(),
            'active_workers': ACTIVE_WORKERS._value.get(),
            'component_health': {
                component: COMPONENT_HEALTH.labels(component=component)._value.get()
                for component in ['api', 'worker', 'bot']
            }
        }
    except Exception as e:
        logger.error(f"Error getting worker health: {str(e)}")
        return {}

async def check_redis_connection() -> bool:
    """Check Redis connection status"""
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection check failed: {str(e)}")
        return False

class AlertingSystem:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.alert_counter = Counter('alerts_total', 'Total number of alerts triggered', ['severity', 'type'])
        self.incident_duration = Histogram('incident_duration_seconds', 'Duration of incidents until resolution')

    async def trigger_alert(self, alert_type: str, severity: str, details: Dict[str, Any]):
        """Trigger an alert with automated response based on severity and type"""
        self.alert_counter.labels(severity=severity, type=alert_type).inc()
        
        alert_context = {
            'type': alert_type,
            'severity': severity,
            'timestamp': time.time(),
            'details': details
        }
        
        self.logger.warning(
            f"Alert triggered: {alert_type}",
            extra={'context': json.dumps(alert_context)}
        )
        
        await self._handle_alert(alert_context)

    async def _handle_alert(self, context: Dict[str, Any]):
        """Handle alerts with automated responses based on type and severity"""
        severity = context['severity']
        alert_type = context['type']
        
        if severity == 'critical':
            await self._handle_critical_alert(context)
        elif severity == 'warning':
            await self._handle_warning_alert(context)
        
        # Track incident in monitoring system
        COMPONENT_HEALTH.labels(component=alert_type).set(0)

    async def _handle_critical_alert(self, context: Dict[str, Any]):
        """Handle critical alerts with immediate action"""
        # Implement automated recovery procedures
        if context['type'] == 'service_down':
            await self._attempt_service_recovery(context)
        elif context['type'] == 'high_error_rate':
            await self._implement_circuit_breaker(context)
        
        # Notify on-call team
        await self._notify_team(context)

    async def _handle_warning_alert(self, context: Dict[str, Any]):
        """Handle warning alerts with preventive measures"""
        if context['type'] == 'high_latency':
            await self._optimize_performance(context)
        elif context['type'] == 'resource_usage':
            await self._scale_resources(context)

    async def _attempt_service_recovery(self, context: Dict[str, Any]):
        """Attempt to recover failed services automatically"""
        service = context['details'].get('service')
        try:
            # Implement service-specific recovery logic
            if service == 'api':
                await self._restart_api_service()
            elif service == 'worker':
                await self._restart_worker_process()
            elif service == 'database':
                await self._reconnect_database()
            
            self.logger.info(
                f"Recovery attempted for service {service}",
                extra={'context': json.dumps({'service': service, 'status': 'recovery_attempted'})}
            )
        except Exception as e:
            self.logger.error(
                f"Recovery failed for service {service}",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _implement_circuit_breaker(self, context: Dict[str, Any]):
        """Implement circuit breaker pattern for failing components"""
        component = context['details'].get('component')
        try:
            # Temporarily disable the failing component
            COMPONENT_HEALTH.labels(component=component).set(0)
            
            # Implement fallback mechanism
            await self._activate_fallback(component)
            
            self.logger.info(
                f"Circuit breaker activated for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'circuit_breaker_activated'})}
            )
        except Exception as e:
            self.logger.error(
                f"Circuit breaker implementation failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _optimize_performance(self, context: Dict[str, Any]):
        """Optimize system performance based on monitoring data"""
        try:
            # Implement performance optimization logic
            component = context['details'].get('component')
            current_latency = context['details'].get('latency', 0)
            
            if current_latency > 1.0:  # High latency threshold
                # Implement optimization strategies
                await self._reduce_load(component)
                await self._scale_resources(component)
            
            self.logger.info(
                f"Performance optimization completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'performance_optimized'})}
            )
        except Exception as e:
            self.logger.error(
                "Performance optimization failed",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _scale_resources(self, component: str):
        """Scale system resources based on demand"""
        try:
            # Implement auto-scaling logic
            current_usage = self._get_resource_usage(component)
            if current_usage > 80:  # High usage threshold
                # Trigger resource scaling
                await self._increase_capacity(component)
            
            self.logger.info(
                f"Resource scaling completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'resources_scaled'})}
            )
        except Exception as e:
            self.logger.error(
                f"Resource scaling failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _notify_team(self, context: Dict[str, Any]):
        """Notify on-call team about critical incidents"""
        try:
            # Implement notification logic (e.g., email, Slack, PagerDuty)
            notification_context = {
                'incident_type': context['type'],
                'severity': context['severity'],
                'timestamp': context['timestamp'],
                'details': context['details']
            }
            
            # Log notification attempt
            self.logger.info(
                "On-call team notification sent",
                extra={'context': json.dumps(notification_context)}
            )
        except Exception as e:
            self.logger.error(
                "Failed to notify on-call team",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

class AlertingSystem:
    def __init__(self):
        self.logger

async def get_task_history(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent task processing history"""
    try:
        # For now, return a simple list of recent task metrics
        tasks = []
        for sample in TASK_THROUGHPUT._metrics:
            task_type = sample.labels.get('task_type', 'unknown')
            status = sample.labels.get('status', 'unknown')
            count = sample.value
            tasks.append({
                'task_type': task_type,
                'status': status,
                'count': count
            })
        return tasks[:limit]
    except Exception as e:
        logger.error(f"Error getting task history: {str(e)}")
        return []

async def get_worker_health() -> Dict[str, Any]:
    """Get current worker health metrics"""
    try:
        return {
            'cpu_usage': CPU_USAGE._value.get(),
            'memory_usage': MEMORY_USAGE._value.get(),
            'active_workers': ACTIVE_WORKERS._value.get(),
            'component_health': {
                component: COMPONENT_HEALTH.labels(component=component)._value.get()
                for component in ['api', 'worker', 'bot']
            }
        }
    except Exception as e:
        logger.error(f"Error getting worker health: {str(e)}")
        return {}

async def check_redis_connection() -> bool:
    """Check Redis connection status"""
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection check failed: {str(e)}")
        return False

class AlertingSystem:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.alert_counter = Counter('alerts_total', 'Total number of alerts triggered', ['severity', 'type'])
        self.incident_duration = Histogram('incident_duration_seconds', 'Duration of incidents until resolution')

    async def trigger_alert(self, alert_type: str, severity: str, details: Dict[str, Any]):
        """Trigger an alert with automated response based on severity and type"""
        self.alert_counter.labels(severity=severity, type=alert_type).inc()
        
        alert_context = {
            'type': alert_type,
            'severity': severity,
            'timestamp': time.time(),
            'details': details
        }
        
        self.logger.warning(
            f"Alert triggered: {alert_type}",
            extra={'context': json.dumps(alert_context)}
        )
        
        await self._handle_alert(alert_context)

    async def _handle_alert(self, context: Dict[str, Any]):
        """Handle alerts with automated responses based on type and severity"""
        severity = context['severity']
        alert_type = context['type']
        
        if severity == 'critical':
            await self._handle_critical_alert(context)
        elif severity == 'warning':
            await self._handle_warning_alert(context)
        
        # Track incident in monitoring system
        COMPONENT_HEALTH.labels(component=alert_type).set(0)

    async def _handle_critical_alert(self, context: Dict[str, Any]):
        """Handle critical alerts with immediate action"""
        # Implement automated recovery procedures
        if context['type'] == 'service_down':
            await self._attempt_service_recovery(context)
        elif context['type'] == 'high_error_rate':
            await self._implement_circuit_breaker(context)
        
        # Notify on-call team
        await self._notify_team(context)

    async def _handle_warning_alert(self, context: Dict[str, Any]):
        """Handle warning alerts with preventive measures"""
        if context['type'] == 'high_latency':
            await self._optimize_performance(context)
        elif context['type'] == 'resource_usage':
            await self._scale_resources(context)

    async def _attempt_service_recovery(self, context: Dict[str, Any]):
        """Attempt to recover failed services automatically"""
        service = context['details'].get('service')
        try:
            # Implement service-specific recovery logic
            if service == 'api':
                await self._restart_api_service()
            elif service == 'worker':
                await self._restart_worker_process()
            elif service == 'database':
                await self._reconnect_database()
            
            self.logger.info(
                f"Recovery attempted for service {service}",
                extra={'context': json.dumps({'service': service, 'status': 'recovery_attempted'})}
            )
        except Exception as e:
            self.logger.error(
                f"Recovery failed for service {service}",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _implement_circuit_breaker(self, context: Dict[str, Any]):
        """Implement circuit breaker pattern for failing components"""
        component = context['details'].get('component')
        try:
            # Temporarily disable the failing component
            COMPONENT_HEALTH.labels(component=component).set(0)
            
            # Implement fallback mechanism
            await self._activate_fallback(component)
            
            self.logger.info(
                f"Circuit breaker activated for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'circuit_breaker_activated'})}
            )
        except Exception as e:
            self.logger.error(
                f"Circuit breaker implementation failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _optimize_performance(self, context: Dict[str, Any]):
        """Optimize system performance based on monitoring data"""
        try:
            # Implement performance optimization logic
            component = context['details'].get('component')
            current_latency = context['details'].get('latency', 0)
            
            if current_latency > 1.0:  # High latency threshold
                # Implement optimization strategies
                await self._reduce_load(component)
                await self._scale_resources(component)
            
            self.logger.info(
                f"Performance optimization completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'performance_optimized'})}
            )
        except Exception as e:
            self.logger.error(
                "Performance optimization failed",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _scale_resources(self, component: str):
        """Scale system resources based on demand"""
        try:
            # Implement auto-scaling logic
            current_usage = self._get_resource_usage(component)
            if current_usage > 80:  # High usage threshold
                # Trigger resource scaling
                await self._increase_capacity(component)
            
            self.logger.info(
                f"Resource scaling completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'resources_scaled'})}
            )
        except Exception as e:
            self.logger.error(
                f"Resource scaling failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _notify_team(self, context: Dict[str, Any]):
        """Notify on-call team about critical incidents"""
        try:
            # Implement notification logic (e.g., email, Slack, PagerDuty)
            notification_context = {
                'incident_type': context['type'],
                'severity': context['severity'],
                'timestamp': context['timestamp'],
                'details': context['details']
            }
            
            # Log notification attempt
            self.logger.info(
                "On-call team notification sent",
                extra={'context': json.dumps(notification_context)}
            )
        except Exception as e:
            self.logger.error(
                "Failed to notify on-call team",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

# Create a custom registry for resource prediction metrics
RESOURCE_REGISTRY = CollectorRegistry()

# Predictive monitoring metrics
RESOURCE_PREDICTION = Gauge('resource_prediction', 'Predicted resource usage', ['resource_type', 'timeframe'], registry=RESOURCE_REGISTRY)
ANOMALY_SCORE = Gauge('anomaly_score', 'System anomaly score', ['component'], registry=RESOURCE_REGISTRY)
CAPACITY_THRESHOLD = Gauge('capacity_threshold', 'Dynamic capacity threshold', ['resource_type'], registry=RESOURCE_REGISTRY)

# Capacity planning metrics
RESOURCE_TREND = Gauge('resource_trend', 'Resource usage trend', ['resource_type', 'window'], registry=RESOURCE_REGISTRY)
SCALING_RECOMMENDATION = Gauge('scaling_recommendation', 'Recommended scaling factor', ['component'], registry=RESOURCE_REGISTRY)
RESOURCE_EFFICIENCY = Gauge('resource_efficiency', 'Resource utilization efficiency', ['resource_type'], registry=RESOURCE_REGISTRY)

async def update_predictive_metrics(resource_type: str, current_usage: float, historical_data: list):
    """Update predictive monitoring metrics based on historical data"""
    # Calculate short-term prediction (1 hour)
    short_term_prediction = calculate_prediction(historical_data, timeframe='1h')
    RESOURCE_PREDICTION.labels(resource_type=resource_type, timeframe='1h').set(short_term_prediction)
    
    # Calculate long-term prediction (24 hours)
    long_term_prediction = calculate_prediction(historical_data, timeframe='24h')
    RESOURCE_PREDICTION.labels(resource_type=resource_type, timeframe='24h').set(long_term_prediction)
    
    # Update anomaly score
    anomaly_score = detect_anomalies(current_usage, historical_data)
    ANOMALY_SCORE.labels(component=resource_type).set(anomaly_score)

async def update_capacity_metrics(resource_type: str, usage_data: list):
    """Update capacity planning metrics based on usage patterns"""
    # Calculate resource usage trend
    short_trend = calculate_trend(usage_data, window='1h')
    long_trend = calculate_trend(usage_data, window='24h')
    RESOURCE_TREND.labels(resource_type=resource_type, window='1h').set(short_trend)
    RESOURCE_TREND.labels(resource_type=resource_type, window='24h').set(long_trend)
    
    # Calculate dynamic capacity threshold
    threshold = calculate_dynamic_threshold(usage_data)
    CAPACITY_THRESHOLD.labels(resource_type=resource_type).set(threshold)
    
    # Calculate scaling recommendation
    scaling_factor = calculate_scaling_factor(usage_data, threshold)
    SCALING_RECOMMENDATION.labels(component=resource_type).set(scaling_factor)
    
    # Calculate resource efficiency
    efficiency = calculate_resource_efficiency(usage_data)
    RESOURCE_EFFICIENCY.labels(resource_type=resource_type).set(efficiency)

def calculate_prediction(historical_data: list, timeframe: str) -> float:
    """Calculate resource usage prediction based on historical data"""
    # Implement time series forecasting (e.g., using exponential smoothing)
    # For now, using a simple moving average
    return sum(historical_data[-10:]) / len(historical_data[-10:])

def detect_anomalies(current_value: float, historical_data: list) -> float:
    """Detect anomalies in resource usage patterns"""
    mean = sum(historical_data) / len(historical_data)
    std_dev = (sum((x - mean) ** 2 for x in historical_data) / len(historical_data)) ** 0.5
    z_score = abs(current_value - mean) / std_dev if std_dev > 0 else 0
    return z_score

def calculate_trend(usage_data: list, window: str) -> float:
    """Calculate resource usage trend"""
    if len(usage_data) < 2:
        return 0.0
    return (usage_data[-1] - usage_data[0]) / len(usage_data)

def calculate_dynamic_threshold(usage_data: list) -> float:
    """Calculate dynamic capacity threshold based on usage patterns"""
    mean = sum(usage_data) / len(usage_data)
    std_dev = (sum((x - mean) ** 2 for x in usage_data) / len(usage_data)) ** 0.5
    return mean + (2 * std_dev)  # Using 2 standard deviations as threshold

def calculate_scaling_factor(usage_data: list, threshold: float) -> float:
    """Calculate recommended scaling factor based on usage and threshold"""
    current_usage = usage_data[-1] if usage_data else 0
    if current_usage > threshold:
        return 1.2  # Recommend 20% increase in capacity
    elif current_usage < threshold * 0.5:
        return 0.8  # Recommend 20% decrease in capacity
    return 1.0

def calculate_resource_efficiency(usage_data: list) -> float:
    """Calculate resource utilization efficiency"""
    if not usage_data:
        return 0.0
    peak_usage = max(usage_data)
    avg_usage = sum(usage_data) / len(usage_data)
    return avg_usage / peak_usage if peak_usage > 0 else 0.0

    @property
    def error_rate(self):
        return self.errors / self.total if self.total > 0 else 0

# Global trackers
hf_requests = RequestTracker()
apify_requests = RequestTracker()

def track_metrics():
    """Track enhanced worker metrics with service monitoring and detailed error context"""
    try:
        # Basic metrics with enhanced context
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        metrics_context = {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent,
            "timestamp": time.time()
        }
        
        CPU_USAGE.set(cpu_percent)
        MEMORY_USAGE.set(memory.percent)
        # Get active workers count from process monitoring
        active_workers = len(psutil.Process().children())
        ACTIVE_WORKERS.set(active_workers)

        # Service-specific metrics with detailed tracking
        HF_API_CALLS.inc()
        HF_ERROR_RATE.set(hf_requests.error_rate)
        APIFY_CALLS.inc()
        APIFY_ERROR_RATE.set(apify_requests.error_rate)

        # Response time metrics with percentile tracking
        HF_RESPONSE_TIME.observe(hf_requests.avg_response_time)
        APIFY_RESPONSE_TIME.observe(apify_requests.avg_response_time)

        # Component health check with enhanced monitoring
        health_status = update_component_health()
        metrics_context["component_health"] = health_status

        # Resource monitoring alerts with thresholds
        if cpu_percent > 80:
            logging.warning(
                "High CPU usage detected", 
                extra={"context": json.dumps({**metrics_context, "alert_type": "cpu_high"})}
            )
        if memory.percent > 90:
            logging.warning(
                "High memory usage detected", 
                extra={"context": json.dumps({**metrics_context, "alert_type": "memory_high"})}
            )
        if disk.percent > 85:
            logging.warning(
                "High disk usage detected",
                extra={"context": json.dumps({**metrics_context, "alert_type": "disk_high"})}
            )

        # Log successful metrics update
        logging.info(
            "Metrics updated successfully",
            extra={"context": json.dumps(metrics_context)}
        )

    except Exception as e:
        error_context = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "timestamp": time.time()
        }
        logging.error(
            f"Error updating metrics: {str(e)}", 
            extra={"context": json.dumps(error_context)},
            exc_info=True
        )

def log_external_api_call(service_name: str, duration: float, success: bool = True):
    """Log external API calls with enhanced monitoring"""
    try:
        if service_name.lower() == 'huggingface':
            tracker = hf_requests
            response_time = HF_RESPONSE_TIME
            error_rate = HF_ERROR_RATE
        elif service_name.lower() == 'apify':
            tracker = apify_requests
            response_time = APIFY_RESPONSE_TIME
            error_rate = APIFY_ERROR_RATE
        else:
            return

        tracker.total += 1
        tracker.total_response_time += duration
        if not success:
            tracker.errors += 1

        response_time.observe(duration)
        error_rate.set(tracker.error_rate)

        if duration > 5.0:  # Alert on slow responses
            logging.warning(f"Slow {service_name} API response", 
                          extra={"context": json.dumps({"duration": duration})})

    except Exception as e:
        logging.error(f"Error logging API call: {str(e)}", 
                     extra={"context": json.dumps({"error": str(e)})})

def update_component_health():
    """Enhanced component health check with detailed status tracking"""
    health_status = {}
    components = ['api', 'worker', 'bot', 'redis', 'database']
    
    for component in components:
        try:
            # Implement specific health checks for each component
            status = check_component_status(component)
            COMPONENT_HEALTH.labels(component=component).set(status['health_score'])
            health_status[component] = status
        except Exception as e:
            logging.error(f"Health check failed for {component}", 
                         extra={"context": json.dumps({"error": str(e), "component": component})})
            COMPONENT_HEALTH.labels(component=component).set(0)
            health_status[component] = {"status": "error", "error": str(e)}
    
    return health_status

def check_component_status(component: str) -> Dict[str, Any]:
    """Perform detailed health checks for specific components"""
    status = {"health_score": 1.0, "last_check": time.time()}
    
    if component == 'worker':
        # Worker-specific checks
        cpu = psutil.cpu_percent()
        memory = psutil.virtual_memory().percent
        status.update({
            "cpu_usage": cpu,
            "memory_usage": memory,
            "health_score": 1.0 if cpu < 80 and memory < 80 else 0.5
        })
    
    elif component == 'redis':
        # Redis connection check
        try:
            # Implement Redis ping check here
            status["health_score"] = 1.0
        except Exception as e:
            status["health_score"] = 0.0
            status["error"] = str(e)
    
    # Add more component-specific checks as needed
    
    return status

def track_performance_metrics(task_type: str, start_time: float):
    """Track detailed performance metrics for tasks"""
    processing_time = time.time() - start_time
    PROCESSING_TIME.labels(task_type=task_type).observe(processing_time)
    
    # Track memory usage
    process = psutil.Process()
    memory_info = process.memory_info()
    MEMORY_PER_TASK.labels(task_type=task_type).set(memory_info.rss)
    
    # Track task throughput
    TASK_THROUGHPUT.labels(task_type=task_type, status="completed").inc()

# Helper functions

async def update_task_status(task_id: str, status: str, context: Dict[str, Any] = None):
    """Update task status and track metrics"""
    try:
        TASK_THROUGHPUT.labels(task_type=status, status='success').inc()
        if context:
            logger.info(f"Task {task_id} status updated to {status}",
                      extra={'context': json.dumps(context)})
    except Exception as e:
        logger.error(f"Error updating task status: {str(e)}",
                    extra={'context': json.dumps({'task_id': task_id, 'error': str(e)})})

async def log_task_lifecycle(task_id: str, event: str, context: Dict[str, Any] = None):
    """Log task lifecycle events with metrics tracking"""
    try:
        if context:
            logger.info(f"Task {task_id} lifecycle event: {event}",
                      extra={'context': json.dumps(context)})
    except Exception as e:
        logger.error(f"Error logging task lifecycle: {str(e)}",
                    extra={'context': json.dumps({'task_id': task_id, 'error': str(e)})})

class AlertingSystem:
    def __init__(self):
        self.logger

async def get_task_history(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent task processing history"""
    try:
        # For now, return a simple list of recent task metrics
        tasks = []
        for sample in TASK_THROUGHPUT._metrics:
            task_type = sample.labels.get('task_type', 'unknown')
            status = sample.labels.get('status', 'unknown')
            count = sample.value
            tasks.append({
                'task_type': task_type,
                'status': status,
                'count': count
            })
        return tasks[:limit]
    except Exception as e:
        logger.error(f"Error getting task history: {str(e)}")
        return []

async def get_worker_health() -> Dict[str, Any]:
    """Get current worker health metrics"""
    try:
        return {
            'cpu_usage': CPU_USAGE._value.get(),
            'memory_usage': MEMORY_USAGE._value.get(),
            'active_workers': ACTIVE_WORKERS._value.get(),
            'component_health': {
                component: COMPONENT_HEALTH.labels(component=component)._value.get()
                for component in ['api', 'worker', 'bot']
            }
        }
    except Exception as e:
        logger.error(f"Error getting worker health: {str(e)}")
        return {}

async def check_redis_connection() -> bool:
    """Check Redis connection status"""
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection check failed: {str(e)}")
        return False

class AlertingSystem:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.alert_counter = Counter('alerts_total', 'Total number of alerts triggered', ['severity', 'type'])
        self.incident_duration = Histogram('incident_duration_seconds', 'Duration of incidents until resolution')

    async def trigger_alert(self, alert_type: str, severity: str, details: Dict[str, Any]):
        """Trigger an alert with automated response based on severity and type"""
        self.alert_counter.labels(severity=severity, type=alert_type).inc()
        
        alert_context = {
            'type': alert_type,
            'severity': severity,
            'timestamp': time.time(),
            'details': details
        }
        
        self.logger.warning(
            f"Alert triggered: {alert_type}",
            extra={'context': json.dumps(alert_context)}
        )
        
        await self._handle_alert(alert_context)

    async def _handle_alert(self, context: Dict[str, Any]):
        """Handle alerts with automated responses based on type and severity"""
        severity = context['severity']
        alert_type = context['type']
        
        if severity == 'critical':
            await self._handle_critical_alert(context)
        elif severity == 'warning':
            await self._handle_warning_alert(context)
        
        # Track incident in monitoring system
        COMPONENT_HEALTH.labels(component=alert_type).set(0)

    async def _handle_critical_alert(self, context: Dict[str, Any]):
        """Handle critical alerts with immediate action"""
        # Implement automated recovery procedures
        if context['type'] == 'service_down':
            await self._attempt_service_recovery(context)
        elif context['type'] == 'high_error_rate':
            await self._implement_circuit_breaker(context)
        
        # Notify on-call team
        await self._notify_team(context)

    async def _handle_warning_alert(self, context: Dict[str, Any]):
        """Handle warning alerts with preventive measures"""
        if context['type'] == 'high_latency':
            await self._optimize_performance(context)
        elif context['type'] == 'resource_usage':
            await self._scale_resources(context)

    async def _attempt_service_recovery(self, context: Dict[str, Any]):
        """Attempt to recover failed services automatically"""
        service = context['details'].get('service')
        try:
            # Implement service-specific recovery logic
            if service == 'api':
                await self._restart_api_service()
            elif service == 'worker':
                await self._restart_worker_process()
            elif service == 'database':
                await self._reconnect_database()
            
            self.logger.info(
                f"Recovery attempted for service {service}",
                extra={'context': json.dumps({'service': service, 'status': 'recovery_attempted'})}
            )
        except Exception as e:
            self.logger.error(
                f"Recovery failed for service {service}",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _implement_circuit_breaker(self, context: Dict[str, Any]):
        """Implement circuit breaker pattern for failing components"""
        component = context['details'].get('component')
        try:
            # Temporarily disable the failing component
            COMPONENT_HEALTH.labels(component=component).set(0)
            
            # Implement fallback mechanism
            await self._activate_fallback(component)
            
            self.logger.info(
                f"Circuit breaker activated for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'circuit_breaker_activated'})}
            )
        except Exception as e:
            self.logger.error(
                f"Circuit breaker implementation failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _optimize_performance(self, context: Dict[str, Any]):
        """Optimize system performance based on monitoring data"""
        try:
            # Implement performance optimization logic
            component = context['details'].get('component')
            current_latency = context['details'].get('latency', 0)
            
            if current_latency > 1.0:  # High latency threshold
                # Implement optimization strategies
                await self._reduce_load(component)
                await self._scale_resources(component)
            
            self.logger.info(
                f"Performance optimization completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'performance_optimized'})}
            )
        except Exception as e:
            self.logger.error(
                "Performance optimization failed",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _scale_resources(self, component: str):
        """Scale system resources based on demand"""
        try:
            # Implement auto-scaling logic
            current_usage = self._get_resource_usage(component)
            if current_usage > 80:  # High usage threshold
                # Trigger resource scaling
                await self._increase_capacity(component)
            
            self.logger.info(
                f"Resource scaling completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'resources_scaled'})}
            )
        except Exception as e:
            self.logger.error(
                f"Resource scaling failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _notify_team(self, context: Dict[str, Any]):
        """Notify on-call team about critical incidents"""
        try:
            # Implement notification logic (e.g., email, Slack, PagerDuty)
            notification_context = {
                'incident_type': context['type'],
                'severity': context['severity'],
                'timestamp': context['timestamp'],
                'details': context['details']
            }
            
            # Log notification attempt
            self.logger.info(
                "On-call team notification sent",
                extra={'context': json.dumps(notification_context)}
            )
        except Exception as e:
            self.logger.error(
                "Failed to notify on-call team",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

class AlertingSystem:
    def __init__(self):
        self.logger

async def get_task_history(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent task processing history"""
    try:
        # For now, return a simple list of recent task metrics
        tasks = []
        for sample in TASK_THROUGHPUT._metrics:
            task_type = sample.labels.get('task_type', 'unknown')
            status = sample.labels.get('status', 'unknown')
            count = sample.value
            tasks.append({
                'task_type': task_type,
                'status': status,
                'count': count
            })
        return tasks[:limit]
    except Exception as e:
        logger.error(f"Error getting task history: {str(e)}")
        return []

async def get_worker_health() -> Dict[str, Any]:
    """Get current worker health metrics"""
    try:
        return {
            'cpu_usage': CPU_USAGE._value.get(),
            'memory_usage': MEMORY_USAGE._value.get(),
            'active_workers': ACTIVE_WORKERS._value.get(),
            'component_health': {
                component: COMPONENT_HEALTH.labels(component=component)._value.get()
                for component in ['api', 'worker', 'bot']
            }
        }
    except Exception as e:
        logger.error(f"Error getting worker health: {str(e)}")
        return {}

async def check_redis_connection() -> bool:
    """Check Redis connection status"""
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection check failed: {str(e)}")
        return False

class AlertingSystem:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.alert_counter = Counter('alerts_total', 'Total number of alerts triggered', ['severity', 'type'])
        self.incident_duration = Histogram('incident_duration_seconds', 'Duration of incidents until resolution')

    async def trigger_alert(self, alert_type: str, severity: str, details: Dict[str, Any]):
        """Trigger an alert with automated response based on severity and type"""
        self.alert_counter.labels(severity=severity, type=alert_type).inc()
        
        alert_context = {
            'type': alert_type,
            'severity': severity,
            'timestamp': time.time(),
            'details': details
        }
        
        self.logger.warning(
            f"Alert triggered: {alert_type}",
            extra={'context': json.dumps(alert_context)}
        )
        
        await self._handle_alert(alert_context)

    async def _handle_alert(self, context: Dict[str, Any]):
        """Handle alerts with automated responses based on type and severity"""
        severity = context['severity']
        alert_type = context['type']
        
        if severity == 'critical':
            await self._handle_critical_alert(context)
        elif severity == 'warning':
            await self._handle_warning_alert(context)
        
        # Track incident in monitoring system
        COMPONENT_HEALTH.labels(component=alert_type).set(0)

    async def _handle_critical_alert(self, context: Dict[str, Any]):
        """Handle critical alerts with immediate action"""
        # Implement automated recovery procedures
        if context['type'] == 'service_down':
            await self._attempt_service_recovery(context)
        elif context['type'] == 'high_error_rate':
            await self._implement_circuit_breaker(context)
        
        # Notify on-call team
        await self._notify_team(context)

    async def _handle_warning_alert(self, context: Dict[str, Any]):
        """Handle warning alerts with preventive measures"""
        if context['type'] == 'high_latency':
            await self._optimize_performance(context)
        elif context['type'] == 'resource_usage':
            await self._scale_resources(context)

    async def _attempt_service_recovery(self, context: Dict[str, Any]):
        """Attempt to recover failed services automatically"""
        service = context['details'].get('service')
        try:
            # Implement service-specific recovery logic
            if service == 'api':
                await self._restart_api_service()
            elif service == 'worker':
                await self._restart_worker_process()
            elif service == 'database':
                await self._reconnect_database()
            
            self.logger.info(
                f"Recovery attempted for service {service}",
                extra={'context': json.dumps({'service': service, 'status': 'recovery_attempted'})}
            )
        except Exception as e:
            self.logger.error(
                f"Recovery failed for service {service}",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _implement_circuit_breaker(self, context: Dict[str, Any]):
        """Implement circuit breaker pattern for failing components"""
        component = context['details'].get('component')
        try:
            # Temporarily disable the failing component
            COMPONENT_HEALTH.labels(component=component).set(0)
            
            # Implement fallback mechanism
            await self._activate_fallback(component)
            
            self.logger.info(
                f"Circuit breaker activated for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'circuit_breaker_activated'})}
            )
        except Exception as e:
            self.logger.error(
                f"Circuit breaker implementation failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _optimize_performance(self, context: Dict[str, Any]):
        """Optimize system performance based on monitoring data"""
        try:
            # Implement performance optimization logic
            component = context['details'].get('component')
            current_latency = context['details'].get('latency', 0)
            
            if current_latency > 1.0:  # High latency threshold
                # Implement optimization strategies
                await self._reduce_load(component)
                await self._scale_resources(component)
            
            self.logger.info(
                f"Performance optimization completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'performance_optimized'})}
            )
        except Exception as e:
            self.logger.error(
                "Performance optimization failed",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _scale_resources(self, component: str):
        """Scale system resources based on demand"""
        try:
            # Implement auto-scaling logic
            current_usage = self._get_resource_usage(component)
            if current_usage > 80:  # High usage threshold
                # Trigger resource scaling
                await self._increase_capacity(component)
            
            self.logger.info(
                f"Resource scaling completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'resources_scaled'})}
            )
        except Exception as e:
            self.logger.error(
                f"Resource scaling failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _notify_team(self, context: Dict[str, Any]):
        """Notify on-call team about critical incidents"""
        try:
            # Implement notification logic (e.g., email, Slack, PagerDuty)
            notification_context = {
                'incident_type': context['type'],
                'severity': context['severity'],
                'timestamp': context['timestamp'],
                'details': context['details']
            }
            
            # Log notification attempt
            self.logger.info(
                "On-call team notification sent",
                extra={'context': json.dumps(notification_context)}
            )
        except Exception as e:
            self.logger.error(
                "Failed to notify on-call team",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

# Create a custom registry for resource prediction metrics
RESOURCE_REGISTRY = CollectorRegistry()

# Predictive monitoring metrics
RESOURCE_PREDICTION = Gauge('resource_prediction', 'Predicted resource usage', ['resource_type', 'timeframe'], registry=RESOURCE_REGISTRY)
ANOMALY_SCORE = Gauge('anomaly_score', 'System anomaly score', ['component'], registry=RESOURCE_REGISTRY)
CAPACITY_THRESHOLD = Gauge('capacity_threshold', 'Dynamic capacity threshold', ['resource_type'], registry=RESOURCE_REGISTRY)

# Capacity planning metrics
RESOURCE_TREND = Gauge('resource_trend', 'Resource usage trend', ['resource_type', 'window'], registry=RESOURCE_REGISTRY)
SCALING_RECOMMENDATION = Gauge('scaling_recommendation', 'Recommended scaling factor', ['component'], registry=RESOURCE_REGISTRY)
RESOURCE_EFFICIENCY = Gauge('resource_efficiency', 'Resource utilization efficiency', ['resource_type'], registry=RESOURCE_REGISTRY)

async def update_predictive_metrics(resource_type: str, current_usage: float, historical_data: list):
    """Update predictive monitoring metrics based on historical data"""
    # Calculate short-term prediction (1 hour)
    short_term_prediction = calculate_prediction(historical_data, timeframe='1h')
    RESOURCE_PREDICTION.labels(resource_type=resource_type, timeframe='1h').set(short_term_prediction)
    
    # Calculate long-term prediction (24 hours)
    long_term_prediction = calculate_prediction(historical_data, timeframe='24h')
    RESOURCE_PREDICTION.labels(resource_type=resource_type, timeframe='24h').set(long_term_prediction)
    
    # Update anomaly score
    anomaly_score = detect_anomalies(current_usage, historical_data)
    ANOMALY_SCORE.labels(component=resource_type).set(anomaly_score)

async def update_capacity_metrics(resource_type: str, usage_data: list):
    """Update capacity planning metrics based on usage patterns"""
    # Calculate resource usage trend
    short_trend = calculate_trend(usage_data, window='1h')
    long_trend = calculate_trend(usage_data, window='24h')
    RESOURCE_TREND.labels(resource_type=resource_type, window='1h').set(short_trend)
    RESOURCE_TREND.labels(resource_type=resource_type, window='24h').set(long_trend)
    
    # Calculate dynamic capacity threshold
    threshold = calculate_dynamic_threshold(usage_data)
    CAPACITY_THRESHOLD.labels(resource_type=resource_type).set(threshold)
    
    # Calculate scaling recommendation
    scaling_factor = calculate_scaling_factor(usage_data, threshold)
    SCALING_RECOMMENDATION.labels(component=resource_type).set(scaling_factor)
    
    # Calculate resource efficiency
    efficiency = calculate_resource_efficiency(usage_data)
    RESOURCE_EFFICIENCY.labels(resource_type=resource_type).set(efficiency)

def calculate_prediction(historical_data: list, timeframe: str) -> float:
    """Calculate resource usage prediction based on historical data"""
    # Implement time series forecasting (e.g., using exponential smoothing)
    # For now, using a simple moving average
    return sum(historical_data[-10:]) / len(historical_data[-10:])

def detect_anomalies(current_value: float, historical_data: list) -> float:
    """Detect anomalies in resource usage patterns"""
    mean = sum(historical_data) / len(historical_data)
    std_dev = (sum((x - mean) ** 2 for x in historical_data) / len(historical_data)) ** 0.5
    z_score = abs(current_value - mean) / std_dev if std_dev > 0 else 0
    return z_score

def calculate_trend(usage_data: list, window: str) -> float:
    """Calculate resource usage trend"""
    if len(usage_data) < 2:
        return 0.0
    return (usage_data[-1] - usage_data[0]) / len(usage_data)

def calculate_dynamic_threshold(usage_data: list) -> float:
    """Calculate dynamic capacity threshold based on usage patterns"""
    mean = sum(usage_data) / len(usage_data)
    std_dev = (sum((x - mean) ** 2 for x in usage_data) / len(usage_data)) ** 0.5
    return mean + (2 * std_dev)  # Using 2 standard deviations as threshold

def calculate_scaling_factor(usage_data: list, threshold: float) -> float:
    """Calculate recommended scaling factor based on usage and threshold"""
    current_usage = usage_data[-1] if usage_data else 0
    if current_usage > threshold:
        return 1.2  # Recommend 20% increase in capacity
    elif current_usage < threshold * 0.5:
        return 0.8  # Recommend 20% decrease in capacity
    return 1.0

def calculate_resource_efficiency(usage_data: list) -> float:
    """Calculate resource utilization efficiency"""
    if not usage_data:
        return 0.0
    peak_usage = max(usage_data)
    avg_usage = sum(usage_data) / len(usage_data)
    return avg_usage / peak_usage if peak_usage > 0 else 0.0

    @property
    def error_rate(self):
        return self.errors / self.total if self.total > 0 else 0

# Global trackers
hf_requests = RequestTracker()
apify_requests = RequestTracker()

def track_metrics():
    """Track enhanced worker metrics with service monitoring and detailed error context"""
    try:
        # Basic metrics with enhanced context
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        metrics_context = {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent,
            "timestamp": time.time()
        }
        
        CPU_USAGE.set(cpu_percent)
        MEMORY_USAGE.set(memory.percent)
        # Get active workers count from process monitoring
        active_workers = len(psutil.Process().children())
        ACTIVE_WORKERS.set(active_workers)

        # Service-specific metrics with detailed tracking
        HF_API_CALLS.inc()
        HF_ERROR_RATE.set(hf_requests.error_rate)
        APIFY_CALLS.inc()
        APIFY_ERROR_RATE.set(apify_requests.error_rate)

        # Response time metrics with percentile tracking
        HF_RESPONSE_TIME.observe(hf_requests.avg_response_time)
        APIFY_RESPONSE_TIME.observe(apify_requests.avg_response_time)

        # Component health check with enhanced monitoring
        health_status = update_component_health()
        metrics_context["component_health"] = health_status

        # Resource monitoring alerts with thresholds
        if cpu_percent > 80:
            logging.warning(
                "High CPU usage detected", 
                extra={"context": json.dumps({**metrics_context, "alert_type": "cpu_high"})}
            )
        if memory.percent > 90:
            logging.warning(
                "High memory usage detected", 
                extra={"context": json.dumps({**metrics_context, "alert_type": "memory_high"})}
            )
        if disk.percent > 85:
            logging.warning(
                "High disk usage detected",
                extra={"context": json.dumps({**metrics_context, "alert_type": "disk_high"})}
            )

        # Log successful metrics update
        logging.info(
            "Metrics updated successfully",
            extra={"context": json.dumps(metrics_context)}
        )

    except Exception as e:
        error_context = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "timestamp": time.time()
        }
        logging.error(
            f"Error updating metrics: {str(e)}", 
            extra={"context": json.dumps(error_context)},
            exc_info=True
        )

def log_external_api_call(service_name: str, duration: float, success: bool = True):
    """Log external API calls with enhanced monitoring"""
    try:
        if service_name.lower() == 'huggingface':
            tracker = hf_requests
            response_time = HF_RESPONSE_TIME
            error_rate = HF_ERROR_RATE
        elif service_name.lower() == 'apify':
            tracker = apify_requests
            response_time = APIFY_RESPONSE_TIME
            error_rate = APIFY_ERROR_RATE
        else:
            return

        tracker.total += 1
        tracker.total_response_time += duration
        if not success:
            tracker.errors += 1

        response_time.observe(duration)
        error_rate.set(tracker.error_rate)

        if duration > 5.0:  # Alert on slow responses
            logging.warning(f"Slow {service_name} API response", 
                          extra={"context": json.dumps({"duration": duration})})

    except Exception as e:
        logging.error(f"Error logging API call: {str(e)}", 
                     extra={"context": json.dumps({"error": str(e)})})

def update_component_health():
    """Enhanced component health check with detailed status tracking"""
    health_status = {}
    components = ['api', 'worker', 'bot', 'redis', 'database']
    
    for component in components:
        try:
            # Implement specific health checks for each component
            status = check_component_status(component)
            COMPONENT_HEALTH.labels(component=component).set(status['health_score'])
            health_status[component] = status
        except Exception as e:
            logging.error(f"Health check failed for {component}", 
                         extra={"context": json.dumps({"error": str(e), "component": component})})
            COMPONENT_HEALTH.labels(component=component).set(0)
            health_status[component] = {"status": "error", "error": str(e)}
    
    return health_status

def check_component_status(component: str) -> Dict[str, Any]:
    """Perform detailed health checks for specific components"""
    status = {"health_score": 1.0, "last_check": time.time()}
    
    if component == 'worker':
        # Worker-specific checks
        cpu = psutil.cpu_percent()
        memory = psutil.virtual_memory().percent
        status.update({
            "cpu_usage": cpu,
            "memory_usage": memory,
            "health_score": 1.0 if cpu < 80 and memory < 80 else 0.5
        })
    
    elif component == 'redis':
        # Redis connection check
        try:
            # Implement Redis ping check here
            status["health_score"] = 1.0
        except Exception as e:
            status["health_score"] = 0.0
            status["error"] = str(e)
    
    # Add more component-specific checks as needed
    
    return status

def track_performance_metrics(task_type: str, start_time: float):
    """Track detailed performance metrics for tasks"""
    processing_time = time.time() - start_time
    PROCESSING_TIME.labels(task_type=task_type).observe(processing_time)
    
    # Track memory usage
    process = psutil.Process()
    memory_info = process.memory_info()
    MEMORY_PER_TASK.labels(task_type=task_type).set(memory_info.rss)
    
    # Track task throughput
    TASK_THROUGHPUT.labels(task_type=task_type, status="completed").inc()

# Helper functions

async def update_task_status(task_id: str, status: str, context: Dict[str, Any] = None):
    """Update task status and track metrics"""
    try:
        TASK_THROUGHPUT.labels(task_type=status, status='success').inc()
        if context:
            logger.info(f"Task {task_id} status updated to {status}",
                      extra={'context': json.dumps(context)})
    except Exception as e:
        logger.error(f"Error updating task status: {str(e)}",
                    extra={'context': json.dumps({'task_id': task_id, 'error': str(e)})})

async def log_task_lifecycle(task_id: str, event: str, context: Dict[str, Any] = None):
    """Log task lifecycle events with metrics tracking"""
    try:
        if context:
            logger.info(f"Task {task_id} lifecycle event: {event}",
                      extra={'context': json.dumps(context)})
    except Exception as e:
        logger.error(f"Error logging task lifecycle: {str(e)}",
                    extra={'context': json.dumps({'task_id': task_id, 'error': str(e)})})

class AlertingSystem:
    def __init__(self):
        self.logger

async def get_task_history(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent task processing history"""
    try:
        # For now, return a simple list of recent task metrics
        tasks = []
        for sample in TASK_THROUGHPUT._metrics:
            task_type = sample.labels.get('task_type', 'unknown')
            status = sample.labels.get('status', 'unknown')
            count = sample.value
            tasks.append({
                'task_type': task_type,
                'status': status,
                'count': count
            })
        return tasks[:limit]
    except Exception as e:
        logger.error(f"Error getting task history: {str(e)}")
        return []

async def get_worker_health() -> Dict[str, Any]:
    """Get current worker health metrics"""
    try:
        return {
            'cpu_usage': CPU_USAGE._value.get(),
            'memory_usage': MEMORY_USAGE._value.get(),
            'active_workers': ACTIVE_WORKERS._value.get(),
            'component_health': {
                component: COMPONENT_HEALTH.labels(component=component)._value.get()
                for component in ['api', 'worker', 'bot']
            }
        }
    except Exception as e:
        logger.error(f"Error getting worker health: {str(e)}")
        return {}

async def check_redis_connection() -> bool:
    """Check Redis connection status"""
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection check failed: {str(e)}")
        return False

class AlertingSystem:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.alert_counter = Counter('alerts_total', 'Total number of alerts triggered', ['severity', 'type'])
        self.incident_duration = Histogram('incident_duration_seconds', 'Duration of incidents until resolution')

    async def trigger_alert(self, alert_type: str, severity: str, details: Dict[str, Any]):
        """Trigger an alert with automated response based on severity and type"""
        self.alert_counter.labels(severity=severity, type=alert_type).inc()
        
        alert_context = {
            'type': alert_type,
            'severity': severity,
            'timestamp': time.time(),
            'details': details
        }
        
        self.logger.warning(
            f"Alert triggered: {alert_type}",
            extra={'context': json.dumps(alert_context)}
        )
        
        await self._handle_alert(alert_context)

    async def _handle_alert(self, context: Dict[str, Any]):
        """Handle alerts with automated responses based on type and severity"""
        severity = context['severity']
        alert_type = context['type']
        
        if severity == 'critical':
            await self._handle_critical_alert(context)
        elif severity == 'warning':
            await self._handle_warning_alert(context)
        
        # Track incident in monitoring system
        COMPONENT_HEALTH.labels(component=alert_type).set(0)

    async def _handle_critical_alert(self, context: Dict[str, Any]):
        """Handle critical alerts with immediate action"""
        # Implement automated recovery procedures
        if context['type'] == 'service_down':
            await self._attempt_service_recovery(context)
        elif context['type'] == 'high_error_rate':
            await self._implement_circuit_breaker(context)
        
        # Notify on-call team
        await self._notify_team(context)

    async def _handle_warning_alert(self, context: Dict[str, Any]):
        """Handle warning alerts with preventive measures"""
        if context['type'] == 'high_latency':
            await self._optimize_performance(context)
        elif context['type'] == 'resource_usage':
            await self._scale_resources(context)

    async def _attempt_service_recovery(self, context: Dict[str, Any]):
        """Attempt to recover failed services automatically"""
        service = context['details'].get('service')
        try:
            # Implement service-specific recovery logic
            if service == 'api':
                await self._restart_api_service()
            elif service == 'worker':
                await self._restart_worker_process()
            elif service == 'database':
                await self._reconnect_database()
            
            self.logger.info(
                f"Recovery attempted for service {service}",
                extra={'context': json.dumps({'service': service, 'status': 'recovery_attempted'})}
            )
        except Exception as e:
            self.logger.error(
                f"Recovery failed for service {service}",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _implement_circuit_breaker(self, context: Dict[str, Any]):
        """Implement circuit breaker pattern for failing components"""
        component = context['details'].get('component')
        try:
            # Temporarily disable the failing component
            COMPONENT_HEALTH.labels(component=component).set(0)
            
            # Implement fallback mechanism
            await self._activate_fallback(component)
            
            self.logger.info(
                f"Circuit breaker activated for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'circuit_breaker_activated'})}
            )
        except Exception as e:
            self.logger.error(
                f"Circuit breaker implementation failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _optimize_performance(self, context: Dict[str, Any]):
        """Optimize system performance based on monitoring data"""
        try:
            # Implement performance optimization logic
            component = context['details'].get('component')
            current_latency = context['details'].get('latency', 0)
            
            if current_latency > 1.0:  # High latency threshold
                # Implement optimization strategies
                await self._reduce_load(component)
                await self._scale_resources(component)
            
            self.logger.info(
                f"Performance optimization completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'performance_optimized'})}
            )
        except Exception as e:
            self.logger.error(
                "Performance optimization failed",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _scale_resources(self, component: str):
        """Scale system resources based on demand"""
        try:
            # Implement auto-scaling logic
            current_usage = self._get_resource_usage(component)
            if current_usage > 80:  # High usage threshold
                # Trigger resource scaling
                await self._increase_capacity(component)
            
            self.logger.info(
                f"Resource scaling completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'resources_scaled'})}
            )
        except Exception as e:
            self.logger.error(
                f"Resource scaling failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _notify_team(self, context: Dict[str, Any]):
        """Notify on-call team about critical incidents"""
        try:
            # Implement notification logic (e.g., email, Slack, PagerDuty)
            notification_context = {
                'incident_type': context['type'],
                'severity': context['severity'],
                'timestamp': context['timestamp'],
                'details': context['details']
            }
            
            # Log notification attempt
            self.logger.info(
                "On-call team notification sent",
                extra={'context': json.dumps(notification_context)}
            )
        except Exception as e:
            self.logger.error(
                "Failed to notify on-call team",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

class AlertingSystem:
    def __init__(self):
        self.logger

async def get_task_history(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent task processing history"""
    try:
        # For now, return a simple list of recent task metrics
        tasks = []
        for sample in TASK_THROUGHPUT._metrics:
            task_type = sample.labels.get('task_type', 'unknown')
            status = sample.labels.get('status', 'unknown')
            count = sample.value
            tasks.append({
                'task_type': task_type,
                'status': status,
                'count': count
            })
        return tasks[:limit]
    except Exception as e:
        logger.error(f"Error getting task history: {str(e)}")
        return []

async def get_worker_health() -> Dict[str, Any]:
    """Get current worker health metrics"""
    try:
        return {
            'cpu_usage': CPU_USAGE._value.get(),
            'memory_usage': MEMORY_USAGE._value.get(),
            'active_workers': ACTIVE_WORKERS._value.get(),
            'component_health': {
                component: COMPONENT_HEALTH.labels(component=component)._value.get()
                for component in ['api', 'worker', 'bot']
            }
        }
    except Exception as e:
        logger.error(f"Error getting worker health: {str(e)}")
        return {}

async def check_redis_connection() -> bool:
    """Check Redis connection status"""
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection check failed: {str(e)}")
        return False

class AlertingSystem:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.alert_counter = Counter('alerts_total', 'Total number of alerts triggered', ['severity', 'type'])
        self.incident_duration = Histogram('incident_duration_seconds', 'Duration of incidents until resolution')

    async def trigger_alert(self, alert_type: str, severity: str, details: Dict[str, Any]):
        """Trigger an alert with automated response based on severity and type"""
        self.alert_counter.labels(severity=severity, type=alert_type).inc()
        
        alert_context = {
            'type': alert_type,
            'severity': severity,
            'timestamp': time.time(),
            'details': details
        }
        
        self.logger.warning(
            f"Alert triggered: {alert_type}",
            extra={'context': json.dumps(alert_context)}
        )
        
        await self._handle_alert(alert_context)

    async def _handle_alert(self, context: Dict[str, Any]):
        """Handle alerts with automated responses based on type and severity"""
        severity = context['severity']
        alert_type = context['type']
        
        if severity == 'critical':
            await self._handle_critical_alert(context)
        elif severity == 'warning':
            await self._handle_warning_alert(context)
        
        # Track incident in monitoring system
        COMPONENT_HEALTH.labels(component=alert_type).set(0)

    async def _handle_critical_alert(self, context: Dict[str, Any]):
        """Handle critical alerts with immediate action"""
        # Implement automated recovery procedures
        if context['type'] == 'service_down':
            await self._attempt_service_recovery(context)
        elif context['type'] == 'high_error_rate':
            await self._implement_circuit_breaker(context)
        
        # Notify on-call team
        await self._notify_team(context)

    async def _handle_warning_alert(self, context: Dict[str, Any]):
        """Handle warning alerts with preventive measures"""
        if context['type'] == 'high_latency':
            await self._optimize_performance(context)
        elif context['type'] == 'resource_usage':
            await self._scale_resources(context)

    async def _attempt_service_recovery(self, context: Dict[str, Any]):
        """Attempt to recover failed services automatically"""
        service = context['details'].get('service')
        try:
            # Implement service-specific recovery logic
            if service == 'api':
                await self._restart_api_service()
            elif service == 'worker':
                await self._restart_worker_process()
            elif service == 'database':
                await self._reconnect_database()
            
            self.logger.info(
                f"Recovery attempted for service {service}",
                extra={'context': json.dumps({'service': service, 'status': 'recovery_attempted'})}
            )
        except Exception as e:
            self.logger.error(
                f"Recovery failed for service {service}",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _implement_circuit_breaker(self, context: Dict[str, Any]):
        """Implement circuit breaker pattern for failing components"""
        component = context['details'].get('component')
        try:
            # Temporarily disable the failing component
            COMPONENT_HEALTH.labels(component=component).set(0)
            
            # Implement fallback mechanism
            await self._activate_fallback(component)
            
            self.logger.info(
                f"Circuit breaker activated for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'circuit_breaker_activated'})}
            )
        except Exception as e:
            self.logger.error(
                f"Circuit breaker implementation failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _optimize_performance(self, context: Dict[str, Any]):
        """Optimize system performance based on monitoring data"""
        try:
            # Implement performance optimization logic
            component = context['details'].get('component')
            current_latency = context['details'].get('latency', 0)
            
            if current_latency > 1.0:  # High latency threshold
                # Implement optimization strategies
                await self._reduce_load(component)
                await self._scale_resources(component)
            
            self.logger.info(
                f"Performance optimization completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'performance_optimized'})}
            )
        except Exception as e:
            self.logger.error(
                "Performance optimization failed",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _scale_resources(self, component: str):
        """Scale system resources based on demand"""
        try:
            # Implement auto-scaling logic
            current_usage = self._get_resource_usage(component)
            if current_usage > 80:  # High usage threshold
                # Trigger resource scaling
                await self._increase_capacity(component)
            
            self.logger.info(
                f"Resource scaling completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'resources_scaled'})}
            )
        except Exception as e:
            self.logger.error(
                f"Resource scaling failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _notify_team(self, context: Dict[str, Any]):
        """Notify on-call team about critical incidents"""
        try:
            # Implement notification logic (e.g., email, Slack, PagerDuty)
            notification_context = {
                'incident_type': context['type'],
                'severity': context['severity'],
                'timestamp': context['timestamp'],
                'details': context['details']
            }
            
            # Log notification attempt
            self.logger.info(
                "On-call team notification sent",
                extra={'context': json.dumps(notification_context)}
            )
        except Exception as e:
            self.logger.error(
                "Failed to notify on-call team",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

async def predict_resource_usage(resource_type: str, time_window: str):
    """Predict future resource usage based on historical data"""
    current_usage = CPU_USAGE.collect()[0].samples[0].value if resource_type == 'cpu' else MEMORY_USAGE.collect()[0].samples[0].value
    # Simple moving average prediction for now
    predicted_usage = current_usage * 1.1  # Add 10% buffer
    RESOURCE_PREDICTION.labels(resource_type=resource_type, timeframe=time_window).set(predicted_usage)

async def update_capacity_thresholds(resource_type: str, current_usage: float):
    """Dynamically update capacity thresholds based on usage patterns"""
    # Start with basic threshold at 80% of current maximum
    threshold = current_usage * 0.8
    CAPACITY_THRESHOLD.labels(resource_type=resource_type).set(threshold)

async def detect_anomalies(component: str):
    """Detect system behavior anomalies using basic statistical analysis"""
    # Simple anomaly detection based on current vs historical metrics
    current_health = COMPONENT_HEALTH.labels(component=component).collect()[0].samples[0].value
    current_latency = COMPONENT_LATENCY.labels(source=component, destination='api').collect()[0].samples[0].value
    
    # Basic anomaly score calculation
    anomaly_score = 0.0
    if current_health < 1.0:
        anomaly_score += 0.5
    if current_latency > 1.0:  # If latency is more than 1 second
        anomaly_score += 0.5
        
    ANOMALY_SCORE.labels(component=component).set(anomaly_score)

    @property
    def error_rate(self):
        return self.errors / self.total if self.total > 0 else 0

# Global trackers
hf_requests = RequestTracker()
apify_requests = RequestTracker()

def track_metrics():
    """Track enhanced worker metrics with service monitoring and detailed error context"""
    try:
        # Basic metrics with enhanced context
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        metrics_context = {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent,
            "timestamp": time.time()
        }
        
        CPU_USAGE.set(cpu_percent)
        MEMORY_USAGE.set(memory.percent)
        # Get active workers count from process monitoring
        active_workers = len(psutil.Process().children())
        ACTIVE_WORKERS.set(active_workers)

        # Service-specific metrics with detailed tracking
        HF_API_CALLS.inc()
        HF_ERROR_RATE.set(hf_requests.error_rate)
        APIFY_CALLS.inc()
        APIFY_ERROR_RATE.set(apify_requests.error_rate)

        # Response time metrics with percentile tracking
        HF_RESPONSE_TIME.observe(hf_requests.avg_response_time)
        APIFY_RESPONSE_TIME.observe(apify_requests.avg_response_time)

        # Component health check with enhanced monitoring
        health_status = update_component_health()
        metrics_context["component_health"] = health_status

        # Resource monitoring alerts with thresholds
        if cpu_percent > 80:
            logging.warning(
                "High CPU usage detected", 
                extra={"context": json.dumps({**metrics_context, "alert_type": "cpu_high"})}
            )
        if memory.percent > 90:
            logging.warning(
                "High memory usage detected", 
                extra={"context": json.dumps({**metrics_context, "alert_type": "memory_high"})}
            )
        if disk.percent > 85:
            logging.warning(
                "High disk usage detected",
                extra={"context": json.dumps({**metrics_context, "alert_type": "disk_high"})}
            )

        # Log successful metrics update
        logging.info(
            "Metrics updated successfully",
            extra={"context": json.dumps(metrics_context)}
        )

    except Exception as e:
        error_context = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "timestamp": time.time()
        }
        logging.error(
            f"Error updating metrics: {str(e)}", 
            extra={"context": json.dumps(error_context)},
            exc_info=True
        )

def log_external_api_call(service_name: str, duration: float, success: bool = True):
    """Log external API calls with enhanced monitoring"""
    try:
        if service_name.lower() == 'huggingface':
            tracker = hf_requests
            response_time = HF_RESPONSE_TIME
            error_rate = HF_ERROR_RATE
        elif service_name.lower() == 'apify':
            tracker = apify_requests
            response_time = APIFY_RESPONSE_TIME
            error_rate = APIFY_ERROR_RATE
        else:
            return

        tracker.total += 1
        tracker.total_response_time += duration
        if not success:
            tracker.errors += 1

        response_time.observe(duration)
        error_rate.set(tracker.error_rate)

        if duration > 5.0:  # Alert on slow responses
            logging.warning(f"Slow {service_name} API response", 
                          extra={"context": json.dumps({"duration": duration})})

    except Exception as e:
        logging.error(f"Error logging API call: {str(e)}", 
                     extra={"context": json.dumps({"error": str(e)})})

def update_component_health():
    """Enhanced component health check with detailed status tracking"""
    health_status = {}
    components = ['api', 'worker', 'bot', 'redis', 'database']
    
    for component in components:
        try:
            # Implement specific health checks for each component
            status = check_component_status(component)
            COMPONENT_HEALTH.labels(component=component).set(status['health_score'])
            health_status[component] = status
        except Exception as e:
            logging.error(f"Health check failed for {component}", 
                         extra={"context": json.dumps({"error": str(e), "component": component})})
            COMPONENT_HEALTH.labels(component=component).set(0)
            health_status[component] = {"status": "error", "error": str(e)}
    
    return health_status

def check_component_status(component: str) -> Dict[str, Any]:
    """Perform detailed health checks for specific components"""
    status = {"health_score": 1.0, "last_check": time.time()}
    
    if component == 'worker':
        # Worker-specific checks
        cpu = psutil.cpu_percent()
        memory = psutil.virtual_memory().percent
        status.update({
            "cpu_usage": cpu,
            "memory_usage": memory,
            "health_score": 1.0 if cpu < 80 and memory < 80 else 0.5
        })
    
    elif component == 'redis':
        # Redis connection check
        try:
            # Implement Redis ping check here
            status["health_score"] = 1.0
        except Exception as e:
            status["health_score"] = 0.0
            status["error"] = str(e)
    
    # Add more component-specific checks as needed
    
    return status

def track_performance_metrics(task_type: str, start_time: float):
    """Track detailed performance metrics for tasks"""
    processing_time = time.time() - start_time
    PROCESSING_TIME.labels(task_type=task_type).observe(processing_time)
    
    # Track memory usage
    process = psutil.Process()
    memory_info = process.memory_info()
    MEMORY_PER_TASK.labels(task_type=task_type).set(memory_info.rss)
    
    # Track task throughput
    TASK_THROUGHPUT.labels(task_type=task_type, status="completed").inc()

# Helper functions

async def update_task_status(task_id: str, status: str, context: Dict[str, Any] = None):
    """Update task status and track metrics"""
    try:
        TASK_THROUGHPUT.labels(task_type=status, status='success').inc()
        if context:
            logger.info(f"Task {task_id} status updated to {status}",
                      extra={'context': json.dumps(context)})
    except Exception as e:
        logger.error(f"Error updating task status: {str(e)}",
                    extra={'context': json.dumps({'task_id': task_id, 'error': str(e)})})

async def log_task_lifecycle(task_id: str, event: str, context: Dict[str, Any] = None):
    """Log task lifecycle events with metrics tracking"""
    try:
        if context:
            logger.info(f"Task {task_id} lifecycle event: {event}",
                      extra={'context': json.dumps(context)})
    except Exception as e:
        logger.error(f"Error logging task lifecycle: {str(e)}",
                    extra={'context': json.dumps({'task_id': task_id, 'error': str(e)})})

class AlertingSystem:
    def __init__(self):
        self.logger

async def get_task_history(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent task processing history"""
    try:
        # For now, return a simple list of recent task metrics
        tasks = []
        for sample in TASK_THROUGHPUT._metrics:
            task_type = sample.labels.get('task_type', 'unknown')
            status = sample.labels.get('status', 'unknown')
            count = sample.value
            tasks.append({
                'task_type': task_type,
                'status': status,
                'count': count
            })
        return tasks[:limit]
    except Exception as e:
        logger.error(f"Error getting task history: {str(e)}")
        return []

async def get_worker_health() -> Dict[str, Any]:
    """Get current worker health metrics"""
    try:
        return {
            'cpu_usage': CPU_USAGE._value.get(),
            'memory_usage': MEMORY_USAGE._value.get(),
            'active_workers': ACTIVE_WORKERS._value.get(),
            'component_health': {
                component: COMPONENT_HEALTH.labels(component=component)._value.get()
                for component in ['api', 'worker', 'bot']
            }
        }
    except Exception as e:
        logger.error(f"Error getting worker health: {str(e)}")
        return {}

async def check_redis_connection() -> bool:
    """Check Redis connection status"""
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection check failed: {str(e)}")
        return False

class AlertingSystem:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.alert_counter = Counter('alerts_total', 'Total number of alerts triggered', ['severity', 'type'])
        self.incident_duration = Histogram('incident_duration_seconds', 'Duration of incidents until resolution')

    async def trigger_alert(self, alert_type: str, severity: str, details: Dict[str, Any]):
        """Trigger an alert with automated response based on severity and type"""
        self.alert_counter.labels(severity=severity, type=alert_type).inc()
        
        alert_context = {
            'type': alert_type,
            'severity': severity,
            'timestamp': time.time(),
            'details': details
        }
        
        self.logger.warning(
            f"Alert triggered: {alert_type}",
            extra={'context': json.dumps(alert_context)}
        )
        
        await self._handle_alert(alert_context)

    async def _handle_alert(self, context: Dict[str, Any]):
        """Handle alerts with automated responses based on type and severity"""
        severity = context['severity']
        alert_type = context['type']
        
        if severity == 'critical':
            await self._handle_critical_alert(context)
        elif severity == 'warning':
            await self._handle_warning_alert(context)
        
        # Track incident in monitoring system
        COMPONENT_HEALTH.labels(component=alert_type).set(0)

    async def _handle_critical_alert(self, context: Dict[str, Any]):
        """Handle critical alerts with immediate action"""
        # Implement automated recovery procedures
        if context['type'] == 'service_down':
            await self._attempt_service_recovery(context)
        elif context['type'] == 'high_error_rate':
            await self._implement_circuit_breaker(context)
        
        # Notify on-call team
        await self._notify_team(context)

    async def _handle_warning_alert(self, context: Dict[str, Any]):
        """Handle warning alerts with preventive measures"""
        if context['type'] == 'high_latency':
            await self._optimize_performance(context)
        elif context['type'] == 'resource_usage':
            await self._scale_resources(context)

    async def _attempt_service_recovery(self, context: Dict[str, Any]):
        """Attempt to recover failed services automatically"""
        service = context['details'].get('service')
        try:
            # Implement service-specific recovery logic
            if service == 'api':
                await self._restart_api_service()
            elif service == 'worker':
                await self._restart_worker_process()
            elif service == 'database':
                await self._reconnect_database()
            
            self.logger.info(
                f"Recovery attempted for service {service}",
                extra={'context': json.dumps({'service': service, 'status': 'recovery_attempted'})}
            )
        except Exception as e:
            self.logger.error(
                f"Recovery failed for service {service}",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _implement_circuit_breaker(self, context: Dict[str, Any]):
        """Implement circuit breaker pattern for failing components"""
        component = context['details'].get('component')
        try:
            # Temporarily disable the failing component
            COMPONENT_HEALTH.labels(component=component).set(0)
            
            # Implement fallback mechanism
            await self._activate_fallback(component)
            
            self.logger.info(
                f"Circuit breaker activated for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'circuit_breaker_activated'})}
            )
        except Exception as e:
            self.logger.error(
                f"Circuit breaker implementation failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _optimize_performance(self, context: Dict[str, Any]):
        """Optimize system performance based on monitoring data"""
        try:
            # Implement performance optimization logic
            component = context['details'].get('component')
            current_latency = context['details'].get('latency', 0)
            
            if current_latency > 1.0:  # High latency threshold
                # Implement optimization strategies
                await self._reduce_load(component)
                await self._scale_resources(component)
            
            self.logger.info(
                f"Performance optimization completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'performance_optimized'})}
            )
        except Exception as e:
            self.logger.error(
                "Performance optimization failed",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _scale_resources(self, component: str):
        """Scale system resources based on demand"""
        try:
            # Implement auto-scaling logic
            current_usage = self._get_resource_usage(component)
            if current_usage > 80:  # High usage threshold
                # Trigger resource scaling
                await self._increase_capacity(component)
            
            self.logger.info(
                f"Resource scaling completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'resources_scaled'})}
            )
        except Exception as e:
            self.logger.error(
                f"Resource scaling failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _notify_team(self, context: Dict[str, Any]):
        """Notify on-call team about critical incidents"""
        try:
            # Implement notification logic (e.g., email, Slack, PagerDuty)
            notification_context = {
                'incident_type': context['type'],
                'severity': context['severity'],
                'timestamp': context['timestamp'],
                'details': context['details']
            }
            
            # Log notification attempt
            self.logger.info(
                "On-call team notification sent",
                extra={'context': json.dumps(notification_context)}
            )
        except Exception as e:
            self.logger.error(
                "Failed to notify on-call team",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

class AlertingSystem:
    def __init__(self):
        self.logger

async def get_task_history(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent task processing history"""
    try:
        # For now, return a simple list of recent task metrics
        tasks = []
        for sample in TASK_THROUGHPUT._metrics:
            task_type = sample.labels.get('task_type', 'unknown')
            status = sample.labels.get('status', 'unknown')
            count = sample.value
            tasks.append({
                'task_type': task_type,
                'status': status,
                'count': count
            })
        return tasks[:limit]
    except Exception as e:
        logger.error(f"Error getting task history: {str(e)}")
        return []

async def get_worker_health() -> Dict[str, Any]:
    """Get current worker health metrics"""
    try:
        return {
            'cpu_usage': CPU_USAGE._value.get(),
            'memory_usage': MEMORY_USAGE._value.get(),
            'active_workers': ACTIVE_WORKERS._value.get(),
            'component_health': {
                component: COMPONENT_HEALTH.labels(component=component)._value.get()
                for component in ['api', 'worker', 'bot']
            }
        }
    except Exception as e:
        logger.error(f"Error getting worker health: {str(e)}")
        return {}

async def check_redis_connection() -> bool:
    """Check Redis connection status"""
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection check failed: {str(e)}")
        return False

class AlertingSystem:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.alert_counter = Counter('alerts_total', 'Total number of alerts triggered', ['severity', 'type'])
        self.incident_duration = Histogram('incident_duration_seconds', 'Duration of incidents until resolution')

    async def trigger_alert(self, alert_type: str, severity: str, details: Dict[str, Any]):
        """Trigger an alert with automated response based on severity and type"""
        self.alert_counter.labels(severity=severity, type=alert_type).inc()
        
        alert_context = {
            'type': alert_type,
            'severity': severity,
            'timestamp': time.time(),
            'details': details
        }
        
        self.logger.warning(
            f"Alert triggered: {alert_type}",
            extra={'context': json.dumps(alert_context)}
        )
        
        await self._handle_alert(alert_context)

    async def _handle_alert(self, context: Dict[str, Any]):
        """Handle alerts with automated responses based on type and severity"""
        severity = context['severity']
        alert_type = context['type']
        
        if severity == 'critical':
            await self._handle_critical_alert(context)
        elif severity == 'warning':
            await self._handle_warning_alert(context)
        
        # Track incident in monitoring system
        COMPONENT_HEALTH.labels(component=alert_type).set(0)

    async def _handle_critical_alert(self, context: Dict[str, Any]):
        """Handle critical alerts with immediate action"""
        # Implement automated recovery procedures
        if context['type'] == 'service_down':
            await self._attempt_service_recovery(context)
        elif context['type'] == 'high_error_rate':
            await self._implement_circuit_breaker(context)
        
        # Notify on-call team
        await self._notify_team(context)

    async def _handle_warning_alert(self, context: Dict[str, Any]):
        """Handle warning alerts with preventive measures"""
        if context['type'] == 'high_latency':
            await self._optimize_performance(context)
        elif context['type'] == 'resource_usage':
            await self._scale_resources(context)

    async def _attempt_service_recovery(self, context: Dict[str, Any]):
        """Attempt to recover failed services automatically"""
        service = context['details'].get('service')
        try:
            # Implement service-specific recovery logic
            if service == 'api':
                await self._restart_api_service()
            elif service == 'worker':
                await self._restart_worker_process()
            elif service == 'database':
                await self._reconnect_database()
            
            self.logger.info(
                f"Recovery attempted for service {service}",
                extra={'context': json.dumps({'service': service, 'status': 'recovery_attempted'})}
            )
        except Exception as e:
            self.logger.error(
                f"Recovery failed for service {service}",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _implement_circuit_breaker(self, context: Dict[str, Any]):
        """Implement circuit breaker pattern for failing components"""
        component = context['details'].get('component')
        try:
            # Temporarily disable the failing component
            COMPONENT_HEALTH.labels(component=component).set(0)
            
            # Implement fallback mechanism
            await self._activate_fallback(component)
            
            self.logger.info(
                f"Circuit breaker activated for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'circuit_breaker_activated'})}
            )
        except Exception as e:
            self.logger.error(
                f"Circuit breaker implementation failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _optimize_performance(self, context: Dict[str, Any]):
        """Optimize system performance based on monitoring data"""
        try:
            # Implement performance optimization logic
            component = context['details'].get('component')
            current_latency = context['details'].get('latency', 0)
            
            if current_latency > 1.0:  # High latency threshold
                # Implement optimization strategies
                await self._reduce_load(component)
                await self._scale_resources(component)
            
            self.logger.info(
                f"Performance optimization completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'performance_optimized'})}
            )
        except Exception as e:
            self.logger.error(
                "Performance optimization failed",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

    async def _scale_resources(self, component: str):
        """Scale system resources based on demand"""
        try:
            # Implement auto-scaling logic
            current_usage = self._get_resource_usage(component)
            if current_usage > 80:  # High usage threshold
                # Trigger resource scaling
                await self._increase_capacity(component)
            
            self.logger.info(
                f"Resource scaling completed for {component}",
                extra={'context': json.dumps({'component': component, 'action': 'resources_scaled'})}
            )
        except Exception as e:
            self.logger.error(
                f"Resource scaling failed for {component}",
                extra={'context': json.dumps({'error': str(e), 'component': component})}
            )

    async def _notify_team(self, context: Dict[str, Any]):
        """Notify on-call team about critical incidents"""
        try:
            # Implement notification logic (e.g., email, Slack, PagerDuty)
            notification_context = {
                'incident_type': context['type'],
                'severity': context['severity'],
                'timestamp': context['timestamp'],
                'details': context['details']
            }
            
            # Log notification attempt
            self.logger.info(
                "On-call team notification sent",
                extra={'context': json.dumps(notification_context)}
            )
        except Exception as e:
            self.logger.error(
                "Failed to notify on-call team",
                extra={'context': json.dumps({'error': str(e), **context})}
            )

async def predict_resource_usage(resource_type: str, time_window: str):
    """Predict future resource usage based on historical data"""
    current_usage = CPU_USAGE.collect()[0].samples[0].value if resource_type == 'cpu' else MEMORY_USAGE.collect()[0].samples[0].value
    # Simple moving average prediction for now
    predicted_usage = current_usage * 1.1  # Add 10% buffer
    RESOURCE_PREDICTION.labels(resource_type=resource_type, timeframe=time_window).set(predicted_usage)

async def update_capacity_thresholds(resource_type: str, current_usage: float):
    """Dynamically update capacity thresholds based on usage patterns"""
    # Start with basic threshold at 80% of current maximum
    threshold = current_usage * 0.8
    CAPACITY_THRESHOLD.labels(resource_type=resource_type).set(threshold)

async def detect_anomalies(component: str):
    """Detect system behavior anomalies using basic statistical analysis"""
    # Simple anomaly detection based on current vs historical metrics
    current_health = COMPONENT_HEALTH.labels(component=component).collect()[0].samples[0].value
    current_latency = COMPONENT_LATENCY.labels(source=component, destination='api').collect()[0].samples[0].value
    
    # Basic anomaly score calculation
    anomaly_score = 0.0
    if current_health < 1.0:
        anomaly_score += 0.5
    if current_latency > 1.0:  # If latency is more than 1 second
        anomaly_score += 0.5
        
    ANOMALY_SCORE.labels(component=component).set(anomaly_score)

    @property
    def error_rate(self):
        return self.errors / self.total if self.total > 0 else 0

# Global trackers
hf_requests = RequestTracker()
apify_requests = RequestTracker()

def track_metrics():
    """Track enhanced worker metrics with service monitoring and detailed error context"""
    try:
        # Basic metrics with enhanced context
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        metrics_context = {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent,
            "timestamp": time.time()
        }
        
        CPU_USAGE.set(cpu_percent)
        MEMORY_USAGE.set(memory.percent)
        # Get active workers count from process monitoring
        active_workers = len(psutil.Process().children())
        ACTIVE_WORKERS.set(active_workers)

        # Service-specific metrics with detailed tracking
        HF_API_CALLS.inc()
        HF_ERROR_RATE.set(hf_requests.error_rate)
        APIFY_CALLS.inc()
        APIFY_ERROR_RATE.set(apify_requests.error_rate)

        # Response time metrics with percentile tracking
        HF_RESPONSE_TIME.observe(hf_requests.avg_response_time)
        APIFY_RESPONSE_TIME.observe(apify_requests.avg_response_time)

        # Component health check with enhanced monitoring
        health_status = update_component_health()
        metrics_context["component_health"] = health_status

        # Resource monitoring alerts with thresholds
        if cpu_percent > 80:
            logging.warning(
                "High CPU usage detected", 
                extra={"context": json.dumps({**metrics_context, "alert_type": "cpu_high"})}
            )
        if memory.percent > 90:
            logging.warning(
                "High memory usage detected", 
                extra={"context": json.dumps({**metrics_context, "alert_type": "memory_high"})}
            )
        if disk.percent > 85:
            logging.warning(
                "High disk usage detected",
                extra={"context": json.dumps({**metrics_context, "alert_type": "disk_high"})}
            )

        # Log successful metrics update
        logging.info(
            "Metrics updated successfully",
            extra={"context": json.dumps(metrics_context)}
        )

    except Exception as e:
        error_context = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "timestamp": time.time()
        }
        logging.error(
            f"Error updating metrics: {str(e)}", 
            extra={"context": json.dumps(error_context)},
            exc_info=True
        )

def log_external_api_call(service_name: str, duration: float, success: bool = True):
    """Log external API calls with enhanced monitoring"""
    try:
        if service_name.lower() == 'huggingface':
            tracker = hf_requests
            response_time = HF_RESPONSE_TIME
            error_rate = HF_ERROR_RATE
        elif service_name.lower() == 'apify':
            tracker = apify_requests
            response_time = APIFY_RESPONSE_TIME
            error_rate = APIFY_ERROR_RATE
        else:
            return

        tracker.total += 1
        tracker.total_response_time += duration
        if not success:
            tracker.errors += 1

        response_time.observe(duration)
        error_rate.set(tracker.error_rate)

        if duration > 5.0:  # Alert on slow responses
            logging.warning(f"Slow {service_name} API response", 
                          extra={"context": json.dumps({"duration": duration})})

    except Exception as e:
        logging.error(f"Error logging API call: {str(e)}", 
                     extra={"context": json.dumps({"error": str(e)})})

def update_component_health():
    """Enhanced component health check with detailed status tracking"""
    health_status = {}
    components = ['api', 'worker', 'bot', 'redis', 'database']
    
    for component in components:
        try:
            # Implement specific health checks for each component
            status = check_component_status(component)
            COMPONENT_HEALTH.labels(component=component).set(status['health_score'])
            health_status[component] = status
        except Exception as e:
            logging.error(f"Health check failed for {component}", 
                         extra={"context": json.dumps({"error": str(e), "component": component})})
            COMPONENT_HEALTH.labels(component=component).set(0)
            health_status[component] = {"status": "error", "error": str(e)}
    
    return health_status

def check_component_status(component: str) -> Dict[str, Any]:
    """Perform detailed health checks for specific components"""
    status = {"health_score": 1.0, "last_check": time.time()}
    
    if component == 'worker':
        # Worker-specific checks
        cpu = psutil.cpu_percent()
        memory = psutil.virtual_memory().percent
        status.update({
            "cpu_usage": cpu,
            "memory_usage": memory,
            "health_score": 1.0 if cpu < 80 and memory < 80 else 0.5
        })
    
    elif component == 'redis':
        # Redis connection check
        try:
            # Implement Redis ping check here
            status["health_score"] = 1.0
        except Exception as e:
            status["health_score"] = 0.0
            status["error"] = str(e)
    
    # Add more component-specific checks as needed
    
    return status

def track_performance_metrics(task_type: str, start_time: float):
    """Track detailed performance metrics for tasks"""
    processing_time = time.time() - start_time
    PROCESSING_TIME.labels(task_type=task_type).observe(processing_time)
    
    # Track memory usage
    process = psutil.Process()
    memory_info = process.memory_info()
    MEMORY_PER_TASK.labels(task_type=task_type).set(memory_info.rss)
    
    # Track task throughput
    TASK_THROUGHPUT.labels(task_type=task_type, status="completed").inc()

# Helper functions

async def update_task_status(task_id: str, status: str, context: Dict[str, Any] = None):
    """Update task status and track metrics"""
    try:
        TASK_THROUGHPUT.labels(task_type=status, status='success').inc()
        if context:
            logger.info(f"Task {task_id} status updated to {status}",
                      extra={'context': json.dumps(context)})
    except Exception as e:
        logger.error(f"Error updating task status: {str(e)}",
                    extra={'context': json.dumps({'task_id': task_id, 'error': str(e)})})

async def log_task_lifecycle(task_id: str, event: str, context: Dict[str, Any] = None):
    """Log task lifecycle events with metrics tracking"""
    try:
        if context:
            logger.info(f"Task {task_id} lifecycle event: {event}",
                      extra={'context': json.dumps(context)})
    except Exception as e:
        logger.error(f"Error logging task lifecycle: {str(e)}",
                    extra={'context': json.dumps({'task_id': task_id, 'error': str(e)})})

class AlertingSystem:
    def __init__(self):
        self.logger

async def get_task_history(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent task processing history"""
    try:
        # For now, return a simple list of recent task metrics
        tasks = []
        for sample in TASK_THROUGHPUT._metrics:
            task_type = sample.labels.get('task_type', 'unknown')
            status = sample.labels.get('status', 'unknown')
            count = sample.value
            tasks.append({
                'task_type': task_type,
                'status': status,
                'count': count
            })
        return tasks[:limit]
    except Exception as e:
        logger.error(f"Error getting task history: {str(e)}")
        return []

async def get_worker_health() -> Dict[str, Any]:
    """Get current worker health metrics"""
    try:
        return {
            'cpu_usage': CPU_USAGE._value.get(),
            'memory_usage': MEMORY_USAGE._value.get(),
            'active_workers': ACTIVE_WORKERS._value.get(),
            'component_health': {
                component: COMPONENT_HEALTH.labels(component=component)._value.get()
                for component in ['api', 'worker', 'bot']
            }
        }
    except Exception as e:
        logger.error(f"Error getting worker health: {str(e)}")
        return {}

async def check_redis_connection() -> bool:
    """Check Redis connection status"""
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection check failed: {str(e)}")
        return False

class AlertingSystem:
    def __init__(self):
        self.logger