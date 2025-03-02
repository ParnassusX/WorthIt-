import redis
import json
import os
import asyncio
import logging
from typing import Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

logger = logging.getLogger(__name__)

class TaskQueue:
    def __init__(self):
        self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.queue_name = 'worthit_tasks'
        self.redis = None
        self.pool = None
        self.connect_with_retry()
    
    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=10))
    def connect_with_retry(self):
        try:
            # Create a connection pool
            self.pool = redis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=10,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
                retry_on_timeout=True
            )
            # Create Redis client with the connection pool
            self.redis = redis.Redis(connection_pool=self.pool)
            # Test the connection
            self.redis.ping()
            logger.info("Successfully connected to Redis")
        except redis.ConnectionError as e:
            logger.error(f"Redis connection error: {e}")
            raise
        except redis.TimeoutError as e:
            logger.error(f"Redis timeout error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected Redis error: {e}")
            raise
    
    async def enqueue(self, task: Dict[str, Any]) -> bool:
        """Add a task to the queue"""
        return self.redis.lpush(self.queue_name, json.dumps(task))
    
    async def dequeue(self) -> Dict[str, Any]:
        """Get a task from the queue, blocking if empty"""
        _, task_json = self.redis.brpop(self.queue_name)
        return json.loads(task_json)
    
    async def get_queue_length(self) -> int:
        """Get the current length of the queue"""
        return self.redis.llen(self.queue_name)
    
    async def clear_queue(self) -> bool:
        """Clear all tasks from the queue"""
        return self.redis.delete(self.queue_name)

# Helper function to get a singleton queue instance
_queue_instance = None

def get_task_queue() -> TaskQueue:
    """Get a singleton instance of the TaskQueue"""
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = TaskQueue()
    return _queue_instance

# Utility functions for enqueueing tasks from the webhook handler
async def enqueue_task(task: Dict[str, Any]) -> bool:
    """Enqueue a task to be processed by the background worker"""
    queue = get_task_queue()
    return await queue.enqueue(task)