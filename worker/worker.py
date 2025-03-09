import asyncio
import os
import logging
import logging.handlers  # Explicitly import logging.handlers
import time
import json
from datetime import datetime
from redis.asyncio import Redis
from telegram import Bot, Update
from dotenv import load_dotenv
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
import httpx

# Import the queue interface and redis manager
from worker.queue import get_task_queue, enqueue_task, dequeue_task
from worker.redis_manager import get_redis_manager, get_redis_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(
            'logs/worker.log',
            maxBytes=10485760,
            backupCount=5,
            encoding='utf-8'
        ),
        logging.StreamHandler(),
        logging.handlers.SocketHandler('localhost', 9020)
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

async def notify_completion(task_id: str, result: Dict[str, Any]) -> bool:
    """Notify task completion"""
    try:
        # Convert result to string if it's not already
        if isinstance(result, dict):
            result = json.dumps(result)
        
        # Send notification
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{os.getenv('API_BASE_URL')}/notify",
                json={"task_id": task_id, "result": result}
            )
            
            if response.status_code == 200:
                logger.info(f"Successfully notified completion of task {task_id}")
                return True
            else:
                logger.error(f"Failed to notify completion of task {task_id}: {response.text}")
                return False
    except Exception as e:
        logger.error(f"Error notifying completion of task {task_id}: {str(e)}")
        return False

async def get_redis_client() -> Redis:
    """Get a Redis client instance"""
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _redis_client = await Redis.from_url(redis_url)
    return _redis_client

# Global Redis client
_redis_client = None

class TaskWorker:
    """Worker class for processing tasks from the queue"""
    
    def __init__(self):
        self.is_running = False
        self.current_task = None
        self.task_queue = None
        self.redis_client = None
    
    async def initialize(self):
        """Initialize the worker"""
        try:
            # Get Redis client
            self.redis_client = await get_redis_client()
            
            # Get task queue
            self.task_queue = await get_task_queue()
            
            logger.info("Worker initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize worker: {str(e)}")
            return False
    
    async def start(self):
        """Start the worker"""
        if not self.redis_client:
            await self.initialize()
        
        self.is_running = True
        logger.info("Worker started")
        
        while self.is_running:
            try:
                # Dequeue a task
                task = await dequeue_task()
                
                if task:
                    # Process the task
                    result = await self.process_task(task)
                    
                    # Update task status
                    await self.update_task_status(task['id'], result)
                    
                    # Notify completion
                    await notify_completion(task['id'], result)
            except Exception as e:
                logger.error(f"Error processing task: {str(e)}")
            
            # Sleep briefly to prevent CPU spinning
            await asyncio.sleep(0.1)
    
    async def update_task_status(self, task_id: str, result: Dict[str, Any]) -> bool:
        """Update task status in Redis"""
        try:
            # Get the task from Redis
            task_key = f"task:{task_id}"
            task_data = await self.redis_client.get(task_key)
            
            if not task_data:
                logger.error(f"Task {task_id} not found in Redis")
                return False
            
            # Parse the task data
            task = json.loads(task_data)
            
            # Update the task status
            task.update(result)
            
            # Save the updated task back to Redis
            await self.redis_client.set(task_key, json.dumps(task))
            
            logger.info(f"Updated status of task {task_id} to {result.get('status', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"Error updating task status: {str(e)}")
            return False
    
    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Process a task"""
        try:
            task_type = task.get('type')
            task_data = task.get('data', {})
            
            logger.info(f"Processing task {task['id']} of type {task_type}")
            
            # Import task-specific modules only when needed
            if task_type == 'product_analysis':
                from api.scraper import scrape_product
                from api.ml_processor import analyze_sentiment, extract_product_pros_cons, get_value_score
                
                # Scrape product data
                product_data = await scrape_product(task_data.get('url'))
                
                # Analyze sentiment
                sentiment = await analyze_sentiment(product_data.get('reviews', []))
                
                # Extract pros and cons
                pros, cons = await extract_product_pros_cons(product_data.get('reviews', []))
                
                # Calculate value score
                value_score = await get_value_score(product_data, sentiment)
                
                # Generate recommendation
                recommendation = get_recommendation(value_score)
                
                return {
                    'status': 'completed',
                    'product': product_data,
                    'sentiment': sentiment,
                    'pros': pros,
                    'cons': cons,
                    'value_score': value_score,
                    'recommendation': recommendation
                }
            else:
                logger.error(f"Unknown task type: {task_type}")
                return {
                    'status': 'failed',
                    'error': f"Unknown task type: {task_type}"
                }
        except Exception as e:
            logger.error(f"Error processing task {task.get('id')}: {str(e)}")
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    async def run(self):
        """Run the worker"""
        if not await self.initialize():
            logger.error("Failed to initialize worker")
            return
        
        await self.start()
# Helper function for recommendation text
def get_recommendation(value_score: float) -> str:
    """Get recommendation text based on value score"""
    if value_score >= 8.0:
        return "Ottimo acquisto! Questo prodotto offre un eccellente rapporto qualità/prezzo."
    elif value_score >= 6.0:
        return "Buon acquisto. Il prodotto vale il suo prezzo."
    elif value_score >= 4.0:
        return "Acquisto nella media. Valuta se ci sono alternative migliori."
    else:
        return "Non consigliato. Il prodotto non vale il prezzo richiesto."

async def process_task_legacy(task: Dict[str, Any], bot: Bot) -> None:
    """Legacy process task function for backward compatibility"""
    worker = TaskWorker()
    await worker.process_task(task)

async def main() -> None:
    """Main entry point for the worker"""
    worker = TaskWorker()
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())