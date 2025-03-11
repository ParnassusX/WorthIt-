from fastapi import FastAPI, Request, HTTPException, Depends
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from typing import Optional, Dict, Any, Callable
import httpx
import os
import re
import asyncio
import logging
import json
import time
from dotenv import load_dotenv
from .bot import start, handle_text, analyze_product_url, format_analysis_response, get_bot_instance
from .http_client import get_http_client, close_http_client
from worker.queue import enqueue_task

# PRODUCTION: Enhance logging configuration for production environment
# TODO: Configure structured logging with proper log levels
# TODO: Add log rotation and retention policies
# TODO: Implement centralized logging solution
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address

app = FastAPI()

# Production-ready rate limiting configuration
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# Configure rate limits based on endpoint sensitivity
@limiter.limit("60/minute")
async def limiter_webhook(request: Request):
    return get_remote_address(request)

# Configure CORS with restricted origins for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv('ALLOWED_ORIGIN', 'https://worthit-py.netlify.app')],
    allow_methods=['POST'],
    allow_headers=['Content-Type', 'X-Requested-With'],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"]
)

# Initialize bot instance
# PRODUCTION: Implement proper error handling for missing environment variables
# TODO: Add validation for environment variables at startup
# TODO: Implement graceful shutdown if critical variables are missing
bot_token = os.getenv('TELEGRAM_TOKEN')
if not bot_token:
    raise ValueError("TELEGRAM_TOKEN environment variable is not set")

_bot_instance = get_bot_instance(bot_token)

# PRODUCTION: Enhance error handling with proper monitoring integration
# TODO: Integrate with error tracking service (e.g., Sentry)
# TODO: Implement proper error categorization and prioritization
# TODO: Add recovery mechanisms for common error scenarios
async def error_handler(update: object, context) -> None:
    """Handle errors in the telegram bot with enhanced logging, monitoring, and recovery."""
    # Create structured error context for better debugging and monitoring
    error_context = {
        "error_type": context.error.__class__.__name__,
        "error_message": str(context.error),
        "timestamp": time.time(),
        "update_id": getattr(update, 'update_id', None),
        "chat_id": getattr(update.effective_chat, 'id', None) if hasattr(update, 'effective_chat') else None,
        "user_id": getattr(update.effective_user, 'id', None) if hasattr(update, 'effective_user') else None,
        "message_id": getattr(update.effective_message, 'message_id', None) if hasattr(update, 'effective_message') else None,
        "environment": os.getenv('NODE_ENV', 'development')
    }
    
    # Log error with structured context for better traceability
    logger.error(
        f"Exception while handling an update: {context.error}",
        extra={"error_context": error_context},
        exc_info=True
    )
    
    # Categorize errors for better handling
    if isinstance(context.error, (ConnectionError, httpx.HTTPError, httpx.ConnectError, httpx.ConnectTimeout)):
        logger.error(f"Network error detected: {context.error}")
        # Implement exponential backoff for network errors
        retry_count = getattr(context, 'retry_count', 0)
        if retry_count < 3:
            context.retry_count = retry_count + 1
            delay = 2 ** retry_count  # Exponential backoff: 1, 2, 4 seconds
            logger.info(f"Retrying after {delay} seconds (attempt {retry_count + 1}/3)")
            await asyncio.sleep(delay)
            # Attempt to retry the operation
            return
    
    # Special handling for event loop errors with enhanced recovery attempt
    if isinstance(context.error, RuntimeError) and "Event loop is closed" in str(context.error):
        logger.info("Detected event loop closure - attempting recovery")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # Add additional cleanup to ensure resources are properly managed
            # Reset any global state that might be affected
            await get_http_client(force_new=True)
            return
        except Exception as e:
            logger.error(f"Failed to recover event loop: {e}", exc_info=True)
    
    # Enhanced user communication with proper error tracking and localization
    if update and hasattr(update, 'effective_message') and update.effective_message:
        try:
            # Send user-friendly error message
            await update.effective_message.reply_text(
                "Mi dispiace, si è verificato un errore durante l'elaborazione della richiesta. "
                "Il team è stato notificato e risolverà il problema al più presto."
            )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}", exc_info=True)
    
    # Notify monitoring system with structured error data
    try:
        # In production, this would send to a monitoring service like Sentry
        # For now, we'll just log it with a special tag for monitoring
        logger.critical(
            f"MONITORING_ALERT: Bot error occurred: {context.error}",
            extra={"error_context": error_context}
        )
        
        # Implement proper error monitoring notification
        await notify_error_monitoring(error_context)
    except Exception as e:
        logger.error(f"Failed to notify monitoring system: {e}", exc_info=True)

async def notify_error_monitoring(error_context):
    """Send error information to monitoring service.
    
    In production, this would integrate with a service like Sentry, Datadog, or similar.
    For now, we implement a basic structured logging approach that can be easily parsed
    by log aggregation tools.
    
    Args:
        error_context: Dictionary containing error details and context
    """
    try:
        # Format error for monitoring
        monitoring_data = {
            "severity": "error",
            "source": "telegram_bot",
            "timestamp": time.time(),
            "error_type": error_context.get("error_type", "Unknown"),
            "error_message": error_context.get("error_message", "No message"),
            "user_id": error_context.get("user_id"),
            "chat_id": error_context.get("chat_id"),
            "environment": os.getenv("NODE_ENV", "development"),
            "version": os.getenv("VERSION", "1.0.0")
        }
        
        # Log in a format that can be easily parsed by log aggregation tools
        logger.critical(f"MONITORING_DATA: {json.dumps(monitoring_data)}")
        
        # In production, this would be replaced with actual API calls to monitoring services
        # Example: await send_to_sentry(monitoring_data)
        # Example: await notify_slack(monitoring_data)
        
        # If we have a Redis connection, store recent errors for dashboard display
        try:
            from worker.redis.client import get_redis_client
            redis = await get_redis_client()
            if redis:
                # Store in a capped list of recent errors (max 100)
                await redis.lpush("recent_errors", json.dumps(monitoring_data))
                await redis.ltrim("recent_errors", 0, 99)
                # Increment error counter for metrics
                await redis.incr(f"error_count:{monitoring_data['error_type']}")
                # Set expiry on counter (24 hours)
                await redis.expire(f"error_count:{monitoring_data['error_type']}", 86400)
        except Exception as redis_error:
            logger.error(f"Failed to store error in Redis: {redis_error}")
            
    except Exception as e:
        logger.error(f"Error in notify_error_monitoring: {e}", exc_info=True)


# HTTP client functions are now imported from http_client.py

