import asyncio
import json
import logging
from typing import Optional
from .queue import get_redis_client, get_task_by_id
from .tasks import process_task

logger = logging.getLogger(__name__)

async def process_queue():
    """Main worker loop to process tasks from the Redis queue."""
    while True:
        try:
            redis_client = await get_redis_client()
            if not redis_client:
                logger.error("Failed to get Redis client")
                await asyncio.sleep(5)
                continue

            # Get next task from the queue
            task_data = await redis_client.blpop('task_queue', timeout=5)
            if not task_data:
                continue

            # Parse task data
            _, task_json = task_data
            task = json.loads(task_json)
            task_id = task.get('id')

            if not task_id:
                logger.error("Received task without ID")
                continue

            # Process the task
            try:
                await process_task(task_id, task)
            except Exception as e:
                logger.error(f"Error processing task {task_id}: {e}")
                # Update task status
                task['status'] = 'failed'
                task['error'] = str(e)
                await redis_client.set(f"task:{task_id}", json.dumps(task))

        except Exception as e:
            logger.error(f"Error in worker loop: {e}")
            await asyncio.sleep(5)

def run_worker():
    """Start the worker process."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(process_queue())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker crashed: {e}")
    finally:
        loop.close()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_worker()