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
from .bot import start, handle_text
from .http_client import get_http_client, close_http_client

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
    """Handle errors in the telegram bot."""
    print(f"Exception while handling an update: {context.error}")
    
    # Special handling for event loop errors - don't try to send messages
    if isinstance(context.error, RuntimeError) and "Event loop is closed" in str(context.error):
        print("Detected event loop closure error - this is expected in serverless environments")
        return
    
    # Send a message to the user only for non-event-loop errors
    if update and hasattr(update, 'effective_message') and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Mi dispiace, si è verificato un errore durante l'elaborazione della richiesta."
            )
        except Exception as e:
            print(f"Failed to send error message: {e}")
    
    # Log the error
    print(f"Exception details: {context.error.__class__.__name__}: {context.error}")


# HTTP client functions are now imported from http_client.py

async def analyze_product(url: str, chat_id: int = None) -> Dict[str, Any]:
    """Call the WorthIt! API to analyze a product"""
    vercel_url = os.getenv("VERCEL_URL", "worth-it-bot-git-main-parnassusxs-projects.vercel.app")
    api_host = os.getenv("API_HOST", f"https://{vercel_url}")
    api_url = f"{api_host}/analyze"
    
    try:
        # Ensure we have a valid event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        # Enqueue the task for background processing
        from worker.queue import enqueue_task
        
        task = {
            'task_type': 'product_analysis',
            'url': url,
            'status': 'pending',
            'chat_id': chat_id
        }
        
        # Add task to Redis queue
        await enqueue_task(task)
        
        # Return initial response
        return {
            'status': 'processing',
            'message': 'Analisi in corso... 🔄\n\nSto esaminando il prodotto e le recensioni.\nRiceverai presto i risultati dettagliati.'
        }
        
    except Exception as e:
        print(f"Failed to enqueue task: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start analysis: {str(e)}"
        )
    
    # This code is unreachable due to the return statement above
    # client = get_http_client()
    try:
        try:
            response = await asyncio.wait_for(
                client.post(api_url, params={"url": url}),
                timeout=30.0
            )
            if response.status_code != 200:
                error_detail = await response.text()
                if response.status_code == 401:
                    raise HTTPException(
                        status_code=401,
                        detail="API authentication error: Please check API tokens"
                    )
                elif response.status_code == 400:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid product URL: {error_detail}"
                    )
                else:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"API error: {error_detail}"
                    )
            return response.json()
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Analysis timed out. Please try again later."
            )
        except Exception as e:
            print(f"API request error: {str(e)}")
            if "Connection refused" in str(e):
                raise HTTPException(
                    status_code=503,
                    detail="Service temporarily unavailable. Please try again later."
                )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to analyze product: {str(e)}"
            )
    finally:
        await close_http_client()

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
    """Process incoming telegram updates with proper event loop handling."""
    try:
        # Ensure we have a valid event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Get bot instance and ensure it's initialized
        bot = get_bot_instance()
        if not bot:
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