from fastapi import FastAPI, Request, HTTPException, Depends
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from typing import Optional, Dict, Any, Callable
import httpx
import os
import re
import asyncio
import logging
from dotenv import load_dotenv
from .bot import start, handle_text, analyze_product_url, format_analysis_response, get_bot_instance
from .http_client import get_http_client, close_http_client
from worker.queue import enqueue_task

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address

app = FastAPI()

# Rate limiting for production
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['POST'],
    allow_headers=['Content-Type']
)

# Initialize bot instance
bot_token = os.getenv('TELEGRAM_TOKEN')
if not bot_token:
    raise ValueError("TELEGRAM_TOKEN environment variable is not set")

_bot_instance = get_bot_instance(bot_token)

async def error_handler(update: object, context) -> None:
    """Handle errors in the telegram bot with enhanced logging and recovery."""
    error_context = {
        "error_type": context.error.__class__.__name__,
        "error_message": str(context.error),
        "timestamp": time.time(),
        "update_id": getattr(update, 'update_id', None)
    }
    
    logger.error(
        f"Exception while handling an update: {context.error}",
        extra={"context": json.dumps(error_context)},
        exc_info=True
    )
    
    # Special handling for event loop errors with recovery attempt
    if isinstance(context.error, RuntimeError) and "Event loop is closed" in str(context.error):
        logger.info(
            "Detected event loop closure - attempting recovery",
            extra={"context": json.dumps({"recovery": "event_loop"})}
        )
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return
        except Exception as e:
            logger.error(
                "Failed to recover event loop",
                extra={"context": json.dumps({"recovery_error": str(e)})}
            )
    
    # Enhanced user communication with proper error tracking
    if update and hasattr(update, 'effective_message') and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Mi dispiace, si è verificato un errore durante l'elaborazione della richiesta. "
                "Il team è stato notificato e risolverà il problema al più presto."
            )
        except Exception as e:
            logger.error(
                "Failed to send error message to user",
                extra={"context": json.dumps({"error": str(e), "chat_id": update.effective_chat.id})}
            )
    
    # Notify monitoring system
    try:
        await notify_error_monitoring(error_context)
    except Exception as e:
        logger.error(
            "Failed to notify monitoring system",
            extra={"context": json.dumps({"error": str(e)})}
        )


# HTTP client functions are now imported from http_client.py

async def analyze_product(url: str, chat_id: int = None) -> Dict[str, Any]:
    """Call the WorthIt! API to analyze a product with proper event loop handling.
    
    This function implements a robust approach to handling asynchronous product analysis:
    1. Event loop management with automatic recovery
    2. Task queuing for background processing
    3. Status monitoring with timeout
    4. Error handling with user feedback
    
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
    api_url = f"{api_host}/analyze"
    
    try:
        # Get or create event loop with proper error handling
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            logger.info("Created new event loop for product analysis")
        
        # Set up task cancellation handling
        loop.set_exception_handler(lambda loop, context: logger.error(f"Event loop error: {context}"))
        
        # Create a task for background processing
        task = {
            'task_type': 'product_analysis',
            'url': url,
            'status': 'pending',
            'chat_id': chat_id,
            'created_at': loop.time()
        }
        
        # Add task to Redis queue with monitoring
        task_id = await enqueue_task(task)
        logger.info(f"Enqueued task {task_id} for URL {url}")
        
        # Monitor task status
        from worker.queue import get_task_by_id
        status_check_count = 0
        while status_check_count < 5:  # Check status for up to 5 times
            await asyncio.sleep(2)  # Wait 2 seconds between checks
            task_status = await get_task_by_id(task_id)
            if task_status and task_status.get('status') != 'pending':
                return task_status
            status_check_count += 1
        
        # Return initial response if background processing is taking longer
        return {
            'status': 'processing',
            'task_id': task_id,
            'message': 'Analysis in progress'
        }
        
    except asyncio.CancelledError:
        logger.warning(f"Task cancelled for URL {url}")
        raise
    except Exception as e:
        logger.error(f"Error analyzing product {url}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
async def webhook(request: Request):
    """Handle incoming webhook requests from Telegram."""
    try:
        # Parse the update
        update_dict = await request.json()
        update = Update.de_json(update_dict, _bot_instance)
        
        # Process the update through worker queue
        await process_telegram_update(update)
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
            if any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]):
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
            if any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]):
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