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
        from telegram import MenuButtonWebApp, WebAppInfo, KeyboardButton, BotCommand
        from telegram.ext import CallbackQueryHandler
        
        # Register bot commands with Telegram servers
        commands = [
            BotCommand('start', 'Avvia il bot'),
            BotCommand('analisi', 'Le tue analisi salvate'),
            BotCommand('aiuto', 'Guida e informazioni'),
            BotCommand('cerca', 'Cerca un prodotto'),
            BotCommand('popolari', 'Prodotti più popolari')
        ]
        
        async def post_init(app):
            # Set commands and menu button
            await app.bot.set_my_commands(commands)
            await app.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text='Menu',
                    web_app=WebAppInfo(url=os.getenv('WEBAPP_URL', 'https://worthit-webapp.vercel.app'))
                )
            )
            
            # Initialize Redis connection for task queue
            from worker.queue import initialize_queue
            await initialize_queue()

        self.app.post_init = post_init

        # Add command handlers
        self.app.add_handler(CommandHandler('start', self.start))
        self.app.add_handler(CommandHandler('analisi', self.handle_analysis))
        self.app.add_handler(CommandHandler('aiuto', self.handle_help))
        self.app.add_handler(CommandHandler('cerca', self.handle_search))
        self.app.add_handler(CommandHandler('popolari', self.handle_popular))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        
        # Add callback query handler for inline keyboard actions
        self.app.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        # Add error handler
        self.app.add_error_handler(self.error_handler)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from telegram import KeyboardButton, WebAppInfo, ReplyKeyboardMarkup
        
        # Create keyboard with proper button instances
        keyboard = [
            [KeyboardButton("Scansiona 📸", web_app=WebAppInfo(url=os.getenv('WEBAPP_URL')))],
            [KeyboardButton("📊 Le mie analisi"), KeyboardButton("ℹ️ Aiuto")],
            [KeyboardButton("🔍 Cerca prodotto"), KeyboardButton("⭐️ Prodotti popolari")]
        ]
        
        reply_markup = ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            input_field_placeholder='Seleziona un\'opzione'
        )
        
        welcome_message = (
            "Benvenuto in WorthIt! 🚀\n\n"
            "Puoi:\n"
            "📸 Scansionare un prodotto\n"
            "🔍 Cercare un prodotto tramite link\n"
            "📊 Vedere le tue analisi salvate\n"
            "ℹ️ Ottenere aiuto\n"
        )
        
        await update.message.reply_text(
            welcome_message,
            reply_markup=reply_markup
        )

# Create a global bot instance
_bot_instance = None

def get_bot_instance(token: str = None) -> WorthItBot:
    global _bot_instance
    if _bot_instance is None and token:
        _bot_instance = WorthItBot(token)
    return _bot_instance

# Standalone command handlers for webhook integration
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot = get_bot_instance()
    if bot:
        await bot.start(update, context)
    else:
        raise Exception("Bot instance not initialized")

# Export the necessary components
__all__ = ['WorthItBot', 'start', 'get_bot_instance']

        async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        user_data = {} if context is None else context.user_data or {}
        
        try:
            # Check if user is in URL input mode
            if user_data.get('awaiting_url', False):
                # Reset the awaiting_url flag
                user_data['awaiting_url'] = False
                
                # Check if text contains a URL
                url_pattern = r'https?://[^\s]+'
                urls = re.findall(url_pattern, text)
                
                if urls or ("amazon" in text.lower() or "ebay" in text.lower()):
                    # Process the URL
                    url = urls[0] if urls else text
                    await analyze_product_url(update, url)
                else:
                    await update.message.reply_text("Non sembra un link valido. Per favore, invia un link di un prodotto valido.")
                    # Re-enable URL input mode since the input was invalid
                    user_data['awaiting_url'] = True
                    
            elif text == "🔍 Cerca prodotto":
                # Always set awaiting_url flag
                user_data['awaiting_url'] = True
                
                try:
                    await update.message.reply_text("Incolla il link del prodotto che vuoi analizzare 🔗")
                except RuntimeError as re:
                    if "Event loop is closed" in str(re):
                        # Create a new event loop and retry
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        await update.message.reply_text("Incolla il link del prodotto che vuoi analizzare 🔗")
                    else:
                        raise
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
        except RuntimeError as re:
            if "Event loop is closed" in str(re):
                print("Ignoring closed event loop error in handle_text")
            else:
                raise
        except Exception as e:
            print(f"Error in handle_text: {str(e)}")
            try:
                await update.message.reply_text("Mi dispiace, si è verificato un errore. Riprova più tardi.")
            except:
                pass


