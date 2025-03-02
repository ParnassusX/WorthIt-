from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from typing import Dict, Any
import httpx
import os
import re
import asyncio
from api.security import validate_url
from .http_client import get_http_client, close_http_client

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
        api_url = f"{api_host}/analyze"
        
        try:
            # Use the shared HTTP client with optimized connection pooling
            client = get_http_client()
            response = await client.post(api_url, params={"url": url}, timeout=30.0)
            if response.status_code != 200:
                error_detail = await response.text()
                if response.status_code == 401:
                    raise Exception(f"API authentication error: Please check that APIFY_TOKEN and HF_TOKEN are correctly set in environment variables.")
                else:
                    raise Exception(f"API error: {response.status_code} - {error_detail}")
            data = response.json()
            
            # Format the response with inline keyboard
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
            
            # Create inline keyboard for actions
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(text="🔄 Aggiorna analisi", callback_data=f"refresh_{url}")],
                [InlineKeyboardButton(text="📊 Confronta prezzi", callback_data=f"compare_{url}")],
                [InlineKeyboardButton(text="📱 Apri nel browser", url=url)],
                [InlineKeyboardButton(text="📤 Condividi analisi", switch_inline_query=url)]
            ])
            
            await update.message.reply_text(message, parse_mode="Markdown", reply_markup=keyboard)
        except asyncio.TimeoutError:
            # Handle timeout specifically
            await update.message.reply_text(
                "L'analisi sta richiedendo più tempo del previsto. Riprova più tardi."
            )
        finally:
            # Ensure we close the client after use
            await close_http_client()
        
    except Exception as e:
        error_message = "Mi dispiace, non sono riuscito ad analizzare questo prodotto. "
        if "URL not supported" in str(e):
            error_message += "Per favore, usa un link di Amazon o eBay."
        elif "API authentication error" in str(e):
            error_message += "C'è un problema con l'autenticazione API. L'amministratore deve verificare le chiavi API."
        else:
            error_message += f"Errore: {str(e)}"
        await update.message.reply_text(error_message)

# Export handlers for webhook_handler.py
__all__ = ['start', 'handle_text']