async def analyze_product(url: str, chat_id: int = None) -> Dict[str, Any]:
    """Call the WorthIt! API to analyze a product with enhanced error handling and monitoring.
    
    This function implements a robust approach to handling asynchronous product analysis:
    1. Event loop management with automatic recovery
    2. Task queuing for background processing
    3. Status monitoring with timeout
    4. Error handling with user feedback
    5. Metrics tracking for performance monitoring
    
    Args:
        url: The product URL to analyze
        chat_id: Optional Telegram chat ID for notifications
        
    Returns:
        Dict containing analysis results or task status
        
    Raises:
        HTTPException: If analysis fails
        CancelledError: If task is cancelled
    """
    api_host = os.getenv("API_HOST")
    if not api_host:
        logger.error("API_HOST environment variable not set")
        raise ValueError("API_HOST environment variable not set")
        
    api_url = f"{api_host}/analyze"
    start_time = time.time()
    metrics = {
        "url": url,
        "chat_id": chat_id,
        "start_time": start_time,
        "duration": None,
        "status": "pending",
        "error": None
    }
    
    try:
        # Get or create event loop with proper error handling
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            logger.info("Created new event loop for product analysis")
        
        # Set up enhanced task cancellation handling
        def exception_handler(loop, context):
            exception = context.get('exception')
            logger.error(
                f"Event loop error: {context}", 
                extra={"error_context": context},
                exc_info=exception
            )
        
        loop.set_exception_handler(exception_handler)
        
        # Create a task for background processing with enhanced metadata
        task = {
            'type': 'product_analysis',
            'data': {
                'url': url,
                'chat_id': chat_id
            },
            'status': 'pending',
            'created_at': time.time(),
            'priority': 'normal',
            'retry_count': 0,
            'max_retries': 3
        }
        
        # Add task to Redis queue with monitoring
        try:
            task_id = await enqueue_task(task)
            logger.info(f"Enqueued task {task_id} for URL {url}")
            metrics["task_id"] = task_id
        except Exception as e:
            logger.error(f"Failed to enqueue task: {str(e)}", exc_info=True)
            metrics["status"] = "failed"
            metrics["error"] = f"Queue error: {str(e)}"
            raise
        
        # Monitor task status with improved timeout handling
        from worker.queue import get_task_by_id
        status_check_count = 0
        max_checks = 5
        check_interval = 2  # seconds
        
        while status_check_count < max_checks:
            try:
                await asyncio.sleep(check_interval)
                task_status = await get_task_by_id(task_id)
                
                if task_status:
                    if task_status.get('status') != 'pending':
                        metrics["status"] = task_status.get('status')
                        metrics["duration"] = time.time() - start_time
                        logger.info(
                            f"Task {task_id} completed with status {task_status.get('status')} in {metrics['duration']:.2f}s"
                        )
                        return task_status
                    
                    # Update check interval based on queue position if available
                    if 'queue_position' in task_status and task_status['queue_position'] > 5:
                        check_interval = min(5, check_interval * 1.5)  # Increase interval for tasks far in queue
                else:
                    logger.warning(f"Task {task_id} not found in Redis")
                    
            except Exception as e:
                logger.error(f"Error checking task status: {str(e)}", exc_info=True)
                
            status_check_count += 1
        
        # Return initial response if background processing is taking longer
        metrics["status"] = "processing"
        metrics["duration"] = time.time() - start_time
        logger.info(f"Task {task_id} still processing after {metrics['duration']:.2f}s, returning interim status")
        
        return {
            'status': 'processing',
            'task_id': task_id,
            'message': 'Analysis in progress',
            'eta_seconds': 30,  # Estimated time remaining
            'queue_position': 1  # Default position if unknown
        }
        
    except asyncio.CancelledError:
        metrics["status"] = "cancelled"
        metrics["duration"] = time.time() - start_time
        metrics["error"] = "Task cancelled"
        logger.warning(f"Task cancelled for URL {url} after {metrics['duration']:.2f}s")
        raise
        
    except Exception as e:
        metrics["status"] = "error"
        metrics["duration"] = time.time() - start_time
        metrics["error"] = str(e)
        logger.error(
            f"Error analyzing product {url}: {e}", 
            extra={"metrics": metrics},
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # Log final metrics for monitoring
        if metrics["duration"] is None:
            metrics["duration"] = time.time() - start_time
        logger.info(f"Product analysis metrics: {metrics}")

async def format_analysis_response(data: Dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    """Format the analysis response for Telegram"""
    value_emoji = "🟢" if data["value_score"] >= 7 else "🟡" if data["value_score"] >= 5 else "🔴"
    
    message = f"*{data['title']}*\n\n"
    message += f"💰 Prezzo: {data['price']}\n"
    message += f"⭐ Valore: {value_emoji} {data['value_score']}/10\n\n"
    message += f"*Raccomandazione:* {data['recommendation']}\n\n"
    
    message += "*Punti di forza:*\n"
    for pro in data['pros'][:3]:
        message += f"✅ {pro}\n"
    
    message += "\n*Punti deboli:*\n"
    for con in data['cons'][:3]:
        message += f"❌ {con}\n"
    
    # Create inline keyboard for sharing and actions
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="🔄 Aggiorna analisi", callback_data=f"refresh_{data['url']}")],
        [InlineKeyboardButton(text="📊 Confronta prezzi", callback_data=f"compare_{data['url']}")],
        [InlineKeyboardButton(text="📱 Apri nel browser", url=data['url'])],
        [InlineKeyboardButton(text="📤 Condividi analisi", switch_inline_query=data['url'])]
    ])
    
    return message, keyboard

async def handle_callback_query(update: Update, context: Any):
    """Handle callback queries from inline keyboard buttons"""
    query = update.callback_query
    await query.answer()
    
    action, url = query.data.split('_', 1)
    
    if action == "refresh":
        try:
            data = await analyze_product(url)
            message, keyboard = await format_analysis_response(data)
            await query.edit_message_text(
                text=message,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        except Exception as e:
            await query.edit_message_text(
                text=f"❌ Errore nell'aggiornamento dell'analisi: {str(e)}",
                parse_mode="Markdown"
            )
    elif action == "compare":
        await query.edit_message_text(
            text="🔄 Ricerca prezzi in corso...",
            parse_mode="Markdown"
        )
        # Here you would implement price comparison logic
        # For now, we'll just show a placeholder message
        await query.edit_message_text(
            text="📊 Funzionalità di confronta prezzi in arrivo!\n\nStay tuned per gli aggiornamenti.",
            parse_mode="Markdown"
        )

def get_bot_instance() -> Bot:
    """Get or create a Bot instance (singleton pattern)"""
    global _bot_instance
    if _bot_instance is None:
        load_dotenv()
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_TOKEN environment variable is not set")
        _bot_instance = Bot(token)
    return _bot_instance

async def process_telegram_update(update: Update) -> None:
    """Process a Telegram update by enqueueing it as a task."""
    try:
        # Convert update to dict for queue storage
        update_dict = update.to_dict()
        
        # Create task for worker
        task = {
            'task_type': 'telegram_update',
            'update_data': update_dict,
            'status': 'pending'
        }
        
        # Enqueue the task
        await enqueue_task(task)
        
    except Exception as e:
        logger.error(f"Error processing Telegram update: {e}")
        raise

@app.post("/webhook")
@limiter.limit("60/minute")
async def webhook(request: Request, limiter_dependency=Depends(limiter_webhook)):
    """Handle incoming webhook requests from Telegram with enhanced error handling and monitoring."""
    request_id = str(time.time()) + "-" + str(hash(request))
    start_time = time.time()
    metrics = {
        "request_id": request_id,
        "start_time": start_time,
        "duration": None,
        "status": "pending",
        "error": None
    }
    
    try:
        # Validate content type
        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            logger.warning(f"Invalid content type: {content_type}", extra={"request_id": request_id})
            metrics["status"] = "error"
            metrics["error"] = "Invalid content type"
            return JSONResponse(
                status_code=415,
                content={"status": "error", "message": "Content type must be application/json"}
            )
        
        # Parse the update with size limit validation
        try:
            body = await request.body()
            if len(body) > 1024 * 1024:  # 1MB limit
                logger.warning(f"Request body too large: {len(body)} bytes", extra={"request_id": request_id})
                metrics["status"] = "error"
                metrics["error"] = "Request body too large"
                return JSONResponse(
                    status_code=413,
                    content={"status": "error", "message": "Request body too large"}
                )
                
            update_dict = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}", extra={"request_id": request_id})
            metrics["status"] = "error"
            metrics["error"] = f"Invalid JSON: {str(e)}"
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Invalid JSON payload"}
            )
        
        # Validate update structure
        if "update_id" not in update_dict:
            logger.warning("Invalid update structure", extra={"request_id": request_id})
            metrics["status"] = "error"
            metrics["error"] = "Invalid update structure"
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Invalid update structure"}
            )
        
        # Log incoming update with basic info
        chat_id = None
        if "message" in update_dict and "chat" in update_dict["message"]:
            chat_id = update_dict["message"]["chat"].get("id")
        elif "callback_query" in update_dict and "message" in update_dict["callback_query"]:
            chat_id = update_dict["callback_query"]["message"]["chat"].get("id")
            
        logger.info(
            f"Received update {update_dict['update_id']} from chat {chat_id}",
            extra={"request_id": request_id, "update_id": update_dict["update_id"], "chat_id": chat_id}
        )
        
        # Parse the update into a Telegram Update object
        update = Update.de_json(update_dict, _bot_instance)
        
        # Process the update through worker queue with retry logic
        retry_count = 0
        max_retries = 3
        while retry_count < max_retries:
            try:
                await process_telegram_update(update)
                break
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    raise
                logger.warning(
                    f"Retrying process_telegram_update (attempt {retry_count}/{max_retries}): {e}",
                    extra={"request_id": request_id},
                    exc_info=True
                )
                await asyncio.sleep(1 * retry_count)  # Increasing delay between retries
        
        # Record successful processing
        metrics["status"] = "success"
        metrics["duration"] = time.time() - start_time
        logger.info(
            f"Successfully processed update {update_dict['update_id']} in {metrics['duration']:.2f}s",
            extra={"metrics": metrics}
        )
        
        return JSONResponse(status_code=200, content={"status": "ok"})
        
    except Exception as e:
        # Record error metrics
        metrics["status"] = "error"
        metrics["duration"] = time.time() - start_time
        metrics["error"] = str(e)
        
        # Log detailed error information
        logger.error(
            f"Webhook error: {e}",
            extra={"metrics": metrics},
            exc_info=True
        )
        
        # Return appropriate error response
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Internal server error"}
        )

