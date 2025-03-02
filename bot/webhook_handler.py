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

app = FastAPI()
# We'll use a more stateless approach instead of a global application instance
_bot_instance: Optional[Bot] = None

async def error_handler(update: object, context) -> None:
    """Handle errors in the telegram bot."""
    print(f"Exception while handling an update: {context.error}")
    
    # Send a message to the user
    if update and hasattr(update, 'effective_message') and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Mi dispiace, si è verificato un errore durante l'elaborazione della richiesta."
            )
        except Exception as e:
            print(f"Failed to send error message: {e}")
    
    # Log the error
    print(f"Exception details: {context.error.__class__.__name__}: {context.error}")
    
    # Special handling for event loop errors
    if isinstance(context.error, RuntimeError) and "Event loop is closed" in str(context.error):
        print("Detected event loop closure error - this is expected in serverless environments")
        return

async def analyze_product(url: str) -> Dict[str, Any]:
    """Call the WorthIt! API to analyze a product"""
    vercel_url = os.getenv("VERCEL_URL", "worth-it-bot-git-main-parnassusxs-projects.vercel.app")
    api_host = os.getenv("API_HOST", f"https://{vercel_url}")
    api_url = f"{api_host}/analyze"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, params={"url": url}, timeout=30.0)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except Exception as e:
        # Log the error for debugging
        print(f"API request error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze product: {str(e)}")

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
            text="📊 Funzionalità di confronto prezzi in arrivo!\n\nStay tuned per gli aggiornamenti.",
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
    """Process a Telegram update without using Application instance"""
    # Handle different types of updates directly
    if update.message:
        if update.message.text:
            if update.message.text.startswith("/start"):
                await start(update, None)
            else:
                await handle_text(update, None)
    elif update.callback_query:
        await handle_callback_query(update, None)

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Handle incoming updates from Telegram using a stateless approach"""
    try:
        # Get the bot instance (singleton)
        bot = get_bot_instance()
        
        # Parse the update
        data = await request.json()
        update = Update.de_json(data, bot)
        
        # Process update with timeout protection
        try:
            # Process the update directly without Application instance
            await asyncio.wait_for(process_telegram_update(update), timeout=30.0)
        except asyncio.TimeoutError:
            return {"status": "error", "detail": "Request timed out"}
        except RuntimeError as e:
            print(f"Event loop error: {str(e)}")
            # Return a successful response to prevent retries
            return {"status": "ok", "detail": "Event loop error handled"}
        
        return {"status": "ok"}
    
    except Exception as e:
        print(f"Error in webhook handler: {str(e)}")
        return {"status": "error", "detail": str(e)}