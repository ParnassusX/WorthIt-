from fastapi import FastAPI, Request, HTTPException, Depends
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from typing import Optional, Dict, Any, Callable
import httpx
import os
import re
import asyncio
from dotenv import load_dotenv
from .bot import start, handle_text
from .http_client import get_http_client, close_http_client

app = FastAPI()
# We'll use a more stateless approach instead of a global application instance
_bot_instance: Optional[Bot] = None

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
        
        # Process the update
        if update.message and update.message.text:
            await handle_text(update, None)
        elif update.callback_query:
            # Handle callback queries here if needed
            pass
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
async def webhook_handler(request: Request):
    """Handle incoming updates from Telegram using a stateless approach with Redis queue"""
    try:
        # Get the bot instance (singleton)
        bot = get_bot_instance()
        
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
            await process_telegram_update(update)
            return {"status": "ok", "detail": "Start command processed"}
        
        # For product URLs, send acknowledgment before enqueueing
        if update.message and update.message.text:
            try:
                if update.message.text == "🔍 Cerca prodotto":
                    # Process through handle_text to ensure proper state management
                    await handle_text(update, None)
                    return {"status": "ok", "detail": "Search prompt sent"}
                elif any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]):
                    await update.message.reply_text("Sto analizzando il prodotto... Attendi un momento ⏳")
            except Exception as e:
                print(f"Error sending acknowledgment: {e}")
                # Create a new event loop if needed
                if isinstance(e, RuntimeError) and "Event loop is closed" in str(e):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    if update.message.text == "🔍 Cerca prodotto":
                        await update.message.reply_text("Inserisci il link del prodotto che vuoi analizzare 🔗")
                        return {"status": "ok", "detail": "Search prompt sent"}
                    elif any(domain in update.message.text.lower() for domain in ["amazon", "ebay"]):
                        await update.message.reply_text("Sto analizzando il prodotto... Attendi un momento ⏳")
        
        # Enqueue the task for background processing
        from worker.queue import enqueue_task
        task = {
            'task_type': 'telegram_update',
            'update_data': data,
            'chat_id': update.effective_chat.id if update.effective_chat else None
        }
        
        await enqueue_task(task)
        return {"status": "ok", "detail": "Task enqueued for processing"}
    
    except Exception as e:
        print(f"Error in webhook handler: {str(e)}")
        try:
            await close_http_client()
        except Exception as close_error:
            print(f"Error closing HTTP client: {close_error}")
        return {"status": "ok", "detail": str(e)}