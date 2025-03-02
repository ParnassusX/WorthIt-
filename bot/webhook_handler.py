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

# Initialize a shared httpx client with proper connection pool settings
_http_client = None

def get_http_client():
    """Get or create a shared httpx client with proper connection pool settings"""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            http2=False
        )
    return _http_client

async def close_http_client():
    """Close the shared httpx client to free resources"""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None

async def analyze_product(url: str) -> Dict[str, Any]:
    """Call the WorthIt! API to analyze a product"""
    vercel_url = os.getenv("VERCEL_URL", "worth-it-bot-git-main-parnassusxs-projects.vercel.app")
    api_host = os.getenv("API_HOST", f"https://{vercel_url}")
    api_url = f"{api_host}/analyze"
    
    try:
        client = get_http_client()
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
    client = None
    try:
        client = get_http_client()
        
        # Send an immediate acknowledgment for long-running operations
        if update.message and update.message.text and not update.message.text.startswith("/start"):
            # Check if it might be a product URL
            if "amazon" in update.message.text.lower() or "ebay" in update.message.text.lower():
                try:
                    await asyncio.wait_for(
                        update.message.reply_text("Ho ricevuto il tuo link! Sto iniziando l'analisi in background... 🔄"),
                        timeout=2.0
                    )
                except asyncio.TimeoutError:
                    print("Acknowledgment timed out, but continuing processing")
                except Exception as ack_error:
                    print(f"Failed to send acknowledgment: {ack_error}")
                
        # Process the update with proper error handling for each step
        if update.message:
            if update.message.text:
                try:
                    if update.message.text.startswith("/start"):
                        await start(update, None)
                    else:
                        await handle_text(update, None)
                except HTTPException as http_error:
                    error_message = "Mi dispiace, "
                    if http_error.status_code == 401:
                        error_message += "c'è un problema con l'autenticazione API. Riprova più tardi."
                    elif http_error.status_code == 400:
                        error_message += "il link del prodotto non è valido. Assicurati di usare un link di Amazon o eBay."
                    elif http_error.status_code == 504:
                        error_message += "l'analisi sta richiedendo troppo tempo. Riprova più tardi."
                    elif http_error.status_code == 503:
                        error_message += "il servizio è temporaneamente non disponibile. Riprova più tardi."
                    else:
                        error_message += "si è verificato un errore durante l'analisi. Riprova più tardi."
                    
                    await asyncio.wait_for(
                        update.message.reply_text(error_message),
                        timeout=2.0
                    )
                except RuntimeError as re:
                    if "Event loop is closed" in str(re):
                        print("Ignoring closed event loop error in message handler")
                    else:
                        raise
                except Exception as msg_error:
                    print(f"Error handling message: {msg_error}")
                    try:
                        await asyncio.wait_for(
                            update.message.reply_text(
                                "Mi dispiace, si è verificato un errore durante l'elaborazione della richiesta. Riprova più tardi."
                            ),
                            timeout=2.0
                        )
                    except Exception:
                        pass
        elif update.callback_query:
            try:
                await handle_callback_query(update, None)
            except RuntimeError as re:
                if "Event loop is closed" in str(re):
                    print("Ignoring closed event loop error in callback handler")
                else:
                    raise
            except Exception as cb_error:
                print(f"Error handling callback query: {cb_error}")
    except Exception as e:
        print(f"Error in process_telegram_update: {str(e)}")
        if update.message:
            try:
                await asyncio.wait_for(
                    update.message.reply_text(
                        "Mi dispiace, si è verificato un errore durante l'elaborazione della richiesta. Riprova più tardi."
                    ),
                    timeout=2.0
                )
            except Exception:
                pass
    finally:
        if client is not None:
            await close_http_client()

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Handle incoming updates from Telegram using a stateless approach"""
    try:
        # Get the bot instance (singleton)
        bot = get_bot_instance()
        
        # Parse the update
        data = await request.json()
        update = Update.de_json(data, bot)
        
        # Process the update with proper connection management
        try:
            # Use a shorter timeout for the initial response
            async with asyncio.timeout(3.0):
                # Get a fresh client for this request
                client = get_http_client()
                try:
                    await process_telegram_update(update)
                finally:
                    # Ensure we close the client after use
                    await close_http_client()
        except asyncio.TimeoutError:
            print("Initial response timed out, continuing in background")
            # Schedule background processing without blocking
            asyncio.create_task(process_telegram_update(update))
            return {"status": "ok", "detail": "Processing in background"}
        except Exception as e:
            print(f"Error processing update: {str(e)}")
            # Close the client on error
            await close_http_client()
            return {"status": "ok", "detail": "Error handled gracefully"}
        
        return {"status": "ok"}
    
    except Exception as e:
        print(f"Error in webhook handler: {str(e)}")
        # Ensure client is closed on outer exceptions
        await close_http_client()
        return {"status": "error", "detail": str(e)}