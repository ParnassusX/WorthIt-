from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler
from fastapi import FastAPI, Request
import os

app = FastAPI()
bot = None

async def start(update: Update, context):
    await update.message.reply_text(
        "Benvenuto in WorthIt! 🚀\nScansiona un prodotto:",
        reply_markup={
            "keyboard": [[{
                "text": "Scansiona 📸", 
                "web_app": {"url": os.getenv("VERCEL_URL", "worth-it-bot-git-main-parnassusxs-projects.vercel.app")}
            }]]
        }
    )

@app.post("/webhook")
async def webhook(request: Request):
    global bot
    if not bot:
        bot = init_bot()
    data = await request.json()
    update = Update.de_json(data, bot)
    await bot.process_update(update)
    return {"status": "ok"}

def init_bot():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN environment variable is not set")
    
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    
    # Set webhook URL when deployed
    vercel_url = os.getenv("VERCEL_URL")
    if vercel_url:
        webhook_url = f"https://{vercel_url}/webhook"
        application.set_webhook(webhook_url)
    
    return application

if __name__ == "__main__":
    bot = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()
    bot.add_handler(CommandHandler("start", start))
    bot.run_polling()