import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from .monitoring import get_task_history, get_worker_health, check_redis_connection
from .queue import get_redis_client

app = FastAPI(title="WorthIt! Worker Dashboard")

# Serve static files
app.mount("/static", StaticFiles(directory="worker/static"), name="static")

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
    redis_client = await get_redis_client()
    return {
        "queue_length": await redis_client.llen("worthit_tasks"),
        "active_tasks": len([key async for key in redis_client.scan_iter("task:*") 
                            if await redis_client.hget(key, "status") == "processing"]),
        "redis_connected": await check_redis_connection(),
        "workers_online": int(await redis_client.get("workers:online") or 0)
    }

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
        yield {"event": "metrics", "data": JSON.stringify(metrics)}
        
        # Process real-time updates
        message = await pubsub.get_message(ignore_subscribe_messages=True)
        if message:
            yield {"event": "task_update", "data": message["data"]}
        
        await asyncio.sleep(2)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("DASHBOARD_PORT", 8000)))