from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from typing import Dict, Any
import httpx
import os
import re
import asyncio
from api.security import validate_url
from .http_client import get_http_client, close_http_client

class WorthItBot:
    def __init__(self, token: str):
        self.token = token
        self.app = ApplicationBuilder().token(token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        self.app.add_handler(CommandHandler('start', start))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    async def run(self):
        await self.app.initialize()
        await self.app.start()
        await self.app.run_polling()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [{
            "text": "Scansiona 📸",
            "web_app": {"url": "https://" + os.getenv("VERCEL_URL", "worth-it-bot-git-main-parnassusxs-projects.vercel.app")}
        }],
        ["📊 Le mie analisi", "ℹ️ Aiuto"],
        ["🔍 Cerca prodotto", "⭐️ Prodotti popolari"]
    ]
    
    await update.message.reply_text(
        "Benvenuto in WorthIt! 🚀\nScegli un'opzione:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    # Check if text contains a URL
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, text)
    
    if urls:
        # Found a URL, assume it's a product URL
        await analyze_product_url(update, urls[0])
    elif text == "🔍 Cerca prodotto":
        await update.message.reply_text("Incolla il link del prodotto che vuoi analizzare")
    elif text == "📊 Le mie analisi":
        await update.message.reply_text("Funzionalità in arrivo nelle prossime versioni!")
    elif text == "⭐️ Prodotti popolari":
        await update.message.reply_text("Funzionalità in arrivo nelle prossime versioni!")
    elif text == "ℹ️ Aiuto":
        help_text = (
            "*Come usare WorthIt!*\n\n"
            "1️⃣ Invia un link di un prodotto\n"
            "2️⃣ Usa il pulsante 'Scansiona 📸' per aprire l'app web\n"
            "3️⃣ Ricevi un'analisi dettagliata sul valore reale del prodotto\n\n"
            "WorthIt! analizza recensioni e caratteristiche per dirti se un prodotto vale davvero il suo prezzo."
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")
    else:
        # Try to interpret as a product URL even if it doesn't match the pattern
        if "amazon" in text.lower() or "ebay" in text.lower():
            await update.message.reply_text("Sto provando ad analizzare questo come un link prodotto...")
            await analyze_product_url(update, text)
        else:
            await update.message.reply_text("Non ho capito. Invia un link di un prodotto o usa i pulsanti in basso.")

async def analyze_product_url(update: Update, url: str):
    try:
        # Validate URL
        validate_url(url)
        
        # Send immediate acknowledgment
        await update.message.reply_text("Sto analizzando il prodotto... Attendi un momento ⏳")
        
        # Call our API to analyze the product
        vercel_url = os.getenv("VERCEL_URL", "worth-it-bot-git-main-parnassusxs-projects.vercel.app")
        api_host = os.getenv("API_HOST", f"https://{vercel_url}")
        api_url = f"{api_host}/api/analyze"
        
        # Use the shared HTTP client with optimized connection pooling
        client = get_http_client()
        response = await client.post(api_url, json={"url": url}, timeout=30.0)
        response_data = await response.json()
        
        if response.status_code != 200:
            error_detail = response_data.get('error', 'Unknown error')
            raise Exception(f"API error: {response.status_code} - {error_detail}")
        
        return response_data
        
    except Exception as e:
        error_message = str(e)
        await update.message.reply_text(f"Mi dispiace, non sono riuscito ad analizzare questo prodotto. Errore: {error_message}")
        return {"status": "error", "error": error_message}

# Export handlers for webhook_handler.py
__all__ = ['start', 'handle_text', 'WorthItBot']