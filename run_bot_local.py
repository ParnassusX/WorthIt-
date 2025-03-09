import os
import asyncio
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder
from bot.bot import WorthItBot

async def main():
    # Load environment variables from .env.test for testing
    load_dotenv('.env.test')
    
    # Get the bot token
    token = os.getenv('TELEGRAM_TOKEN')
    if not token or token.strip() == '':
        print("❌ Error: TELEGRAM_TOKEN not found or empty in .env.test file")
        print("Please follow these steps to get a valid test bot token:")
        print("1. Message @BotFather on Telegram")
        print("2. Use the /newbot command to create a test bot")
        print("3. Copy the token provided by BotFather and paste it in your .env.test file")
        return
    
    print(f"🤖 Starting WorthIt! bot in polling mode (test environment)")
    print("Press Ctrl+C to stop the bot")
    
    # Create and run the bot
    bot = WorthItBot(token)
    await bot.app.initialize()
    await bot.app.start()
    
    # Keep the bot running until interrupted
    try:
        await bot.app.updater.start_polling()
        await asyncio.Event().wait()  # Run forever
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Bot stopped")
    finally:
        await bot.app.updater.stop()
        await bot.app.stop()
        await bot.app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())