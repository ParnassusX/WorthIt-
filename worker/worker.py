import asyncio
import os
import logging
import time
from telegram import Bot
from dotenv import load_dotenv
from typing import Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential

# Import the queue interface
from worker.queue import get_task_queue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

async def process_task(task: Dict[str, Any], bot: Bot) -> None:
    """Process a single task from the queue"""
    try:
        logger.info(f"Processing task: {task['task_type']}")
        
        if task['task_type'] == 'telegram_update':
            # Process Telegram update from webhook
            from bot.webhook_handler import process_telegram_update
            
            # Reconstruct the Update object
            update = Update.de_json(task['update_data'], bot)
            
            # Process the update
            await process_telegram_update(update)
            
        elif task['task_type'] == 'product_analysis':
            # Import here to avoid circular imports
            from api.main import analyze_product
            from api.scraper import ProductScraper
            from api.ml_processor import MLProcessor
            
            # Send processing message with stages
            await bot.send_message(
                chat_id=task['chat_id'],
                text="🔍 *Analisi in corso...*\n\n1️⃣ Raccolta dati del prodotto\n2️⃣ Analisi delle recensioni\n3️⃣ Valutazione del rapporto qualità/prezzo",
                parse_mode='Markdown'
            )
            
            # Initialize processors
            scraper = ProductScraper()
            ml_processor = MLProcessor()
            
            try:
                # Step 1: Scrape product data
                await bot.send_message(
                    chat_id=task['chat_id'],
                    text="⏳ Raccolta informazioni sul prodotto..."
                )
                product_data = await scraper.extract_product(task['url'])
                
                # Step 2: Process reviews with ML
                await bot.send_message(
                    chat_id=task['chat_id'],
                    text="⏳ Analisi delle recensioni e del sentiment..."
                )
                reviews = [{'review': r} for r in product_data.get('reviews', [])]
                sentiment_data = await ml_processor.analyze_sentiment(reviews)
                pros_cons = await ml_processor.extract_pros_cons(reviews, product_data)
                
                # Step 3: Calculate value score
                await bot.send_message(
                    chat_id=task['chat_id'],
                    text="⏳ Calcolo del punteggio di valore..."
                )
                value_score = await ml_processor.calculate_value_score(product_data, sentiment_data)
                
                # Step 4: Compile results
                result = {
                    'title': product_data['title'],
                    'price': product_data['price'],
                    'value_score': value_score,
                    'recommendation': get_recommendation(value_score),
                    'pros': pros_cons['pros'],
                    'cons': pros_cons['cons'],
                    'url': task['url']
                }
                
                # Format the response with inline keyboard
                from bot.webhook_handler import format_analysis_response
                message, keyboard = await format_analysis_response(result)
                
                # Send the final result back to the user
                await bot.send_message(
                    chat_id=task['chat_id'],
                    text=message,
                    parse_mode='Markdown',
                    reply_markup=keyboard
                )
                
            except Exception as analysis_error:
                logger.error(f"Analysis error: {analysis_error}")
                await bot.send_message(
                    chat_id=task['chat_id'],
                    text="❌ Mi dispiace, si è verificato un errore durante l'analisi del prodotto.\n\nDettaglio: " + str(analysis_error)
                )
        
        elif task['task_type'] == 'product_search':
            # Import scraper
            from api.scraper import ProductScraper
            
            # Send processing message
            await bot.send_message(
                chat_id=task['chat_id'],
                text="🔍 Ricerca prodotti in corso..."
            )
            
            try:
                # Initialize scraper and search
                scraper = ProductScraper()
                search_results = await scraper.search_products(task['query'])
                
                if search_results:
                    # Format results message
                    results_text = "*Risultati della ricerca:*\n\n"
                    for i, product in enumerate(search_results[:5], 1):
                        results_text += f"{i}. [{product['title']}]({product['url']})\n"
                        results_text += f"💰 {product['price']}\n\n"
                    
                    await bot.send_message(
                        chat_id=task['chat_id'],
                        text=results_text,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                else:
                    await bot.send_message(
                        chat_id=task['chat_id'],
                        text="Nessun prodotto trovato per la tua ricerca."
                    )
                    
            except Exception as search_error:
                logger.error(f"Search error: {search_error}")
                await bot.send_message(
                    chat_id=task['chat_id'],
                    text="Mi dispiace, si è verificato un errore durante la ricerca."
                )
        
        elif task['task_type'] == 'image_analysis':
            # Import here to avoid circular imports
            from api.image_analyzer import analyze_image
            
            # Process image analysis
            result = await analyze_image(task['image_url'])
            
            # Send the result back to the user
            await bot.send_message(
                chat_id=task['chat_id'],
                text=f"📊 *Analisi immagine completata*\n\n{result['summary']}",
                parse_mode='Markdown'
            )
        
        else:
            logger.warning(f"Unknown task type: {task['task_type']}")
            await bot.send_message(
                chat_id=task['chat_id'],
                text="Mi dispiace, non riconosco questo tipo di attività."
            )
            
    except Exception as e:
        logger.error(f"Error processing task: {e}")
        # Try to notify the user if we have a chat_id
        if 'chat_id' in task:
            try:
                await bot.send_message(
                    chat_id=task['chat_id'],
                    text="❌ Si è verificato un errore durante l'elaborazione della richiesta."
                )
            except Exception as notify_error:
                logger.error(f"Failed to notify user of error: {notify_error}")

# Helper function for recommendation text
def get_recommendation(value_score: float) -> str:
    """Get recommendation text based on value score"""
    if value_score >= 8.0:
        return "Ottimo acquisto! Questo prodotto offre un eccellente rapporto qualità/prezzo."
    elif value_score >= 6.0:
        return "Buon acquisto. Il prodotto vale il suo prezzo."
    elif value_score >= 4.0:
        return "Acquisto nella media. Valuta se ci sono alternative migliori."
    else:
        return "Non consigliato. Il prodotto non vale il prezzo richiesto."

async def main() -> None:
    """Main worker loop that processes tasks from the queue"""
    # Initialize the bot
    telegram_token = os.getenv("TELEGRAM_TOKEN")
    if not telegram_token:
        logger.error("TELEGRAM_TOKEN environment variable is not set")
        return
    
    bot = Bot(token=telegram_token)
    queue = get_task_queue()
    
    logger.info("Worker started, waiting for tasks...")
    
    while True:
        try:
            # Get a task from the queue (blocking operation)
            task = await queue.dequeue()
            logger.info(f"Received task: {task['task_type']}")
            
            # Process the task
            await process_task(task, bot)
            
        except Exception as e:
            logger.error(f"Error in worker loop: {e}", exc_info=True)
            # Brief pause to prevent tight loop in case of persistent errors
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())