async def format_analysis_response(analysis_result: Dict[str, Any]) -> tuple[str, Optional[InlineKeyboardMarkup]]:
    """Format the analysis result into a message with optional keyboard markup."""
    message = f"*{analysis_result.get('title', 'Prodotto')}*\n\n"
    message += f"💰 Prezzo: {analysis_result.get('price', 'N/A')}\n"
    message += f"⭐ Punteggio WorthIt: {analysis_result.get('value_score', 0)}/10\n\n"
    
    pros = analysis_result.get('pros', [])
    cons = analysis_result.get('cons', [])
    
    if pros:
        message += "✅ *Punti di forza:*\n"
        for pro in pros[:3]:
            message += f"• {pro}\n"
        message += "\n"
    
    if cons:
        message += "❌ *Punti deboli:*\n"
        for con in cons[:3]:
            message += f"• {con}\n"
    
    # Create inline keyboard if there's a product URL
    keyboard = None
    if url := analysis_result.get('url'):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="🛒 Vedi Prodotto", url=url)]
        ])
    
    return message, keyboard

async def handle_callback_query(update: Update, context: Any):
    """Handle callback queries from inline keyboard buttons"""
    query = update.callback_query
    await query.answer()
    
    action, url = query.data.split('_', 1)
    
    if action == "refresh":
        try:
            data = await analyze_product(url)
            message, keyboard = await format_analysis_response(data)
            await query.edit_message_text(
                text=message,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        except Exception as e:
            await query.edit_message_text(
                text=f"❌ Errore nell'aggiornamento dell'analisi: {str(e)}",
                parse_mode="Markdown"
            )
    elif action == "compare":
        await query.edit_message_text(
            text="🔄 Ricerca prezzi in corso...",
            parse_mode="Markdown"
        )
        # Here you would implement price comparison logic
        # For now, we'll just show a placeholder message
        await query.edit_message_text(
            text="📊 Funzionalità di confronta prezzi in arrivo!\n\nStay tuned per gli aggiornamenti.",
            parse_mode="Markdown"
        )

def get_bot_instance() -> Bot:
    """Get or create a Bot instance (singleton pattern)"""
    global _bot_instance
    if _bot_instance is None:
        load_dotenv()
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_TOKEN environment variable is not set")
        _bot_instance = Bot(token)
    return _bot_instance

async def process_telegram_update(update: Update) -> None:
    """Process incoming telegram updates with proper event loop handling and monitoring."""
    loop = None
    try:
        # Get or create event loop with proper error handling and monitoring
        try:
            loop = asyncio.get_running_loop()
            logger.debug("Using existing event loop")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            logger.info("Created new event loop for update processing")
            
        # Set up task cancellation and exception handling
        loop.set_exception_handler(lambda loop, context: logger.error(f"Event loop error: {context}"))
        
        # Get bot instance and ensure it's initialized with proper validation
        bot = get_bot_instance()
        if not bot:
            logger.error("Bot instance initialization failed")
            raise Exception("Bot instance not initialized")
        
        # Process the update
        if update.message and update.message.text:
            if update.message.text.startswith('/'):
                # Handle commands
                command = update.message.text.split()[0][1:]  # Remove the '/' prefix
                if command == 'start':
                    await bot.start(update, None)
                elif command == 'analisi':
                    await bot.handle_analysis(update, None)
                elif command == 'aiuto':
                    await bot.handle_help(update, None)
                elif command == 'cerca':
                    await bot.handle_search(update, None)
                elif command == 'popolari':
                    await bot.handle_popular(update, None)
                else:
                    await update.message.reply_text("Comando non riconosciuto. Usa /aiuto per vedere i comandi disponibili.")
            else:
                await bot.handle_text(update, None)
        elif update.callback_query:
            await bot.handle_callback_query(update, None)
    except RuntimeError as re:
        if "Event loop is closed" in str(re):
            # Create a new event loop and retry once
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                if update.message and update.message.text:
                    await handle_text(update, None)
            except Exception as retry_error:
                print(f"Failed to process update after event loop retry: {retry_error}")
        else:
            raise
    except Exception as e:
        print(f"Error processing telegram update: {e}")
        # Notify user of error if possible
        try:
            if update.message:
                await update.message.reply_text(
                    "Mi dispiace, si è verificato un errore. Riprova più tardi."
                )
        except Exception as notify_error:
            print(f"Failed to notify user of error: {notify_error}")

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {"status": "ok", "service": "WorthIt! Bot", "version": "1.0.0"}

@app.get("/")
async def root():
    """Root endpoint for basic information"""
    return {"message": "WorthIt! Bot API is running. Use /webhook for Telegram updates."}

class EventLoopManager:
    """Manages event loop lifecycle and prevents race conditions."""
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create an event loop with proper error handling."""
        async with self._lock:
            try:
                loop = asyncio.get_running_loop()
                logger.debug("Using existing event loop")
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                logger.info("Created new event loop")
                
            # Configure loop with proper error handling
            loop.set_exception_handler(self._handle_loop_exception)
            return loop
    
    def _handle_loop_exception(self, loop: asyncio.AbstractEventLoop, context: Dict[str, Any]):
        """Handle loop exceptions with proper logging and recovery."""
        logger.error(f"Event loop error: {context}")
        
        # Extract exception details
        exception = context.get('exception')
        message = context.get('message')
        
        if exception:
            logger.error(f"Exception in event loop: {exception.__class__.__name__}: {str(exception)}")
        
        # Attempt recovery for known error conditions
        if isinstance(exception, asyncio.CancelledError):
            logger.info("Task cancelled - this is expected in some cases")
        elif "Event loop is closed" in str(context):
            logger.warning("Event loop closed unexpectedly - will create new loop on next request")
        else:
            logger.error(f"Unhandled event loop error: {message}")

# Initialize the event loop manager
_loop_manager = EventLoopManager()

# Update the webhook handler to use the event loop manager
@app.post("/webhook")
@limiter.limit("5/minute")
async def webhook_handler(request: Request):
    """Handle incoming updates from Telegram using proper event loop management."""
    try:
        # Get managed event loop
        loop = await _loop_manager.get_loop()
        
        # Get the bot instance (singleton)
        bot = get_bot_instance()
        if not bot:
            logger.error("Bot instance not initialized")
            return {"status": "error", "detail": "Bot not initialized"}
        
        # Parse the update
        data = await request.json()
        update = Update.de_json(data, bot)
        
        # Handle /start command immediately
        if update.message and update.message.text and update.message.text.startswith("/start"):
            try:
                await bot.start(update, None)
                return {"status": "ok", "detail": "Start command processed"}
            except Exception as e:
                logger.error(f"Error processing start command: {e}")
                return {"status": "error", "detail": str(e)}
        
        # For other commands, enqueue the task with proper metadata
        try:
            task = {
                'task_type': 'telegram_update',
                'update_data': data,
                'chat_id': update.effective_chat.id if update.effective_chat else None,
                'created_at': loop.time(),
                'status': 'pending',
                'priority': 'high' if update.message and update.message.text and 
                           any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]) 
                           else 'normal'
            }
            
            task_id = await enqueue_task(task)
            logger.info(f"Task {task_id} enqueued successfully with priority {task['priority']}")
            
            return {
                "status": "ok", 
                "detail": "Task enqueued for processing", 
                "task_id": task_id,
                "priority": task['priority']
            }
            
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            return {"status": "error", "detail": f"Failed to enqueue task: {str(e)}"}
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}

@app.post("/webhook")
@limiter.limit("5/minute")
async def webhook_handler(request: Request):
    """Handle incoming updates from Telegram using a stateless approach with Redis queue"""
    try:
        # Get the bot instance (singleton)
        bot = get_bot_instance()
        if not bot:
            logger.error("Bot instance not initialized")
            return {"status": "error", "detail": "Bot not initialized"}
        
        # Parse the update
        data = await request.json()
        update = Update.de_json(data, bot)
        
        # Ensure we have a valid event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Handle /start command immediately
        if update.message and update.message.text and update.message.text.startswith("/start"):
            try:
                await bot.start(update, None)
                USER_START_COMMANDS.inc()
                return {"status": "ok", "detail": "Start command processed"}
            except Exception as e:
                logger.error(f"Error processing start command: {e}")
                return {"status": "error", "detail": str(e)}
        
        # For other commands, enqueue the task
        try:
            from worker.queue import enqueue_task, get_task_queue
            
            # Initialize task queue with connection check
            task_queue = get_task_queue()
            await task_queue.connect()
            
            # Create task with improved metadata
            task = {
                'task_type': 'telegram_update',
                'update_data': data,
                'chat_id': update.effective_chat.id if update.effective_chat else None,
                'created_at': asyncio.get_event_loop().time(),
                'status': 'pending',
                'priority': 'high' if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]) else 'normal'
            }
            
            # Track product link interactions
            if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]):
                USER_LINK_INTERACTIONS.inc()
            task_id = await enqueue_task(task)
            logger.info(f"Task {task_id} enqueued successfully with priority {task['priority']}")
            
            return {
                "status": "ok", 
                "detail": "Task enqueued for processing", 
                "task_id": task_id,
                "priority": task['priority']
            }
            
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            return {"status": "error", "detail": f"Failed to enqueue task: {str(e)}"}
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}

class WebhookHandler:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.logger = logging.getLogger(__name__)
        self._setup_monitoring()

    def _setup_monitoring(self):
        """Initialize monitoring metrics for webhook handler"""
        self.webhook_latency = RESPONSE_TIME.labels(
            method='POST',
            endpoint='/webhook',
            component='webhook_handler'
        )
        self.webhook_counter = REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='success',
            component='webhook_handler'
        )

    async def handle_update(self, update: dict) -> None:
        """Handle incoming webhook updates with enhanced monitoring and error handling"""
        start_time = time.time()
        try:
            telegram_update = Update.de_json(update, _bot_instance)
            await self._process_update(telegram_update)
            duration = time.time() - start_time
            self.webhook_latency.observe(duration)
            self.webhook_counter.inc()
        except Exception as e:
            error_context = {
                "update_id": update.get('update_id'),
                "chat_id": update.get('message', {}).get('chat', {}).get('id'),
                "error": str(e)
            }
            self.logger.error(
                "Error processing webhook update",
                extra={"context": json.dumps(error_context)},
                exc_info=True
            )
            await self._handle_error(e, error_context)

    async def _process_update(self, update: Update) -> None:
        """Process a single update with proper error handling"""
        if update.message and update.message.text:
            if update.message.text.startswith('/'):
                await self._handle_command(update)
            else:
                await self._handle_message(update)
        elif update.callback_query:
            await self._handle_callback(update.callback_query)

    async def _handle_error(self, error: Exception, context: dict) -> None:
        """Enhanced error handling with proper monitoring and user communication"""
        REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='error',
            component='webhook_handler'
        ).inc()

        if isinstance(error, httpx.HTTPError):
            await self._handle_http_error(error, context)
        elif isinstance(error, asyncio.TimeoutError):
            await self._handle_timeout_error(context)
        else:
            await self._handle_general_error(error, context)

@app.post("/webhook")
@limiter.limit("5/minute")
async def webhook_handler(request: Request):
    """Handle incoming updates from Telegram using a stateless approach with Redis queue"""
    try:
        # Get the bot instance (singleton)
        bot = get_bot_instance()
        if not bot:
            logger.error("Bot instance not initialized")
            return {"status": "error", "detail": "Bot not initialized"}
        
        # Parse the update
        data = await request.json()
        update = Update.de_json(data, bot)
        
        # Ensure we have a valid event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Handle /start command immediately
        if update.message and update.message.text and update.message.text.startswith("/start"):
            try:
                await bot.start(update, None)
                USER_START_COMMANDS.inc()
                return {"status": "ok", "detail": "Start command processed"}
            except Exception as e:
                logger.error(f"Error processing start command: {e}")
                return {"status": "error", "detail": str(e)}
        
        # For other commands, enqueue the task
        try:
            from worker.queue import enqueue_task, get_task_queue
            
            # Initialize task queue with connection check
            task_queue = get_task_queue()
            await task_queue.connect()
            
            # Create task with improved metadata
            task = {
                'task_type': 'telegram_update',
                'update_data': data,
                'chat_id': update.effective_chat.id if update.effective_chat else None,
                'created_at': asyncio.get_event_loop().time(),
                'status': 'pending',
                'priority': 'high' if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]) else 'normal'
            }
            
            # Track product link interactions
            if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]):
                USER_LINK_INTERACTIONS.inc()
            task_id = await enqueue_task(task)
            logger.info(f"Task {task_id} enqueued successfully with priority {task['priority']}")
            
            return {
                "status": "ok", 
                "detail": "Task enqueued for processing", 
                "task_id": task_id,
                "priority": task['priority']
            }
            
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            return {"status": "error", "detail": f"Failed to enqueue task: {str(e)}"}
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}

class WebhookHandler:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.logger = logging.getLogger(__name__)
        self._setup_monitoring()

    def _setup_monitoring(self):
        """Initialize monitoring metrics for webhook handler"""
        self.webhook_latency = RESPONSE_TIME.labels(
            method='POST',
            endpoint='/webhook',
            component='webhook_handler'
        )
        self.webhook_counter = REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='success',
            component='webhook_handler'
        )

    async def handle_update(self, update: dict) -> None:
        """Handle incoming webhook updates with enhanced monitoring and error handling"""
        start_time = time.time()
        try:
            telegram_update = Update.de_json(update, _bot_instance)
            await self._process_update(telegram_update)
            duration = time.time() - start_time
            self.webhook_latency.observe(duration)
            self.webhook_counter.inc()
        except Exception as e:
            error_context = {
                "update_id": update.get('update_id'),
                "chat_id": update.get('message', {}).get('chat', {}).get('id'),
                "error": str(e)
            }
            self.logger.error(
                "Error processing webhook update",
                extra={"context": json.dumps(error_context)},
                exc_info=True
            )
            await self._handle_error(e, error_context)

    async def _process_update(self, update: Update) -> None:
        """Process a single update with proper error handling"""
        if update.message and update.message.text:
            if update.message.text.startswith('/'):
                await self._handle_command(update)
            else:
                await self._handle_message(update)
        elif update.callback_query:
            await self._handle_callback(update.callback_query)

    async def _handle_error(self, error: Exception, context: dict) -> None:
        """Enhanced error handling with proper monitoring and user communication"""
        REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='error',
            component='webhook_handler'
        ).inc()

        if isinstance(error, httpx.HTTPError):
            await self._handle_http_error(error, context)
        elif isinstance(error, asyncio.TimeoutError):
            await self._handle_timeout_error(context)
        else:
            await self._handle_general_error(error, context)

@app.post("/webhook")
@limiter.limit("5/minute")
async def webhook_handler(request: Request):
    """Handle incoming updates from Telegram using a stateless approach with Redis queue"""
    try:
        # Get the bot instance (singleton)
        bot = get_bot_instance()
        if not bot:
            logger.error("Bot instance not initialized")
            return {"status": "error", "detail": "Bot not initialized"}
        
        # Parse the update
        data = await request.json()
        update = Update.de_json(data, bot)
        
        # Ensure we have a valid event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Handle /start command immediately
        if update.message and update.message.text and update.message.text.startswith("/start"):
            try:
                await bot.start(update, None)
                USER_START_COMMANDS.inc()
                return {"status": "ok", "detail": "Start command processed"}
            except Exception as e:
                logger.error(f"Error processing start command: {e}")
                return {"status": "error", "detail": str(e)}
        
        # For other commands, enqueue the task
        try:
            from worker.queue import enqueue_task, get_task_queue
            
            # Initialize task queue with connection check
            task_queue = get_task_queue()
            await task_queue.connect()
            
            # Create task with improved metadata
            task = {
                'task_type': 'telegram_update',
                'update_data': data,
                'chat_id': update.effective_chat.id if update.effective_chat else None,
                'created_at': asyncio.get_event_loop().time(),
                'status': 'pending',
                'priority': 'high' if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]) else 'normal'
            }
            
            # Track product link interactions
            if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]):
                USER_LINK_INTERACTIONS.inc()
            task_id = await enqueue_task(task)
            logger.info(f"Task {task_id} enqueued successfully with priority {task['priority']}")
            
            return {
                "status": "ok", 
                "detail": "Task enqueued for processing", 
                "task_id": task_id,
                "priority": task['priority']
            }
            
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            return {"status": "error", "detail": f"Failed to enqueue task: {str(e)}"}
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}

class WebhookHandler:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.logger = logging.getLogger(__name__)
        self._setup_monitoring()

    def _setup_monitoring(self):
        """Initialize monitoring metrics for webhook handler"""
        self.webhook_latency = RESPONSE_TIME.labels(
            method='POST',
            endpoint='/webhook',
            component='webhook_handler'
        )
        self.webhook_counter = REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='success',
            component='webhook_handler'
        )

    async def handle_update(self, update: dict) -> None:
        """Handle incoming webhook updates with enhanced monitoring and error handling"""
        start_time = time.time()
        try:
            telegram_update = Update.de_json(update, _bot_instance)
            await self._process_update(telegram_update)
            duration = time.time() - start_time
            self.webhook_latency.observe(duration)
            self.webhook_counter.inc()
        except Exception as e:
            error_context = {
                "update_id": update.get('update_id'),
                "chat_id": update.get('message', {}).get('chat', {}).get('id'),
                "error": str(e)
            }
            self.logger.error(
                "Error processing webhook update",
                extra={"context": json.dumps(error_context)},
                exc_info=True
            )
            await self._handle_error(e, error_context)

    async def _process_update(self, update: Update) -> None:
        """Process a single update with proper error handling"""
        if update.message and update.message.text:
            if update.message.text.startswith('/'):
                await self._handle_command(update)
            else:
                await self._handle_message(update)
        elif update.callback_query:
            await self._handle_callback(update.callback_query)

    async def _handle_error(self, error: Exception, context: dict) -> None:
        """Enhanced error handling with proper monitoring and user communication"""
        REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='error',
            component='webhook_handler'
        ).inc()

        if isinstance(error, httpx.HTTPError):
            await self._handle_http_error(error, context)
        elif isinstance(error, asyncio.TimeoutError):
            await self._handle_timeout_error(context)
        else:
            await self._handle_general_error(error, context)

@app.post("/webhook")
@limiter.limit("5/minute")
async def webhook_handler(request: Request):
    """Handle incoming updates from Telegram using a stateless approach with Redis queue"""
    try:
        # Get the bot instance (singleton)
        bot = get_bot_instance()
        if not bot:
            logger.error("Bot instance not initialized")
            return {"status": "error", "detail": "Bot not initialized"}
        
        # Parse the update
        data = await request.json()
        update = Update.de_json(data, bot)
        
        # Ensure we have a valid event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Handle /start command immediately
        if update.message and update.message.text and update.message.text.startswith("/start"):
            try:
                await bot.start(update, None)
                USER_START_COMMANDS.inc()
                return {"status": "ok", "detail": "Start command processed"}
            except Exception as e:
                logger.error(f"Error processing start command: {e}")
                return {"status": "error", "detail": str(e)}
        
        # For other commands, enqueue the task
        try:
            from worker.queue import enqueue_task, get_task_queue
            
            # Initialize task queue with connection check
            task_queue = get_task_queue()
            await task_queue.connect()
            
            # Create task with improved metadata
            task = {
                'task_type': 'telegram_update',
                'update_data': data,
                'chat_id': update.effective_chat.id if update.effective_chat else None,
                'created_at': asyncio.get_event_loop().time(),
                'status': 'pending',
                'priority': 'high' if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]) else 'normal'
            }
            
            # Track product link interactions
            if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]):
                USER_LINK_INTERACTIONS.inc()
            task_id = await enqueue_task(task)
            logger.info(f"Task {task_id} enqueued successfully with priority {task['priority']}")
            
            return {
                "status": "ok", 
                "detail": "Task enqueued for processing", 
                "task_id": task_id,
                "priority": task['priority']
            }
            
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            return {"status": "error", "detail": f"Failed to enqueue task: {str(e)}"}
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}

class WebhookHandler:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.logger = logging.getLogger(__name__)
        self._setup_monitoring()

    def _setup_monitoring(self):
        """Initialize monitoring metrics for webhook handler"""
        self.webhook_latency = RESPONSE_TIME.labels(
            method='POST',
            endpoint='/webhook',
            component='webhook_handler'
        )
        self.webhook_counter = REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='success',
            component='webhook_handler'
        )

    async def handle_update(self, update: dict) -> None:
        """Handle incoming webhook updates with enhanced monitoring and error handling"""
        start_time = time.time()
        try:
            telegram_update = Update.de_json(update, _bot_instance)
            await self._process_update(telegram_update)
            duration = time.time() - start_time
            self.webhook_latency.observe(duration)
            self.webhook_counter.inc()
        except Exception as e:
            error_context = {
                "update_id": update.get('update_id'),
                "chat_id": update.get('message', {}).get('chat', {}).get('id'),
                "error": str(e)
            }
            self.logger.error(
                "Error processing webhook update",
                extra={"context": json.dumps(error_context)},
                exc_info=True
            )
            await self._handle_error(e, error_context)

    async def _process_update(self, update: Update) -> None:
        """Process a single update with proper error handling"""
        if update.message and update.message.text:
            if update.message.text.startswith('/'):
                await self._handle_command(update)
            else:
                await self._handle_message(update)
        elif update.callback_query:
            await self._handle_callback(update.callback_query)

    async def _handle_error(self, error: Exception, context: dict) -> None:
        """Enhanced error handling with proper monitoring and user communication"""
        REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='error',
            component='webhook_handler'
        ).inc()

        if isinstance(error, httpx.HTTPError):
            await self._handle_http_error(error, context)
        elif isinstance(error, asyncio.TimeoutError):
            await self._handle_timeout_error(context)
        else:
            await self._handle_general_error(error, context)

@app.post("/webhook")
@limiter.limit("5/minute")
async def webhook_handler(request: Request):
    """Handle incoming updates from Telegram using a stateless approach with Redis queue"""
    try:
        # Get the bot instance (singleton)
        bot = get_bot_instance()
        if not bot:
            logger.error("Bot instance not initialized")
            return {"status": "error", "detail": "Bot not initialized"}
        
        # Parse the update
        data = await request.json()
        update = Update.de_json(data, bot)
        
        # Ensure we have a valid event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Handle /start command immediately
        if update.message and update.message.text and update.message.text.startswith("/start"):
            try:
                await bot.start(update, None)
                USER_START_COMMANDS.inc()
                return {"status": "ok", "detail": "Start command processed"}
            except Exception as e:
                logger.error(f"Error processing start command: {e}")
                return {"status": "error", "detail": str(e)}
        
        # For other commands, enqueue the task
        try:
            from worker.queue import enqueue_task, get_task_queue
            
            # Initialize task queue with connection check
            task_queue = get_task_queue()
            await task_queue.connect()
            
            # Create task with improved metadata
            task = {
                'task_type': 'telegram_update',
                'update_data': data,
                'chat_id': update.effective_chat.id if update.effective_chat else None,
                'created_at': asyncio.get_event_loop().time(),
                'status': 'pending',
                'priority': 'high' if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]) else 'normal'
            }
            
            # Track product link interactions
            if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]):
                USER_LINK_INTERACTIONS.inc()
            task_id = await enqueue_task(task)
            logger.info(f"Task {task_id} enqueued successfully with priority {task['priority']}")
            
            return {
                "status": "ok", 
                "detail": "Task enqueued for processing", 
                "task_id": task_id,
                "priority": task['priority']
            }
            
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            return {"status": "error", "detail": f"Failed to enqueue task: {str(e)}"}
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}

class WebhookHandler:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.logger = logging.getLogger(__name__)
        self._setup_monitoring()

    def _setup_monitoring(self):
        """Initialize monitoring metrics for webhook handler"""
        self.webhook_latency = RESPONSE_TIME.labels(
            method='POST',
            endpoint='/webhook',
            component='webhook_handler'
        )
        self.webhook_counter = REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='success',
            component='webhook_handler'
        )

    async def handle_update(self, update: dict) -> None:
        """Handle incoming webhook updates with enhanced monitoring and error handling"""
        start_time = time.time()
        try:
            telegram_update = Update.de_json(update, _bot_instance)
            await self._process_update(telegram_update)
            duration = time.time() - start_time
            self.webhook_latency.observe(duration)
            self.webhook_counter.inc()
        except Exception as e:
            error_context = {
                "update_id": update.get('update_id'),
                "chat_id": update.get('message', {}).get('chat', {}).get('id'),
                "error": str(e)
            }
            self.logger.error(
                "Error processing webhook update",
                extra={"context": json.dumps(error_context)},
                exc_info=True
            )
            await self._handle_error(e, error_context)

    async def _process_update(self, update: Update) -> None:
        """Process a single update with proper error handling"""
        if update.message and update.message.text:
            if update.message.text.startswith('/'):
                await self._handle_command(update)
            else:
                await self._handle_message(update)
        elif update.callback_query:
            await self._handle_callback(update.callback_query)

    async def _handle_error(self, error: Exception, context: dict) -> None:
        """Enhanced error handling with proper monitoring and user communication"""
        REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='error',
            component='webhook_handler'
        ).inc()

        if isinstance(error, httpx.HTTPError):
            await self._handle_http_error(error, context)
        elif isinstance(error, asyncio.TimeoutError):
            await self._handle_timeout_error(context)
        else:
            await self._handle_general_error(error, context)

@app.post("/webhook")
@limiter.limit("5/minute")
async def webhook_handler(request: Request):
    """Handle incoming updates from Telegram using a stateless approach with Redis queue"""
    try:
        # Get the bot instance (singleton)
        bot = get_bot_instance()
        if not bot:
            logger.error("Bot instance not initialized")
            return {"status": "error", "detail": "Bot not initialized"}
        
        # Parse the update
        data = await request.json()
        update = Update.de_json(data, bot)
        
        # Ensure we have a valid event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Handle /start command immediately
        if update.message and update.message.text and update.message.text.startswith("/start"):
            try:
                await bot.start(update, None)
                USER_START_COMMANDS.inc()
                return {"status": "ok", "detail": "Start command processed"}
            except Exception as e:
                logger.error(f"Error processing start command: {e}")
                return {"status": "error", "detail": str(e)}
        
        # For other commands, enqueue the task
        try:
            from worker.queue import enqueue_task, get_task_queue
            
            # Initialize task queue with connection check
            task_queue = get_task_queue()
            await task_queue.connect()
            
            # Create task with improved metadata
            task = {
                'task_type': 'telegram_update',
                'update_data': data,
                'chat_id': update.effective_chat.id if update.effective_chat else None,
                'created_at': asyncio.get_event_loop().time(),
                'status': 'pending',
                'priority': 'high' if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]) else 'normal'
            }
            
            # Track product link interactions
            if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]):
                USER_LINK_INTERACTIONS.inc()
            task_id = await enqueue_task(task)
            logger.info(f"Task {task_id} enqueued successfully with priority {task['priority']}")
            
            return {
                "status": "ok", 
                "detail": "Task enqueued for processing", 
                "task_id": task_id,
                "priority": task['priority']
            }
            
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            return {"status": "error", "detail": f"Failed to enqueue task: {str(e)}"}
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}

class WebhookHandler:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.logger = logging.getLogger(__name__)
        self._setup_monitoring()

    def _setup_monitoring(self):
        """Initialize monitoring metrics for webhook handler"""
        self.webhook_latency = RESPONSE_TIME.labels(
            method='POST',
            endpoint='/webhook',
            component='webhook_handler'
        )
        self.webhook_counter = REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='success',
            component='webhook_handler'
        )

    async def handle_update(self, update: dict) -> None:
        """Handle incoming webhook updates with enhanced monitoring and error handling"""
        start_time = time.time()
        try:
            telegram_update = Update.de_json(update, _bot_instance)
            await self._process_update(telegram_update)
            duration = time.time() - start_time
            self.webhook_latency.observe(duration)
            self.webhook_counter.inc()
        except Exception as e:
            error_context = {
                "update_id": update.get('update_id'),
                "chat_id": update.get('message', {}).get('chat', {}).get('id'),
                "error": str(e)
            }
            self.logger.error(
                "Error processing webhook update",
                extra={"context": json.dumps(error_context)},
                exc_info=True
            )
            await self._handle_error(e, error_context)

    async def _process_update(self, update: Update) -> None:
        """Process a single update with proper error handling"""
        if update.message and update.message.text:
            if update.message.text.startswith('/'):
                await self._handle_command(update)
            else:
                await self._handle_message(update)
        elif update.callback_query:
            await self._handle_callback(update.callback_query)

    async def _handle_error(self, error: Exception, context: dict) -> None:
        """Enhanced error handling with proper monitoring and user communication"""
        REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='error',
            component='webhook_handler'
        ).inc()

        if isinstance(error, httpx.HTTPError):
            await self._handle_http_error(error, context)
        elif isinstance(error, asyncio.TimeoutError):
            await self._handle_timeout_error(context)
        else:
            await self._handle_general_error(error, context)

@app.post("/webhook")
@limiter.limit("5/minute")
async def webhook_handler(request: Request):
    """Handle incoming updates from Telegram using a stateless approach with Redis queue"""
    try:
        # Get the bot instance (singleton)
        bot = get_bot_instance()
        if not bot:
            logger.error("Bot instance not initialized")
            return {"status": "error", "detail": "Bot not initialized"}
        
        # Parse the update
        data = await request.json()
        update = Update.de_json(data, bot)
        
        # Ensure we have a valid event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Handle /start command immediately
        if update.message and update.message.text and update.message.text.startswith("/start"):
            try:
                await bot.start(update, None)
                USER_START_COMMANDS.inc()
                return {"status": "ok", "detail": "Start command processed"}
            except Exception as e:
                logger.error(f"Error processing start command: {e}")
                return {"status": "error", "detail": str(e)}
        
        # For other commands, enqueue the task
        try:
            from worker.queue import enqueue_task, get_task_queue
            
            # Initialize task queue with connection check
            task_queue = get_task_queue()
            await task_queue.connect()
            
            # Create task with improved metadata
            task = {
                'task_type': 'telegram_update',
                'update_data': data,
                'chat_id': update.effective_chat.id if update.effective_chat else None,
                'created_at': asyncio.get_event_loop().time(),
                'status': 'pending',
                'priority': 'high' if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]) else 'normal'
            }
            
            # Track product link interactions
            if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]):
                USER_LINK_INTERACTIONS.inc()
            task_id = await enqueue_task(task)
            logger.info(f"Task {task_id} enqueued successfully with priority {task['priority']}")
            
            return {
                "status": "ok", 
                "detail": "Task enqueued for processing", 
                "task_id": task_id,
                "priority": task['priority']
            }
            
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            return {"status": "error", "detail": f"Failed to enqueue task: {str(e)}"}
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}

class WebhookHandler:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.logger = logging.getLogger(__name__)
        self._setup_monitoring()

    def _setup_monitoring(self):
        """Initialize monitoring metrics for webhook handler"""
        self.webhook_latency = RESPONSE_TIME.labels(
            method='POST',
            endpoint='/webhook',
            component='webhook_handler'
        )
        self.webhook_counter = REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='success',
            component='webhook_handler'
        )

    async def handle_update(self, update: dict) -> None:
        """Handle incoming webhook updates with enhanced monitoring and error handling"""
        start_time = time.time()
        try:
            telegram_update = Update.de_json(update, _bot_instance)
            await self._process_update(telegram_update)
            duration = time.time() - start_time
            self.webhook_latency.observe(duration)
            self.webhook_counter.inc()
        except Exception as e:
            error_context = {
                "update_id": update.get('update_id'),
                "chat_id": update.get('message', {}).get('chat', {}).get('id'),
                "error": str(e)
            }
            self.logger.error(
                "Error processing webhook update",
                extra={"context": json.dumps(error_context)},
                exc_info=True
            )
            await self._handle_error(e, error_context)

    async def _process_update(self, update: Update) -> None:
        """Process a single update with proper error handling"""
        if update.message and update.message.text:
            if update.message.text.startswith('/'):
                await self._handle_command(update)
            else:
                await self._handle_message(update)
        elif update.callback_query:
            await self._handle_callback(update.callback_query)

    async def _handle_error(self, error: Exception, context: dict) -> None:
        """Enhanced error handling with proper monitoring and user communication"""
        REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='error',
            component='webhook_handler'
        ).inc()

        if isinstance(error, httpx.HTTPError):
            await self._handle_http_error(error, context)
        elif isinstance(error, asyncio.TimeoutError):
            await self._handle_timeout_error(context)
        else:
            await self._handle_general_error(error, context)

@app.post("/webhook")
@limiter.limit("5/minute")
async def webhook_handler(request: Request):
    """Handle incoming updates from Telegram using a stateless approach with Redis queue"""
    try:
        # Get the bot instance (singleton)
        bot = get_bot_instance()
        if not bot:
            logger.error("Bot instance not initialized")
            return {"status": "error", "detail": "Bot not initialized"}
        
        # Parse the update
        data = await request.json()
        update = Update.de_json(data, bot)
        
        # Ensure we have a valid event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Handle /start command immediately
        if update.message and update.message.text and update.message.text.startswith("/start"):
            try:
                await bot.start(update, None)
                USER_START_COMMANDS.inc()
                return {"status": "ok", "detail": "Start command processed"}
            except Exception as e:
                logger.error(f"Error processing start command: {e}")
                return {"status": "error", "detail": str(e)}
        
        # For other commands, enqueue the task
        try:
            from worker.queue import enqueue_task, get_task_queue
            
            # Initialize task queue with connection check
            task_queue = get_task_queue()
            await task_queue.connect()
            
            # Create task with improved metadata
            task = {
                'task_type': 'telegram_update',
                'update_data': data,
                'chat_id': update.effective_chat.id if update.effective_chat else None,
                'created_at': asyncio.get_event_loop().time(),
                'status': 'pending',
                'priority': 'high' if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]) else 'normal'
            }
            
            # Track product link interactions
            if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]):
                USER_LINK_INTERACTIONS.inc()
            task_id = await enqueue_task(task)
            logger.info(f"Task {task_id} enqueued successfully with priority {task['priority']}")
            
            return {
                "status": "ok", 
                "detail": "Task enqueued for processing", 
                "task_id": task_id,
                "priority": task['priority']
            }
            
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            return {"status": "error", "detail": f"Failed to enqueue task: {str(e)}"}
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}

class WebhookHandler:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.logger = logging.getLogger(__name__)
        self._setup_monitoring()

    def _setup_monitoring(self):
        """Initialize monitoring metrics for webhook handler"""
        self.webhook_latency = RESPONSE_TIME.labels(
            method='POST',
            endpoint='/webhook',
            component='webhook_handler'
        )
        self.webhook_counter = REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='success',
            component='webhook_handler'
        )

    async def handle_update(self, update: dict) -> None:
        """Handle incoming webhook updates with enhanced monitoring and error handling"""
        start_time = time.time()
        try:
            telegram_update = Update.de_json(update, _bot_instance)
            await self._process_update(telegram_update)
            duration = time.time() - start_time
            self.webhook_latency.observe(duration)
            self.webhook_counter.inc()
        except Exception as e:
            error_context = {
                "update_id": update.get('update_id'),
                "chat_id": update.get('message', {}).get('chat', {}).get('id'),
                "error": str(e)
            }
            self.logger.error(
                "Error processing webhook update",
                extra={"context": json.dumps(error_context)},
                exc_info=True
            )
            await self._handle_error(e, error_context)

    async def _process_update(self, update: Update) -> None:
        """Process a single update with proper error handling"""
        if update.message and update.message.text:
            if update.message.text.startswith('/'):
                await self._handle_command(update)
            else:
                await self._handle_message(update)
        elif update.callback_query:
            await self._handle_callback(update.callback_query)

    async def _handle_error(self, error: Exception, context: dict) -> None:
        """Enhanced error handling with proper monitoring and user communication"""
        REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='error',
            component='webhook_handler'
        ).inc()

        if isinstance(error, httpx.HTTPError):
            await self._handle_http_error(error, context)
        elif isinstance(error, asyncio.TimeoutError):
            await self._handle_timeout_error(context)
        else:
            await self._handle_general_error(error, context)

@app.post("/webhook")
@limiter.limit("5/minute")
async def webhook_handler(request: Request):
    """Handle incoming updates from Telegram using a stateless approach with Redis queue"""
    try:
        # Get the bot instance (singleton)
        bot = get_bot_instance()
        if not bot:
            logger.error("Bot instance not initialized")
            return {"status": "error", "detail": "Bot not initialized"}
        
        # Parse the update
        data = await request.json()
        update = Update.de_json(data, bot)
        
        # Ensure we have a valid event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Handle /start command immediately
        if update.message and update.message.text and update.message.text.startswith("/start"):
            try:
                await bot.start(update, None)
                USER_START_COMMANDS.inc()
                return {"status": "ok", "detail": "Start command processed"}
            except Exception as e:
                logger.error(f"Error processing start command: {e}")
                return {"status": "error", "detail": str(e)}
        
        # For other commands, enqueue the task
        try:
            from worker.queue import enqueue_task, get_task_queue
            
            # Initialize task queue with connection check
            task_queue = get_task_queue()
            await task_queue.connect()
            
            # Create task with improved metadata
            task = {
                'task_type': 'telegram_update',
                'update_data': data,
                'chat_id': update.effective_chat.id if update.effective_chat else None,
                'created_at': asyncio.get_event_loop().time(),
                'status': 'pending',
                'priority': 'high' if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]) else 'normal'
            }
            
            # Track product link interactions
            if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]):
                USER_LINK_INTERACTIONS.inc()
            task_id = await enqueue_task(task)
            logger.info(f"Task {task_id} enqueued successfully with priority {task['priority']}")
            
            return {
                "status": "ok", 
                "detail": "Task enqueued for processing", 
                "task_id": task_id,
                "priority": task['priority']
            }
            
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            return {"status": "error", "detail": f"Failed to enqueue task: {str(e)}"}
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}

class WebhookHandler:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.logger = logging.getLogger(__name__)
        self._setup_monitoring()

    def _setup_monitoring(self):
        """Initialize monitoring metrics for webhook handler"""
        self.webhook_latency = RESPONSE_TIME.labels(
            method='POST',
            endpoint='/webhook',
            component='webhook_handler'
        )
        self.webhook_counter = REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='success',
            component='webhook_handler'
        )

    async def handle_update(self, update: dict) -> None:
        """Handle incoming webhook updates with enhanced monitoring and error handling"""
        start_time = time.time()
        try:
            telegram_update = Update.de_json(update, _bot_instance)
            await self._process_update(telegram_update)
            duration = time.time() - start_time
            self.webhook_latency.observe(duration)
            self.webhook_counter.inc()
        except Exception as e:
            error_context = {
                "update_id": update.get('update_id'),
                "chat_id": update.get('message', {}).get('chat', {}).get('id'),
                "error": str(e)
            }
            self.logger.error(
                "Error processing webhook update",
                extra={"context": json.dumps(error_context)},
                exc_info=True
            )
            await self._handle_error(e, error_context)

    async def _process_update(self, update: Update) -> None:
        """Process a single update with proper error handling"""
        if update.message and update.message.text:
            if update.message.text.startswith('/'):
                await self._handle_command(update)
            else:
                await self._handle_message(update)
        elif update.callback_query:
            await self._handle_callback(update.callback_query)

    async def _handle_error(self, error: Exception, context: dict) -> None:
        """Enhanced error handling with proper monitoring and user communication"""
        REQUEST_COUNT.labels(
            method='POST',
            endpoint='/webhook',
            status='error',
            component='webhook_handler'
        ).inc()

        if isinstance(error, httpx.HTTPError):
            await self._handle_http_error(error, context)
        elif isinstance(error, asyncio.TimeoutError):
            await self._handle_timeout_error(context)
        else:
            await self._handle_general_error(error, context)

@app.post("/webhook")
@limiter.limit("5/minute")
async def webhook_handler(request: Request):
    """Handle incoming updates from Telegram using a stateless approach with Redis queue"""
    try:
        # Get the bot instance (singleton)
        bot = get_bot_instance()
        if not bot:
            logger.error("Bot instance not initialized")
            return {"status": "error", "detail": "Bot not initialized"}
        
        # Parse the update
        data = await request.json()
        update = Update.de_json(data, bot)
        
        # Ensure we have a valid event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Handle /start command immediately
        if update.message and update.message.text and update.message.text.startswith("/start"):
            try:
                await bot.start(update, None)
                USER_START_COMMANDS.inc()
                return {"status": "ok", "detail": "Start command processed"}
            except Exception as e:
                logger.error(f"Error processing start command: {e}")
                return {"status": "error", "detail": str(e)}
        
        # For other commands, enqueue the task
        try:
            from worker.queue import enqueue_task, get_task_queue
            
            # Initialize task queue with connection check
            task_queue = get_task_queue()
            await task_queue.connect()
            
            # Create task with improved metadata
            task = {
                'task_type': 'telegram_update',
                'update_data': data,
                'chat_id': update.effective_chat.id if update.effective_chat else None,
                'created_at': asyncio.get_event_loop().time(),
                'status': 'pending',
                'priority': 'high' if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]) else 'normal'
            }
            
            # Track product link interactions
            if update.message and update.message.text and any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]):
                USER_LINK_INTERACTIONS.inc()
            task_id = await enqueue_task(task)
            logger.info(f"Task {task_id} enqueued successfully with priority {task['priority']}")
            
            return {
                "status": "ok", 
                "detail": "Task enqueued for processing", 
                "task_id": task_id,
                "priority": task['priority']
            }
            
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            return {"status": "error", "detail": f"Failed to enqueue task: {str(e)}"}
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": "Internal server error"}