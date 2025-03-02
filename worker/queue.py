import redis
import json
import os
import asyncio
from typing import Dict, Any

class TaskQueue:
    def __init__(self):
        self.redis = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379'))
        self.queue_name = 'worthit_tasks'
    
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