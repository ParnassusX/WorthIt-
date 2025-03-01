from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from fastapi import FastAPI, Request
from dotenv import load_dotenv
import os
import httpx
import json
import re

app = FastAPI()
application = None

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
        await update.message.reply_text("Non ho capito. Invia un link di un prodotto o usa i pulsanti in basso.")

async def analyze_product_url(update, url):
    await update.message.reply_text(f"Sto analizzando il prodotto... Attendi un momento ⏳")
    
    try:
        # Call our API to analyze the product
        api_host = os.getenv("API_HOST", "https://worth-it-api.vercel.app")
        api_url = f"{api_host}/analyze?url={url}"
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url)
            data = response.json()
        
        # Extract pros and cons from analysis
        analysis_text = data["analysis"]
        pros = []
        cons = []
        
        # Simple parsing of pros/cons from the generated text
        lines = analysis_text.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            if "pros:" in line.lower() or "advantages:" in line.lower() or "strengths:" in line.lower():
                current_section = "pros"
                continue
            elif "cons:" in line.lower() or "disadvantages:" in line.lower() or "weaknesses:" in line.lower():
                current_section = "cons"
                continue
                
            if current_section == "pros" and line and not line.lower().startswith("cons"):
                if line.startswith("-") or line.startswith("*"):
                    pros.append(line.lstrip("-* ").capitalize())
                elif len(pros) < 3 and line:  # Backup if no bullet points
                    pros.append(line.capitalize())
                    
            if current_section == "cons" and line:
                if line.startswith("-") or line.startswith("*"):
                    cons.append(line.lstrip("-* ").capitalize())
                elif len(cons) < 3 and line:  # Backup if no bullet points
                    cons.append(line.capitalize())
        
        # Ensure we have at least some pros and cons
        if not pros:
            pros = ["Informazioni insufficienti"]
        if not cons:
            cons = ["Informazioni insufficienti"]
        
        # Format the response message
        value_emoji = "🟢" if data["value_score"] >= 7 else "🟡" if data["value_score"] >= 5 else "🔴"
        
        message = f"*{data['title']}*\n\n"
        message += f"💰 Prezzo: {data['price']}\n"
        message += f"⭐ Valore: {value_emoji} {data['value_score']}/10\n\n"
        message += f"*Raccomandazione:* {data['recommendation']}\n\n"
        
        message += "*Punti di forza:*\n"
        for pro in pros[:3]:  # Limit to 3 pros
            message += f"✅ {pro}\n"
        
        message += "\n*Punti deboli:*\n"
        for con in cons[:3]:  # Limit to 3 cons
            message += f"❌ {con}\n"
        
        # Add share button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="Condividi analisi", switch_inline_query=url)]
        ])
        
        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=keyboard)
        
    except Exception as e:
        await update.message.reply_text(f"Mi dispiace, non sono riuscito ad analizzare questo prodotto. Errore: {str(e)}")

@app.post("/webhook")
async def webhook(request: Request):
    global application
    try:
        if not application:
            application = init_application()
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.update_queue.put(update)
        return {"status": "ok"}
    except Exception as e:
        print(f"Error in webhook: {e}")
        return {"status": "error", "message": str(e)}

def init_application():
    load_dotenv()
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN environment variable is not set")
    
    application = ApplicationBuilder().token(token).build()
    
    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    
    # Register message handlers for non-command messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Set commands with Telegram API
    try:
        commands = [
            ("start", "Avvia il bot e mostra il menu principale")
        ]
        application.bot.set_my_commands(commands)
        print("Bot commands registered successfully")
    except Exception as e:
        print(f"Failed to register bot commands: {e}")
    
    application.start()
    return application

if __name__ == "__main__":
    init_application()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)