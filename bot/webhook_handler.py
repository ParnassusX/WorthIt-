from fastapi import FastAPI, Request, HTTPException, Depends
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from typing import Optional, Dict, Any
import httpx
import os
import re
import asyncio
from dotenv import load_dotenv
from .bot import start, handle_text

app = FastAPI()
application: Optional[Application] = None

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

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Handle incoming updates from Telegram"""
    global application
    
    try:
        if not application:
            load_dotenv()
            token = os.getenv("TELEGRAM_TOKEN")
            if not token:
                raise ValueError("TELEGRAM_TOKEN environment variable is not set")
            
            application = Application.builder().token(token).build()
            application.add_handler(CommandHandler("start", start))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
            application.add_handler(CallbackQueryHandler(handle_callback_query))
            
            # Initialize but don't start the application
            await application.initialize()
            
            # Set bot commands
            await application.bot.set_my_commands([
                ("start", "Avvia il bot e mostra il menu principale"),
                ("help", "Mostra guida all'utilizzo"),
                ("settings", "Gestisci le impostazioni")
            ])
        
        # Process the update
        data = await request.json()
        update = Update.de_json(data, application.bot)
        
        # Create a new event loop for processing updates
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Process update in the new loop
            await application.process_update(update)
        finally:
            # Clean up the loop
            loop.close()
        
        return {"status": "ok"}
    
    except Exception as e:
        return {"status": "error", "detail": str(e)}