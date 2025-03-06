import asyncio
import os
import logging
import time
import json
from datetime import datetime
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

class RedisConnectionManager:
    """Manages Redis connections with proper pooling, cleanup, and resource management."""
    _instance = None
    _lock = asyncio.Lock()
    _pool = None
    _last_health_check = None
    _health_check_interval = 300  # 5 minutes
    _active_connections = set()
    _cleanup_task = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cleanup_task = asyncio.create_task(cls._instance._periodic_cleanup())
        return cls._instance
    
    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=30))
    async def get_connection(self) -> Redis:
        """Get a Redis connection from the pool with automatic recovery and tracking."""
        async with self._lock:
            try:
                if self._pool is None or self._needs_health_check():
                    await self._initialize_pool()
                conn = await self._pool.get_connection()
                self._active_connections.add(conn)
                return conn
            except Exception as e:
                logger.error(
                    f"Redis connection error",
                    extra={"context": json.dumps({"error": str(e), "active_connections": len(self._active_connections)})}
                )
                self._pool = None
                raise
    
    async def release_connection(self, conn):
        """Release a connection back to the pool."""
        try:
            self._active_connections.remove(conn)
            await conn.close()
        except Exception as e:
            logger.error(
                f"Error releasing connection",
                extra={"context": json.dumps({"error": str(e)})}
            )
    
    async def _initialize_pool(self):
        """Initialize the Redis connection pool with proper configuration and monitoring."""
        try:
            redis_url = os.getenv('REDIS_URL')
            if not redis_url:
                raise ValueError("REDIS_URL environment variable not set")
            
            self._pool = await Redis.from_url(
                redis_url,
                encoding='utf-8',
                decode_responses=True,
                max_connections=10,
                socket_timeout=5.0,
                health_check_interval=30.0
            )
            
            logger.info(
                "Redis pool initialized",
                extra={"context": json.dumps({"max_connections": 10, "active_connections": len(self._active_connections)})}
            )
        except Exception as e:
            logger.error(
                "Failed to initialize Redis pool",
                extra={"context": json.dumps({"error": str(e)})}
            )
            raise

    async def _periodic_cleanup(self):
        """Periodically clean up stale connections."""
        while True:
            try:
                await asyncio.sleep(60)  # Run cleanup every minute
                async with self._lock:
                    stale_connections = [conn for conn in self._active_connections if not conn.is_connected()]
                    for conn in stale_connections:
                        await self.release_connection(conn)
                    
                    if stale_connections:
                        logger.info(
                            "Cleaned up stale connections",
                            extra={"context": json.dumps({"cleaned": len(stale_connections), "remaining": len(self._active_connections)})}
                        )
            except Exception as e:
                logger.error(
                    "Error in connection cleanup",
                    extra={"context": json.dumps({"error": str(e)})}
                )
    
    async def shutdown(self):
        """Gracefully shutdown the connection manager."""
        try:
            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
            
            async with self._lock:
                for conn in self._active_connections.copy():
                    await self.release_connection(conn)
                if self._pool:
                    await self._pool.close()
                    self._pool = None
            
            logger.info("Redis connection manager shutdown complete")
        except Exception as e:
            logger.error(
                "Error during shutdown",
                extra={"context": json.dumps({"error": str(e)})}
            )
    
    def _needs_health_check(self) -> bool:
        """Check if we need to verify the Redis connection."""
        return (
            self._last_health_check is None or
            time.time() - self._last_health_check > self._health_check_interval
        )
    
    async def cleanup(self):
        """Properly cleanup Redis connections."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            self._last_health_check = None

# Initialize Redis connection manager
_redis_manager = RedisConnectionManager()

class TaskWorker:
    def __init__(self):
        self.telegram_token = os.getenv("TELEGRAM_TOKEN")
        if not self.telegram_token:
            logger.warning("TELEGRAM_TOKEN environment variable is not set")
        self.redis = None
    
    async def verify_redis_connection(self):
        """Get and verify Redis connection using the connection manager."""
        try:
            self.redis = await _redis_manager.get_connection()
            return True
        except Exception as e:
            logger.error(f"Failed to verify Redis connection: {e}")
            return False
    
    async def cleanup(self):
        """Cleanup resources properly."""
        try:
            await _redis_manager.cleanup()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    def __init__(self):
        """Initialize the worker with proper connection management.
        
        Sets up:
        - Redis connection pooling
        - Telegram bot instance
        - Connection monitoring
        - Retry counters
        """
        self.telegram_token = os.getenv("TELEGRAM_TOKEN")
        self.last_connection_check = None
        self.connection_retries = 0
        if not self.telegram_token:
            logger.warning("TELEGRAM_TOKEN environment variable is not set")
    
    async def verify_redis_connection(self):
        """Verify and re-establish Redis connection if needed.
        
        Features:
        - Connection pooling with automatic recovery
        - Exponential backoff for retries
        - Health check monitoring
        - Graceful degradation
        """
        try:
            if self.redis is None or \
               (self.last_connection_check and \
                time.time() - self.last_connection_check > 300):
                
                logger.info("Verifying Redis connection pool...")
                # Get Redis client with connection pooling
                self.redis = await get_redis_client()
                
                # Test connection with timeout
                try:
                    await asyncio.wait_for(self.redis.ping(), timeout=5.0)
                    self.last_connection_check = time.time()
                    self.connection_retries = 0
                    logger.info("Redis connection pool verified")
                except asyncio.TimeoutError:
                    raise Exception("Redis connection timeout")
                
        except Exception as e:
            self.connection_retries += 1
            wait_time = min(2 ** self.connection_retries, 30)  # Exponential backoff capped at 30 seconds
            logger.error(f"Redis connection failed (attempt {self.connection_retries}): {e}. Retrying in {wait_time}s")
            
            if self.connection_retries > 5:
                logger.critical("Max Redis connection attempts reached. Initiating graceful shutdown...")
                # Allow current tasks to complete
                await self.cleanup_pending_tasks()
                os._exit(1)
                
            await asyncio.sleep(wait_time)

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
        logger.info(f"Processing task {task['id']} ({task['task_type']})")
        await self.verify_redis_connection()
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
            logger.error(f"Task {task.get('id', 'unknown')} failed: {str(e)}", exc_info=True)
            await self.verify_redis_connection()
            return {
                'status': 'failed',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat(),
                'retry_count': task.get('retry_count', 0) + 1
            }
    
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
        logger.info("Worker starting...")
        await self.verify_redis_connection()
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