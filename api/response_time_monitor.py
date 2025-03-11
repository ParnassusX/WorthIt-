import logging
import time
from typing import Dict, List, Optional, Callable
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio
import json
from prometheus_client import Histogram, Gauge, Counter

logger = logging.getLogger(__name__)

# Prometheus metrics for API response time monitoring
API_RESPONSE_TIME = Histogram(
    'api_response_time_seconds',
    'API endpoint response time in seconds',
    ['endpoint', 'method', 'status_code']
)

API_REQUEST_RATE = Counter(
    'api_request_rate_total',
    'API request rate',
    ['endpoint', 'method']
)

API_ERROR_RATE = Counter(
    'api_error_rate_total',
    'API error rate',
    ['endpoint', 'method', 'status_code']
)

API_RESPONSE_SIZE = Histogram(
    'api_response_size_bytes',
    'API response size in bytes',
    ['endpoint', 'method']
)

API_CONCURRENT_REQUESTS = Gauge(
    'api_concurrent_requests',
    'Number of concurrent API requests',
    ['endpoint']
)

# Store historical response times for trend analysis
response_time_history: Dict[str, List[float]] = {}
# Track concurrent requests
concurrent_requests: Dict[str, int] = {}
# Alert thresholds
alert_thresholds = {
    'response_time': 2.0,  # seconds
    'error_rate': 0.05,    # 5%
    'concurrent_requests': 50
}

class ResponseTimeMonitorMiddleware(BaseHTTPMiddleware):
    """Middleware to monitor API response times and collect metrics."""
    
    def __init__(self, app: FastAPI, alert_callback: Optional[Callable] = None):
        super().__init__(app)
        self.alert_callback = alert_callback
    
    async def dispatch(self, request: Request, call_next):
        # Extract endpoint path for metrics
        endpoint = request.url.path
        method = request.method
        
        # Track concurrent requests
        if endpoint not in concurrent_requests:
            concurrent_requests[endpoint] = 0
        concurrent_requests[endpoint] += 1
        API_CONCURRENT_REQUESTS.labels(endpoint=endpoint).set(concurrent_requests[endpoint])
        
        # Check if we need to alert on high concurrent requests
        if concurrent_requests[endpoint] > alert_thresholds['concurrent_requests']:
            logger.warning(
                f"High number of concurrent requests for {endpoint}: {concurrent_requests[endpoint]}",
                extra={"context": json.dumps({"endpoint": endpoint, "concurrent_requests": concurrent_requests[endpoint]})}
            )
            if self.alert_callback:
                await self.alert_callback("high_concurrent_requests", {
                    "endpoint": endpoint,
                    "concurrent_requests": concurrent_requests[endpoint],
                    "threshold": alert_thresholds['concurrent_requests']
                })
        
        # Measure response time
        start_time = time.time()
        
        try:
            # Process the request
            response = await call_next(request)
            
            # Record metrics after processing
            process_time = time.time() - start_time
            status_code = response.status_code
            
            # Update Prometheus metrics
            API_RESPONSE_TIME.labels(
                endpoint=endpoint,
                method=method,
                status_code=status_code
            ).observe(process_time)
            
            API_REQUEST_RATE.labels(
                endpoint=endpoint,
                method=method
            ).inc()
            
            # Track errors (4xx and 5xx responses)
            if status_code >= 400:
                API_ERROR_RATE.labels(
                    endpoint=endpoint,
                    method=method,
                    status_code=status_code
                ).inc()
                
                # Log error details
                logger.warning(
                    f"API Error: {status_code} on {method} {endpoint} in {process_time:.2f}s",
                    extra={"context": json.dumps({
                        "endpoint": endpoint,
                        "method": method,
                        "status_code": status_code,
                        "response_time": process_time
                    })}
                )
            
            # Store in history for trend analysis
            if endpoint not in response_time_history:
                response_time_history[endpoint] = []
            
            # Keep last 100 response times for each endpoint
            response_time_history[endpoint].append(process_time)
            if len(response_time_history[endpoint]) > 100:
                response_time_history[endpoint].pop(0)
            
            # Alert on slow responses
            if process_time > alert_thresholds['response_time']:
                logger.warning(
                    f"Slow API response detected for {endpoint}: {process_time:.2f}s",
                    extra={"context": json.dumps({
                        "endpoint": endpoint,
                        "method": method,
                        "response_time": process_time,
                        "threshold": alert_thresholds['response_time']
                    })}
                )
                if self.alert_callback:
                    await self.alert_callback("slow_response", {
                        "endpoint": endpoint,
                        "method": method,
                        "response_time": process_time,
                        "threshold": alert_thresholds['response_time']
                    })
            
            return response
        finally:
            # Always decrement concurrent requests counter
            concurrent_requests[endpoint] -= 1
            API_CONCURRENT_REQUESTS.labels(endpoint=endpoint).set(concurrent_requests[endpoint])

async def alert_handler(alert_type: str, alert_data: Dict):
    """Handle alerts from the response time monitor.
    
    This function can be customized to send alerts via different channels
    such as email, Slack, or a monitoring dashboard.
    """
    if alert_type == "slow_response":
        logger.error(
            f"ALERT: Slow API response for {alert_data['endpoint']}: {alert_data['response_time']:.2f}s",
            extra={"context": json.dumps(alert_data)}
        )
    elif alert_type == "high_concurrent_requests":
        logger.error(
            f"ALERT: High concurrent requests for {alert_data['endpoint']}: {alert_data['concurrent_requests']}",
            extra={"context": json.dumps(alert_data)}
        )
    elif alert_type == "high_error_rate":
        logger.error(
            f"ALERT: High error rate for {alert_data['endpoint']}: {alert_data['error_rate']:.2%}",
            extra={"context": json.dumps(alert_data)}
        )
    
    # TODO: Implement external alerting mechanisms (email, Slack, etc.)
    # This would be implemented based on the organization's preferred alerting channels

def get_response_time_stats(endpoint: Optional[str] = None) -> Dict:
    """Get response time statistics for analysis.
    
    Args:
        endpoint: Optional endpoint to filter stats for
        
    Returns:
        Dictionary with response time statistics
    """
    if endpoint and endpoint in response_time_history:
        times = response_time_history[endpoint]
    elif endpoint:
        return {"error": f"No data for endpoint {endpoint}"}
    else:
        # Aggregate all endpoints
        times = []
        for endpoint_times in response_time_history.values():
            times.extend(endpoint_times)
    
    if not times:
        return {"error": "No response time data available"}
    
    # Calculate statistics
    avg_time = sum(times) / len(times)
    sorted_times = sorted(times)
    median_time = sorted_times[len(sorted_times) // 2]
    p95_time = sorted_times[int(len(sorted_times) * 0.95)]
    p99_time = sorted_times[int(len(sorted_times) * 0.99)]
    
    return {
        "count": len(times),
        "avg": avg_time,
        "median": median_time,
        "p95": p95_time,
        "p99": p99_time,
        "min": min(times),
        "max": max(times)
    }

def setup_response_time_monitoring(app: FastAPI):
    """Set up response time monitoring for a FastAPI application.
    
    Args:
        app: The FastAPI application to monitor
    """
    # Add the middleware to the application
    app.add_middleware(ResponseTimeMonitorMiddleware, alert_callback=alert_handler)
    
    # Add an endpoint to get response time statistics
    @app.get("/api/metrics/response-times", tags=["Monitoring"])
    async def get_response_times(endpoint: Optional[str] = None):
        return get_response_time_stats(endpoint)
    
    logger.info("Response time monitoring configured successfully")