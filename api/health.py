from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import psutil
import json
from datetime import datetime

router = APIRouter()

async def check_component_health(component: str) -> bool:
    """Check health of a specific system component"""
    # Placeholder implementation - always return True for now
    return True

async def get_queue_size() -> int:
    """Get current queue size"""
    return 0  # Placeholder implementation

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Enhanced health check endpoint with detailed system status"""
    # No need to update system metrics here as we'll get them directly
    
    # Check component health
    components_status = {
        'database': await check_component_health('database'),
        'cache': await check_component_health('cache'),
        'ml_service': await check_component_health('ml_service')
    }
    
    # Get system resources
    memory = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=0.1)  # Reduced interval to speed up tests
    
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