async def analyze_product_url(update: Update, url: str):
    try:
        # Validate URL
        validate_url(url)
        
        # Send immediate acknowledgment with event loop handling
        try:
            await update.message.reply_text("Sto analizzando il prodotto... Attendi un momento ⏳")
        except RuntimeError as re:
            if "Event loop is closed" in str(re):
                # Create a new event loop and retry
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                await update.message.reply_text("Sto analizzando il prodotto... Attendi un momento ⏳")
            else:
                raise
        
        # Enqueue the task for background processing
        from worker.queue import enqueue_task
        
        task = {
            'task_type': 'product_analysis',
            'url': url,
            'status': 'pending',
            'chat_id': update.effective_chat.id
        }
        
        # Add task to Redis queue
        try:
            await enqueue_task(task)
            return {"status": "processing", "message": "Task enqueued for processing"}
        except Exception as e:
            print(f"Failed to enqueue task: {e}")
            # Fall back to direct API call if queueing fails
            return await direct_api_call(update, url)
    except Exception as e:
        error_message = str(e)
        try:
            await update.message.reply_text(f"Mi dispiace, non sono riuscito ad analizzare questo prodotto. Errore: {error_message}")
        except RuntimeError as re:
            if "Event loop is closed" in str(re):
                # Create a new event loop and retry
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                await update.message.reply_text(f"Mi dispiace, non sono riuscito ad analizzare questo prodotto. Errore: {error_message}")
            else:
                raise
        return {"status": "error", "error": error_message}

async def direct_api_call(update: Update, url: str):
    """Fallback method to call API directly if queueing fails."""
    try:
        # Call our API to analyze the product
        vercel_url = os.getenv("VERCEL_URL", "worth-it-bot-git-main-parnassusxs-projects.vercel.app")
        api_host = os.getenv("API_HOST", f"https://{vercel_url}")
        api_url = f"{api_host}/api/analyze"
        
        # Use the shared HTTP client with optimized connection pooling
        client = get_http_client()
        try:
            response = await client.post(api_url, json={"url": url}, timeout=10.0)
            response_data = await response.json()
            
            if response.status_code != 200:
                error_detail = response_data.get('error', 'Unknown error')
                raise Exception(f"API error: {response.status_code} - {error_detail}")
            
            # Format and send the analysis results
            analysis_text = format_analysis_response(response_data)
            try:
                await update.message.reply_text(analysis_text, parse_mode="Markdown")
            except RuntimeError as re:
                if "Event loop is closed" in str(re):
                    # Create a new event loop and retry
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    await update.message.reply_text(analysis_text, parse_mode="Markdown")
                else:
                    raise
            return response_data
        finally:
            # Ensure HTTP client is closed properly
            await close_http_client()
    except Exception as e:
        print(f"Direct API call failed: {e}")
        return {"status": "error", "error": str(e)}

def format_analysis_response(data: Dict[str, Any]) -> str:
    """Format the analysis response into a readable message."""
    worth_it_score = data.get('worth_it_score', 0)
    price = data.get('price', 'N/A')
    title = data.get('title', 'Prodotto')
    pros = data.get('pros', [])
    cons = data.get('cons', [])
    
    message = f"*{title}*\n\n"
    message += f"💰 Prezzo: {price}\n"
    message += f"⭐ Punteggio WorthIt: {worth_it_score}/10\n\n"
    
    if pros:
        message += "✅ *Punti di forza:*\n"
        for pro in pros:
            message += f"• {pro}\n"
        message += "\n"
    
    if cons:
        message += "❌ *Punti deboli:*\n"
        for con in cons:
            message += f"• {con}\n"
    
    return message

# Export handlers for webhook_handler.py
__all__ = ['start', 'handle_text', 'WorthItBot']

    async def run(self):
        await self.app.initialize()
        await self.app.start()
        await self.app.run_polling()

    async def handle_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Funzionalità in arrivo nelle prossime versioni!")

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "*Come usare WorthIt!*\n\n"
            "1️⃣ Invia un link di un prodotto\n"
            "2️⃣ Usa il pulsante 'Scansiona 📸' per aprire l'app web\n"
            "3️⃣ Ricevi un'analisi dettagliata sul valore reale del prodotto\n\n"
            "WorthIt! analizza recensioni e caratteristiche per dirti se un prodotto vale davvero il suo prezzo."
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def handle_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context:
            context.user_data['awaiting_url'] = True
        await update.message.reply_text("Incolla il link del prodotto che vuoi analizzare 🔗")

    async def handle_popular(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Funzionalità in arrivo nelle prossime versioni!")

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f'Error occurred: {context.error}')
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "Mi dispiace, si è verificato un errore. Riprova più tardi."
                )
        except Exception as e:
            print(f'Error in error handler: {e}')