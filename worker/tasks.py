import asyncio
import json
import logging
from typing import Dict, Any
from telegram import Bot, Update
from .queue import get_redis_client, get_task_by_id
from bot.webhook_handler import process_telegram_update, analyze_product, format_analysis_response, get_bot_instance

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
        await process_telegram_update(update)
    except Exception as e:
        logger.error(f"Error processing Telegram update: {e}")
        raise

async def process_product_analysis_task(task_data: Dict[str, Any]) -> None:
    """Process a product analysis task and send results back to the user."""
    try:
        url = task_data.get('url')
        chat_id = task_data.get('chat_id')
        if not url or not chat_id:
            raise ValueError("Missing required task data (url or chat_id)")
        
        # Get bot instance
        bot = get_bot_instance()
        
        try:
            # Perform the analysis
            analysis_result = await analyze_product(url)
            
            # Format the response
            message, keyboard = await format_analysis_response(analysis_result)
            
            # Send the results back to the user
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        except Exception as analysis_error:
            error_message = "Mi dispiace, si è verificato un errore durante l'analisi del prodotto. "
            if "Invalid product URL" in str(analysis_error):
                error_message += "Assicurati di usare un link valido di Amazon o eBay."
            elif "API authentication error" in str(analysis_error):
                error_message += "C'è un problema con l'autenticazione. Riprova più tardi."
            else:
                error_message += "Riprova più tardi."
            
            await bot.send_message(
                chat_id=chat_id,
                text=error_message
            )
    except Exception as e:
        logger.error(f"Error processing product analysis: {e}")
        raise