import os
import json
import asyncio
import logging
from multiprocessing import Process
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from .monitoring import get_task_history, get_worker_health, check_redis_connection
from .queue import get_redis_client

# Configure logging
logger = logging.getLogger(__name__)

# Initialize FastAPI app with proper event loop handling
def create_app():
    app = FastAPI(title="WorthIt! Worker Dashboard")
    
    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Serve static files
    app.mount("/static", StaticFiles(directory="worker/static"), name="static")
    return app

app = create_app()

@app.on_event("startup")
async def startup_event():
    # Ensure we have a clean event loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Set up proper exception handling
    loop.set_exception_handler(lambda loop, context: logger.error(f"Event loop error: {context}"))

@app.get("/health", tags=["Monitoring"])
async def health_check():
    return await get_worker_health()

@app.get("/tasks/{task_id}", tags=["Tasks"])
async def get_task_details(task_id: str):
    return await get_task_history(task_id)

@app.get("/dashboard", response_class=HTMLResponse, tags=["Monitoring"])
async def metrics_dashboard():
    return """
    <html>
        <head>
            <title>Worker Dashboard</title>
            <link rel="stylesheet" href="/static/dashboard.css">
            <script src="/static/dashboard.js"></script>
        </head>
        <body>
            <h1>Real-time Worker Metrics</h1>
            <div class="metrics-grid">
                <div class="metric-card" id="queue-stats">
                    <h2>Task Queue</h2>
                    <div class="metric-value" id="pending-tasks">-</div>
                    <div class="metric-label">Pending Tasks</div>
                </div>
                <div class="metric-card" id="active-tasks">
                    <h2>Active Processing</h2>
                    <div class="metric-value">-</div>
                    <div class="metric-label">Current Tasks</div>
                </div>
                <div class="metric-card" id="redis-health">
                    <h2>Redis Status</h2>
                    <div class="metric-value">-</div>
                    <div class="metric-label">Connection</div>
                </div>
            </div>
            <div id="task-stream"></div>
        </body>
    </html>
    """

@app.get("/metrics", tags=["Monitoring"])
async def get_system_metrics():
    try:
        redis_client = await get_redis_client()
        if not redis_client:
            return {"error": "Redis connection not available", "status": 500}
            
        return {
            "queue_length": await redis_client.llen("worthit_tasks"),
            "active_tasks": len([key async for key in redis_client.scan_iter("task:*") 
                                if await redis_client.hget(key, "status") == "processing"]),
            "redis_connected": await check_redis_connection(),
            "workers_online": int(await redis_client.get("workers:online") or 0)
        }
    except Exception as e:
        logger.error(f"Error getting system metrics: {str(e)}")
        return {"error": "Internal server error", "status": 500}

@app.get("/updates")
async def sse_updates():
    return EventSourceResponse(event_generator())

async def event_generator():
    redis_client = await get_redis_client()
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("task_updates")
    
    async def get_system_metrics():
        return {
            "queue_length": await redis_client.llen("worthit_tasks"),
            "active_tasks": len([key async for key in redis_client.scan_iter("task:*") 
                                if await redis_client.hget(key, "status") == "processing"]),
            "redis_connected": await check_redis_connection()
        }

    while True:
        # Send metrics every 2 seconds
        metrics = await get_system_metrics()
        yield {"event": "metrics", "data": json.dumps(metrics)}
        
        # Process real-time updates
        message = await pubsub.get_message(ignore_subscribe_messages=True)
        if message:
            yield {"event": "task_update", "data": message["data"]}
        
        await asyncio.sleep(2)

@app.on_event("startup")
async def startup_event():
    try:
        # Initialize Redis connection
        redis_client = await get_redis_client()
        if not redis_client:
            logger.error("Failed to initialize Redis connection")
        else:
            logger.info("Successfully connected to Redis")
    except Exception as e:
        logger.error(f"Startup error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("DASHBOARD_PORT", 8000)))