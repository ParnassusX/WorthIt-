import json
import os
import asyncio
import logging
import uuid
from typing import Dict, Any, Optional
from redis.asyncio import Redis
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

logger = logging.getLogger(__name__)

# Redis connection pool
_redis_client = None

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def get_redis_client():
    """Get a Redis client instance with retry logic and connection pooling."""
    global _redis_client
    if _redis_client is None or not await check_redis_connection(_redis_client):
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        # Use SSL for Upstash Redis
        if "upstash" in redis_url and not redis_url.startswith("rediss://"):
            redis_url = redis_url.replace("redis://", "rediss://")
        
        try:
            # Enhanced SSL configuration for Upstash Redis
            ssl_enabled = "upstash" in redis_url
            ssl_config = {
                "ssl_cert_reqs": None,
                "ssl_check_hostname": False,
                "retry_on_timeout": True,
                "max_connections": 20,  # Increased pool size
                "max_idle_time": 300,  # 5 minutes idle timeout
                "retry_on_error": [TimeoutError, ConnectionError],
                "health_check_interval": 30  # More frequent health checks
            } if ssl_enabled else {
                "retry_on_timeout": True,
                "max_connections": 20,
                "max_idle_time": 300
            }
            
            _redis_client = await Redis.from_url(
                redis_url,
                decode_responses=False,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
                socket_keepalive=True,
                **ssl_config
            )
            # Verify connection
            if not await check_redis_connection(_redis_client):
                raise ConnectionError("Failed to establish Redis connection")
            
            logger.info("Successfully established Redis connection")
            return _redis_client
            
        except Exception as e:
            logger.error(f"Redis connection error: {e}")
            _redis_client = None
            raise
    return _redis_client

async def check_redis_connection(client: Redis) -> bool:
    """Check if Redis connection is alive and healthy."""
    try:
        if client is None:
            return False
        await client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection check failed: {e}")
        return False

class TaskQueue:
    def __init__(self):
        self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.queue_name = 'worthit_tasks'
        self.redis = None
        self.max_retries = 3  # Limit retries for free tier
        self.retry_delay = 2  # Initial delay in seconds
    
    async def connect(self):
        """Connect to Redis asynchronously"""
        if self.redis is None:
            try:
                # Use SSL for Upstash Redis
                if "upstash" in self.redis_url and not self.redis_url.startswith("rediss://"):
                    self.redis_url = self.redis_url.replace("redis://", "rediss://")
                
                # Set SSL configuration for Upstash Redis
                ssl_enabled = "upstash" in self.redis_url
                ssl_config = {
                    "ssl_cert_reqs": None,  # Don't verify SSL certificate
                    "ssl_check_hostname": False,  # Don't verify hostname
                    "retry_on_timeout": True,
                    "max_connections": 10
                } if ssl_enabled else {}
                
                self.redis = await Redis.from_url(
                    self.redis_url,
                    decode_responses=False,
                    socket_timeout=5.0,
                    socket_connect_timeout=5.0,
                    socket_keepalive=True,
                    health_check_interval=60,
                    # Remove retry_on_timeout as it's already in ssl_config when needed
                    **ssl_config
                )
                # Test the connection
                await self.redis.ping()
                logger.info("Successfully connected to Redis")
            except Exception as e:
                logger.error(f"Redis connection error: {e}")
                self.redis = None
                raise
        return self.redis
    
    def __del__(self):
        """Cleanup connections when object is destroyed"""
        if hasattr(self, 'redis') and self.redis:
            try:
                asyncio.create_task(self.redis.close())
            except:
                pass
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def enqueue(self, task: Dict[str, Any]) -> bool:
        """Add a task to the queue with retry logic"""
        try:
            if not self.redis:
                await self.connect()
            return await self.redis.lpush(self.queue_name, json.dumps(task))
        except Exception as e:
            logger.error(f"Redis enqueue error: {e}", exc_info=True)
            await self.connect()  # Force reconnect on error
            raise
    
    async def dequeue(self) -> Dict[str, Any]:
        """Get a task from the queue, blocking if empty"""
        try:
            result = await self.redis.brpop(self.queue_name, timeout=1)
            if result:
                _, task_json = result
                return json.loads(task_json)
            return None
        except Exception as e:
            logger.error(f"Redis error during dequeue: {e}")
            await self.connect()
            result = await self.redis.brpop(self.queue_name, timeout=1)
            if result:
                _, task_json = result
                return json.loads(task_json)
            return None
    
    async def get_queue_length(self) -> int:
        """Get the current length of the queue"""
        try:
            return await self.redis.llen(self.queue_name)
        except Exception as e:
            logger.error(f"Redis error during get_queue_length: {e}")
            await self.connect()
            return await self.redis.llen(self.queue_name)
    
    async def clear_queue(self) -> bool:
        """Clear all tasks from the queue"""
        try:
            return await self.redis.delete(self.queue_name)
        except Exception as e:
            logger.error(f"Redis error during clear_queue: {e}")
            await self.connect()
            return await self.redis.delete(self.queue_name)

# Global task queue instance
_task_queue = None

def get_task_queue() -> TaskQueue:
    """Get the global task queue instance"""
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue

async def enqueue_task(task):
    """Enqueue a task to Redis."""
    redis_client = await get_redis_client()
    # Generate a unique task ID if not provided
    task_id = task.get('id') or str(uuid.uuid4())
    task['id'] = task_id
    
    # Store task details in a hash
    task_key = f"task:{task_id}"
    await redis_client.hset(task_key, mapping={
        'status': task.get('status', 'pending'),
        'data': json.dumps(task),
        'created_at': asyncio.get_event_loop().time()
    })
    
    # Add task to queue
    await redis_client.lpush('worthit_tasks', json.dumps(task))
    return task_id

async def dequeue_task():
    """Dequeue a task from Redis."""
    redis_client = await get_redis_client()
    result = await redis_client.brpop('worthit_tasks', timeout=1)
    if result:
        _, task_json = result
        return json.loads(task_json)
    return None

async def get_task_by_id(task_id: str) -> Optional[Dict[str, Any]]:
    """Get task details by task ID."""
    try:
        redis_client = await get_redis_client()
        task_key = f"task:{task_id}"
        
        # Get task details from hash
        task_data = await redis_client.hgetall(task_key)
        if not task_data:
            return None
        
        # Parse the stored JSON data
        task_info = json.loads(task_data['data'])
        task_info['status'] = task_data['status']
        task_info['created_at'] = float(task_data['created_at'])
        
        return task_info
    except Exception as e:
        logger.error(f"Error getting task {task_id}: {e}")
        return None

async def update_task_status(task_id: str, status: str, result: Optional[Dict[str, Any]] = None) -> bool:
    """Update task status and optionally store results."""
    try:
        redis_client = await get_redis_client()
        task_key = f"task:{task_id}"
        
        # Get existing task data
        task_data = await redis_client.hgetall(task_key)
        if not task_data:
            return False
        
        # Update task data
        task_info = json.loads(task_data['data'])
        task_info['status'] = status
        if result:
            task_info['result'] = result
        
        # Store updated task data
        await redis_client.hset(task_key, mapping={
            'status': status,
            'data': json.dumps(task_info),
            'updated_at': asyncio.get_event_loop().time()
        })
        
        return True
    except Exception as e:
        logger.error(f"Error updating task {task_id}: {e}")
        return False