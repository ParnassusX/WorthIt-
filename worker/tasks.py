import asyncio
import json
import logging
from typing import Dict, Any
from telegram import Bot, Update
from .queue import get_redis_client, get_task_by_id
from bot.webhook_handler import analyze_product, format_analysis_response, get_bot_instance

logger = logging.getLogger(__name__)

async def process_task(task_id: str, task_data: Dict[str, Any]) -> None:
    """Process a task from the queue based on its type."""
    try:
        task_type = task_data.get('task_type')
        if task_type == 'telegram_update':
            await process_telegram_update_task(task_data)
        elif task_type == 'product_analysis':
            await process_product_analysis_task(task_data)
        else:
            logger.error(f"Unknown task type: {task_type}")
    except Exception as e:
        logger.error(f"Error processing task {task_id}: {e}")
        # Update task status to failed
        redis_client = await get_redis_client()
        task = await get_task_by_id(task_id)
        if task:
            task['status'] = 'failed'
            task['error'] = str(e)
            await redis_client.set(f"task:{task_id}", json.dumps(task))

async def process_telegram_update_task(task_data: Dict[str, Any]) -> None:
    """Process a Telegram update task."""
    try:
        update_data = task_data.get('update_data')
        if not update_data:
            raise ValueError("No update data provided")
        
        bot = get_bot_instance()
        update = Update.de_json(update_data, bot)
        
        # Process commands and messages
        if update.message:
            if update.message.text:
                if update.message.text.startswith('/'):
                    await process_command(update)
                else:
                    await process_message(update)
            
    except Exception as e:
        logger.error(f"Error processing Telegram update: {e}")
        raise

async def process_command(update: Update) -> None:
    """Process bot commands"""
    command = update.message.text.split()[0][1:]
    bot = get_bot_instance()
    
    if command == 'start':
        # Create keyboard with proper button instances
        from telegram import KeyboardButton, WebAppInfo, ReplyKeyboardMarkup
        
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

async def process_message(update: Update) -> None:
    """Process non-command messages"""
    text = update.message.text
    
    if text == "🔍 Cerca prodotto":
        await update.message.reply_text("Incolla il link del prodotto che vuoi analizzare 🔗")
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
        # Check if it might be a product URL
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, text)
        
        if urls or ("amazon" in text.lower() or "ebay" in text.lower()):
            url = urls[0] if urls else text
            await process_product_analysis_task({
                'url': url,
                'chat_id': update.message.chat_id,
                'id': str(update.message.message_id)
            })
        else:
            await update.message.reply_text("Non ho capito. Invia un link di un prodotto o usa i pulsanti in basso.")

async def process_product_analysis_task(task_data: Dict[str, Any]) -> None:
    """Process a product analysis task and send results back to the user."""
    try:
        url = task_data.get('url')
        chat_id = task_data.get('chat_id')
        task_id = task_data.get('id')
        if not url or not chat_id:
            raise ValueError("Missing required task data (url or chat_id)")
        
        # Get bot instance
        bot = get_bot_instance()
        
        # Send initial status message
        status_message = await bot.send_message(
            chat_id=chat_id,
            text="🔄 Analisi in corso..."
        )
        
        try:
            # Update task status
            redis_client = await get_redis_client()
            await redis_client.hset(f"task:{task_id}", 'status', 'analyzing')
            
            # Send progress update
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text="🔍 Raccolta informazioni sul prodotto..."
            )
            
            # Perform the analysis
            analysis_result = await analyze_product(url)
            
            # Update progress
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text="✨ Elaborazione dei risultati..."
            )
            
            # Format the response
            message, keyboard = await format_analysis_response(analysis_result)
            
            # Update task status to completed
            await redis_client.hset(f"task:{task_id}", 'status', 'completed')
            
            # Send the final results
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=message,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        except Exception as analysis_error:
            error_message = "❌ Mi dispiace, si è verificato un errore durante l'analisi del prodotto. "
            if "Invalid product URL" in str(analysis_error):
                error_message += "Assicurati di usare un link valido di Amazon o eBay."
            elif "API authentication error" in str(analysis_error):
                error_message += "C'è un problema con l'autenticazione. Riprova più tardi."
            else:
                error_message += "Riprova più tardi."
            
            # Update task status to failed
            await redis_client.hset(f"task:{task_id}", 'status', 'failed')
            
            # Update the status message with error
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=error_message
            )
    except Exception as e:
        logger.error(f"Error processing product analysis: {e}")
        raise