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

async def get_redis_client():
    """Get a Redis client instance."""
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        # Use SSL for Upstash Redis
        if "upstash" in redis_url and not redis_url.startswith("rediss://"):
            redis_url = redis_url.replace("redis://", "rediss://")
        
        try:
            # Set SSL configuration for Upstash Redis
            ssl_enabled = "upstash" in redis_url
            ssl_config = {
                "ssl": ssl_enabled,
                "ssl_cert_reqs": None,  # Don't verify SSL certificate
                "ssl_check_hostname": False  # Don't verify hostname
            } if ssl_enabled else {}
            
            _redis_client = await Redis.from_url(
                redis_url,
                decode_responses=False,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
                socket_keepalive=True,
                health_check_interval=60,
                retry_on_timeout=True,
                **ssl_config
            )
            # Test the connection
            await _redis_client.ping()
            return _redis_client
        except Exception as e:
            logger.error(f"Redis connection error: {e}")
            _redis_client = None
            raise
    return _redis_client

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
                    "ssl": ssl_enabled,
                    "ssl_cert_reqs": None,  # Don't verify SSL certificate
                    "ssl_check_hostname": False  # Don't verify hostname
                } if ssl_enabled else {}
                
                self.redis = await Redis.from_url(
                    self.redis_url,
                    decode_responses=False,
                    socket_timeout=5.0,
                    socket_connect_timeout=5.0,
                    socket_keepalive=True,
                    health_check_interval=60,
                    retry_on_timeout=True,
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
    
    async def enqueue(self, task: Dict[str, Any]) -> bool:
        """Add a task to the queue"""
        try:
            return await self.redis.lpush(self.queue_name, json.dumps(task))
        except Exception as e:
            logger.error(f"Redis error during enqueue: {e}")
            await self.connect()
            return await self.redis.lpush(self.queue_name, json.dumps(task))
    
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
    await redis_client.lpush('tasks', json.dumps(task))
    return task_id

async def dequeue_task():
    """Dequeue a task from Redis."""
    redis_client = await get_redis_client()
    result = await redis_client.brpop('tasks', timeout=1)
    if result:
        _, task_json = result
        return json.loads(task_json)
    return None