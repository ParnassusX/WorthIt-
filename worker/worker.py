import asyncio
import os
import logging
import time
import json
from redis.asyncio import Redis
from telegram import Bot, Update
from dotenv import load_dotenv
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
import httpx

# Import the queue interface
from worker.queue import get_redis_client, get_task_queue, enqueue_task, dequeue_task

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Redis connection pool
_redis_client = None

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
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Error notifying completion: {e}")
        return False

async def get_http_client():
    """Get an HTTP client for API calls"""
    return httpx.AsyncClient(timeout=30.0)

class TaskWorker:
    """Worker class for processing tasks from the queue"""
    
    def __init__(self):
        """Initialize the worker"""
        self.telegram_token = os.getenv("TELEGRAM_TOKEN")
        if not self.telegram_token:
            logger.warning("TELEGRAM_TOKEN environment variable is not set")
    
    async def process_telegram_update(update_data: Dict[str, Any]) -> None:
        """Process a Telegram update from the queue"""
        try:
            # Create a new bot instance
            bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
            
            # Parse the update
            update = Update.de_json(update_data, bot)
            
            # Ensure we have a valid event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Import the process_telegram_update function from webhook_handler
            from bot.webhook_handler import process_telegram_update as process_update
            
            # Process the update
            await process_update(update)
            
        except Exception as e:
            logger.error(f"Error processing Telegram update: {e}")
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single task from the queue with retry logic and error handling"""
        try:
            task_id = task.get('id', str(uuid.uuid4()))
            logger.info(f"Processing task {task_id}: {task.get('task_type', 'unknown')}")
            
            # Update task status to processing
            await self.update_task_status(task_id, "processing")
            
            # Handle different task types
            if task.get('task_type') == 'telegram_update':
                # Process Telegram update with error recovery
                try:
                    await process_telegram_update(task.get('update_data', {}))
                    await self.update_task_status(task_id, "completed")
                    return {"status": "completed", "task_id": task_id}
                except Exception as e:
                    logger.error(f"Error processing Telegram update: {e}")
                    await self.update_task_status(task_id, "failed", {"error": str(e)})
                    raise
                
            elif task.get('task_type') == 'product_analysis':
                # Import here to avoid circular imports
                from api.scraper import scrape_product
                from api.ml_processor import analyze_reviews
                
                try:
                    # Step 1: Scrape product data
                    product_data = await scrape_product(task['url'])
                    
                    # Step 2: Process reviews with ML
                    # Import here to avoid circular imports
                    from api.ml_processor import analyze_sentiment, extract_product_pros_cons, get_value_score
                    
                    # Analyze sentiment of reviews
                    sentiment_result = await analyze_sentiment(product_data.get('reviews', []))
                    
                    # Extract pros and cons
                    pros, cons = await extract_product_pros_cons(product_data.get('reviews', []), product_data)
                    
                    # Calculate value score
                    value_score = await get_value_score(product_data, {'average_sentiment': sentiment_result.get('score', 0.5)})
                    
                    # Compile results
                    analysis_result = {
                        'pros': pros,
                        'cons': cons,
                        'sentiment_score': sentiment_result.get('score', 0.5),
                        'value_score': value_score,
                        'recommendation': get_recommendation(value_score)
                    }
                    
                    # Step 3: Compile final results
                    result = {
                        'title': product_data['title'],
                        'price': product_data['price'],
                        'value_score': value_score,
                        'url': task['url'],
                        'pros': pros,
                        'cons': cons,
                        'recommendation': get_recommendation(value_score)
                    }
                    
                    # Store result in Redis
                    redis_client = await get_redis_client()
                    await redis_client.set(f"task:{task.get('id', 'unknown')}", json.dumps(result))
                    
                    # Notify user if chat_id is provided
                    if task.get('chat_id'):
                        try:
                            bot = Bot(token=self.telegram_token)
                            message = f"*{result['title']}*\n\n"
                            message += f"💰 Prezzo: {result['price']}\n"
                            message += f"⭐ Punteggio WorthIt: {result['value_score']}/10\n\n"
                            
                            if pros:
                                message += "✅ *Punti di forza:*\n"
                                for pro in pros[:3]:
                                    message += f"• {pro}\n"
                                message += "\n"
                            
                            if cons:
                                message += "❌ *Punti deboli:*\n"
                                for con in cons[:3]:
                                    message += f"• {con}\n"
                            
                            await bot.send_message(
                                chat_id=task['chat_id'],
                                text=message,
                                parse_mode="Markdown"
                            )
                        except Exception as notify_error:
                            logger.error(f"Error notifying user: {notify_error}")
                    
                    return {"status": "completed", "result": result}
                    
                except Exception as analysis_error:
                    logger.error(f"Analysis error: {analysis_error}")
                    
                    # Notify user of error if chat_id is provided
                    if task.get('chat_id'):
                        try:
                            bot = Bot(token=self.telegram_token)
                            await bot.send_message(
                                chat_id=task['chat_id'],
                                text=f"Mi dispiace, non sono riuscito ad analizzare questo prodotto. Errore: {str(analysis_error)}"
                            )
                        except Exception as notify_error:
                            logger.error(f"Error notifying user of error: {notify_error}")
                    
                    return {"status": "error", "error_message": str(analysis_error)}
            
            else:
                logger.warning(f"Unknown task type: {task.get('task_type', 'unknown')}")
                return {"status": "error", "error_message": f"Unknown task type: {task.get('task_type', 'unknown')}"}
                
        except Exception as e:
            logger.error(f"Error processing task: {e}")
            return {"status": "error", "error_message": str(e)}
    
    async def notify_completion(self, task_id: str, result: Dict[str, Any]) -> bool:
        """Notify the user that their task is complete"""
        try:
            # Get the task data from Redis
            redis_client = await get_redis_client()
            task_data = await redis_client.get(f"task:{task_id}")
            
            if not task_data:
                logger.error(f"Task data not found for task_id: {task_id}")
                return False
            
            # Handle both string and bytes responses from Redis
            if isinstance(task_data, bytes):
                task_info = json.loads(task_data.decode('utf-8'))
            else:
                task_info = json.loads(task_data)
            
            # If there's a chat_id, send a notification
            if 'chat_id' in task_info:
                bot = Bot(token=self.telegram_token)
                await bot.send_message(
                    chat_id=task_info['chat_id'],
                    text=f"✅ Analisi completata per: {task_info.get('title', 'il tuo prodotto')}"
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Error notifying completion: {e}")
            return False
    
    async def run(self):
        """Main worker loop that processes tasks from the queue"""
        logger.info("Worker started, waiting for tasks...")
        
        while True:
            try:
                # Get a task from the queue (blocking operation)
                task = await dequeue_task()
                if task:
                    logger.info(f"Received task: {task['type']}")
                    
                    # Process the task
                    result = await self.process_task(task)
                    
                    # Notify completion
                    if result.get('status') == 'completed':
                        await self.notify_completion(task['id'], result)
                
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                # Brief pause to prevent tight loop in case of persistent errors
                await asyncio.sleep(1)

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