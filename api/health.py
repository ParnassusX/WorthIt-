from fastapi import APIRouter
from api.monitoring import check_component_health, update_system_metrics
import psutil
import json
from datetime import datetime

router = APIRouter()

@router.get("/health")
async def health_check():
    """Enhanced health check endpoint with detailed system status"""
    # Update system metrics
    update_system_metrics()
    
    # Check component health
    components_status = {
        'database': check_component_health('database'),
        'cache': check_component_health('cache'),
        'ml_service': check_component_health('ml_service')
    }
    
    # Get system resources
    memory = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=1)
    
    return {
        "status": "ok" if all(components_status.values()) else "degraded",
        "service": "WorthIt! API",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            name: "healthy" if status else "unhealthy"
            for name, status in components_status.items()
        },
        "system_health": {
            "memory_usage_percent": memory.percent,
            "cpu_usage_percent": cpu_percent,
            "memory_available_gb": round(memory.available / (1024 ** 3), 2)
        }
    }