from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler
import os

async def start(update: Update, context):
    await update.message.reply_text(
        "Benvenuto in WorthIt! 🚀\nScansiona un prodotto:",
        reply_markup={
            "keyboard": [[{
                "text": "Scansiona 📸", 
                "web_app": {"url": "https://your-app.vercel.app"}
            }]]
        }
    )

if __name__ == "__main__":
    app = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()